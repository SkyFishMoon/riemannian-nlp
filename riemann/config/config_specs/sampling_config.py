from ..config import ConfigDict
from ..graph_sampling_config import GraphSamplingConfig

CONFIG_NAME = "sampling"


class SamplingConfig(ConfigDict):
    """
    Configuration for neighborhood sampling
    """
    train_sampling_config: GraphSamplingConfig = GraphSamplingConfig(
        n_graph_neighbors=20,
        n_rand_neighbors=50,
        n_manifold_neighbors=0,
        batch_size=5000
    )
    eval_sampling_config: GraphSamplingConfig = GraphSamplingConfig(
        n_graph_neighbors=500,
        n_rand_neighbors=500,
        n_manifold_neighbors=0,
        batch_size=1000
    )

    manifold_neighbor_block_size: int = 100000
    manifold_nn_k: int = 600
    manifold_neighbor_resampling_rate: int = 1
