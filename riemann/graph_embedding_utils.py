import torch
import torch.nn as nn
from torch.nn import Embedding
from torch.nn.functional import cross_entropy, kl_div, log_softmax, softmax, relu_, mse_loss, cosine_similarity, relu
from manifolds import RiemannianManifold
from manifold_tensors import ManifoldParameter
from typing import Dict, List
from embedding import GloveSentenceEmbedder
from embedding import SimpleSentence
from tqdm import tqdm
from embed_save import Savable
from jacobian import compute_jacobian
import numpy as np
from manifold_initialization import initialize_manifold_tensor
from torch.autograd import Function

EPSILON = 1e-9

def manifold_dist_loss_relu_sum(model: nn.Module, inputs: torch.Tensor, train_distances: torch.Tensor, manifold: RiemannianManifold, margin=0.01, discount_factor=0.9):
    """ See write up for details on this loss function -- encourages embeddings to preserve graph topology
    Args:
        model (nn.Module): model that takes in graph indices and outputs embeddings
        inputs (torch.Tensor): LongTensor of shape [batch_size, num_samples+1] giving the indices of the vertices to be trained with the first vertex in each element of the batch being the main vertex and the others being samples
        train_distances (torch.Tensor): floating point tensor of shape [batch_size, num_samples] containing the training distances from the input vertex to the sampled vertices
        manifold (RiemannianManifold): Manifold that model embeds vertices into

    Returns:
        loss (scalar): Computed loss
    """
    
    input_embeddings = model(inputs)

    sample_vertices = input_embeddings.narrow(1, 1, input_embeddings.size(1)-1)
    main_vertices = input_embeddings.narrow(1, 0, 1).expand_as(sample_vertices)
    manifold_dists = manifold.dist(main_vertices, sample_vertices)

    sorted_indices = train_distances.argsort(dim=-1)
    manifold_dists_sorted = torch.gather(manifold_dists, -1, sorted_indices)
    manifold_dists_sorted.add_(EPSILON).log_()
    diff_matrix_shape = [manifold_dists.size()[0], manifold_dists.size()[1], manifold_dists.size()[1]]
    row_expanded = manifold_dists_sorted.unsqueeze(2).expand(*diff_matrix_shape)
    column_expanded = manifold_dists_sorted.unsqueeze(1).expand(*diff_matrix_shape)
    diff_matrix = row_expanded - column_expanded + margin

    train_dists_sorted = torch.gather(train_distances, -1, sorted_indices)
    train_row_expanded = train_dists_sorted.unsqueeze(2).expand(*diff_matrix_shape)
    train_column_expanded = train_dists_sorted.unsqueeze(1).expand(*diff_matrix_shape)
    diff_matrix_train = train_row_expanded - train_column_expanded
    masked_diff_matrix = torch.where(diff_matrix_train == 0, diff_matrix_train, diff_matrix)
    masked_diff_matrix.triu_()
    relu_(masked_diff_matrix)
    masked_diff_matrix = masked_diff_matrix.mean(-1)
    order_scale = torch.arange(0, masked_diff_matrix.size()[1], device=masked_diff_matrix.device, dtype=masked_diff_matrix.dtype)
    order_scale = (torch.ones_like(order_scale) * discount_factor).pow(order_scale)
    order_scale = order_scale.unsqueeze_(0).expand_as(masked_diff_matrix) 
    masked_diff_matrix *= order_scale
    loss = masked_diff_matrix.sum(-1).mean()
    return loss

def metric_loss(model: nn.Module, input_embeddings: torch.Tensor, in_manifold: RiemannianManifold, out_manifold: RiemannianManifold, out_dimension, isometric=False, random_samples=0, random_init = None):
    input_embeddings = model.input_embedding(input_embeddings)
    if random_samples > 0:
        random_samples = torch.empty(random_samples, input_embeddings.size()[1], dtype=input_embeddings.dtype, device=input_embeddings.device)
        initialize_manifold_tensor(random_samples, in_manifold, random_init)
        input_embeddings = torch.cat([input_embeddings, random_samples])

    model = model.embedding_model
    jacobian, model_out = compute_jacobian(model, input_embeddings, out_dimension)
    jacobian = jacobian.clamp(-1, 1)
    tangent_proj_out = out_manifold.tangent_proj_matrix(model_out)
    jacobian_shape = jacobian.size()
    tangent_proj_out_shape = tangent_proj_out.size()
    tangent_proj_out_batch = tangent_proj_out.view(-1, tangent_proj_out_shape[-2], tangent_proj_out_shape[-1])
    jacobian_batch = jacobian.view(-1, jacobian_shape[-2], jacobian_shape[-1])

    tangent_proj_in = in_manifold.tangent_proj_matrix(input_embeddings)
    proj_eigenval, proj_eigenvec = torch.symeig(tangent_proj_in, eigenvectors=True)
    first_nonzero = (proj_eigenval > 1e-3).nonzero()[0][1]
    significant_eigenvec = proj_eigenvec.narrow(-1, first_nonzero, proj_eigenvec.size()[-1] - first_nonzero)
    significant_eigenvec_shape = significant_eigenvec.size()
    significant_eigenvec_batch = significant_eigenvec.view(-1, significant_eigenvec_shape[-2], significant_eigenvec_shape[-1])
    metric_conjugator = torch.bmm(torch.bmm(tangent_proj_out_batch, jacobian_batch), significant_eigenvec_batch)
    metric_conjugator_t = torch.transpose(metric_conjugator, -2, -1)
    out_metric = out_manifold.get_metric_tensor(model_out)
    out_metric_shape = out_metric.size()
    out_metric_batch = out_metric.view(-1, out_metric_shape[-2], out_metric_shape[-1])
    pullback_metric = torch.bmm(torch.bmm(metric_conjugator_t, out_metric_batch), metric_conjugator)
    in_metric = in_manifold.get_metric_tensor(input_embeddings)
    in_metric_shape = in_metric.size()
    in_metric_batch = in_metric.view(-1, in_metric_shape[-2], in_metric_shape[-1])
    sig_eig_t = torch.transpose(significant_eigenvec_batch, -2, -1)
    in_metric_reduced = torch.bmm(torch.bmm(sig_eig_t, in_metric_batch), significant_eigenvec_batch)
    in_metric_flattened = in_metric_batch.view(in_metric_reduced.size()[0], -1)
    pullback_flattened = pullback_metric.view(pullback_metric.size()[0], -1)

    if isometric:
        loss = riemannian_divergence(in_metric_reduced, pullback_metric).mean()
        #loss = log_det_divergence(in_metric_reduced, pullback_metric).mean()
    else:
        loss = -torch.mean(cosine_similarity(pullback_flattened, in_metric_flattened, -1))

    return loss

def riemannian_divergence(matrix_a: torch.Tensor, matrix_b: torch.Tensor):
    matrix_a_inv = torch.inverse(matrix_a)
    ainvb = torch.bmm(matrix_a_inv, matrix_b)
    eigenvalues, _ = torch.symeig(ainvb, eigenvectors=True)
    eigenvalues_positive = torch.clamp(eigenvalues, min=1e-5) 
    log_eig = torch.log(eigenvalues_positive)
    return log_eig.norm(dim=-1) ** 2

def closest_pd_matrix(matrix: torch.Tensor):
    eigenvalues, vectors = torch.symeig(matrix, eigenvectors=True)
    eigenvalues = relu(eigenvalues)
    diag_vals = torch.diag_embed(eigenvalues, offset=0, dim1=-2, dim2=-1)
    nearest_psd = torch.bmm(torch.bmm(vectors, diag_vals), vectors.transpose(-1, -2))
    if eigenvalues.min() < 1e-3:
        offset = 1e-3 * torch.eye(nearest_psd.size()[-1], device=nearest_psd.device, dtype=nearest_psd.dtype).unsqueeze(0).expand_as(nearest_psd)
        return nearest_psd + offset
    else:
        return nearest_psd

def log_det_divergence(matrix_a: torch.Tensor, matrix_b: torch.Tensor):
    ab_product = torch.bmm(matrix_a, matrix_b)
    ab_sum = (matrix_a + matrix_b) / 2
    logdet_sum = torch.logdet(ab_sum)
    logdet_product = (torch.logdet(ab_product) / 2)
    divergence = logdet_sum - logdet_product
    return divergence

class ManifoldEmbedding(Embedding, Savable):

    def __init__(
            self,
            manifold: RiemannianManifold,
            num_embeddings,
            embedding_dim,
            padding_idx=None,
            max_norm=None,
            norm_type=2.0,
            scale_grad_by_freq=False,
            sparse=False,
            _weight=None):
        super().__init__(num_embeddings, embedding_dim, padding_idx=padding_idx, max_norm=max_norm, norm_type=norm_type, scale_grad_by_freq=scale_grad_by_freq, sparse=sparse, _weight=_weight)

        self.manifold = manifold
        self.params = [manifold, num_embeddings, embedding_dim, padding_idx, max_norm, norm_type, scale_grad_by_freq, sparse]
        self.weight = ManifoldParameter(self.weight.data, manifold=manifold)
    
    def get_embedding_matrix(self):
        return self.weight.data

    def get_save_data(self):
        return {
            'state_dict': self.state_dict(),
            'params': self.params
        }

    @classmethod
    def from_save_data(cls, data):
        params = data["params"]
        state_dict = data["state_dict"]
        embedding = ManifoldEmbedding(*params)
        embedding.load_state_dict(state_dict)
        return embedding

    def get_savable_model(self):
        return self

class FeaturizedModelEmbedding(nn.Module):
    def __init__(self, embedding_model: nn.Module, features_list, in_manifold, featurizer=None, featurizer_dim=0, dtype=torch.float, device=None):
        super(FeaturizedModelEmbedding, self).__init__()
        self.embedding_model = embedding_model
        if featurizer is None:
            featurizer, featurizer_dim = get_canonical_glove_sentence_featurizer()
        self.featurizer = featurizer
        self.featurizer_dim = featurizer_dim
        self.input_embedding = get_featurized_embedding(features_list, featurizer, featurizer_dim, dtype=dtype, device=device)
        in_manifold.proj_(self.input_embedding.weight)

    def forward(self, x):
        return self.embedding_model(self.input_embedding(x))

    def forward_featurize(self, feature):
        featurized = self.embedding_model(self.featurizer(feature))
        return featurized

    def get_embedding_matrix(self):
        out = self.embedding_model(self.input_embedding.weight.data)
        return out

    def get_savable_model(self):
        return self.embedding_model

def get_canonical_glove_sentence_featurizer():
    embedder = GloveSentenceEmbedder.canonical()
    return lambda sent : embedder.embed(SimpleSentence.from_text(sent), l2_normalize=False), embedder.dim

def get_featurized_embedding(features: List, featurizer, featurizer_dim, dtype=torch.float, device=None, verbose=True):
    embeddings_list = np.empty((len(features), featurizer_dim))
    iterator = range(len(features))
    if verbose:
        print("Processing features of dataset...") 
        iterator = tqdm(iterator)
    for i in iterator:
        embeddings_list[i] = featurizer(features[i])
    return Embedding.from_pretrained(torch.as_tensor(np.array(embeddings_list), dtype=dtype, device=device))

