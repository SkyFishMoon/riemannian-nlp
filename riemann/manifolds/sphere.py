from .manifold import RiemannianManifold
import torch

# Determines when to use approximations when dividing by small values is a possibility
EPSILON = 1e-4

class GradClippedACos(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x):
        x = x.clamp(-1,  1)
        ctx.save_for_backward(x)
        dtype = x.dtype
        return torch.acos(x)

    @staticmethod
    def backward(ctx, grad_output):
        x, = ctx.saved_tensors
        x = x.clamp(-1 + EPSILON, 1 - EPSILON)
        grad = - grad_output / ((1 - x ** 2) ** 0.5)
        return grad

def acos(x):
    return GradClippedACos.apply(x)

class SphericalManifold(RiemannianManifold):
    '''
    Implementation of Spherical Riemannian manifold with standard pullback metric
    '''

    @classmethod
    def from_params(cls, params):
        return SphericalManifold()

    def proj(self, x, indices=None):
        if indices is not None:
            norm = x[indices].norm(dim=-1, keepdim=True)
            x_proj = x.clone()
            x_proj[indices] /= norm
        else:
            norm = x.norm(dim=-1, keepdim=True)
            return x / norm

    def proj_(self, x, indices=None):
        if indices is not None:
            norm = x[indices].norm(dim=-1, keepdim=True)
            x[indices] /= norm
            return x
        else:
            norm = x.norm(dim=-1, keepdim=True)
            return x.div_(norm)

    def retr(self, x, u, indices=None):
        if indices is not None:
            y = x.index_add(0, indices, u)
        else:
            y = x + u
        return self.proj(y, indices)

    def retr_(self, x, u, indices=None):
        if indices is not None:
            x.index_add_(0, indices, u)
        else:
            x = x.add_(u)
        return self.proj_(x, indices)

    def exp(self, x, u):
        norm_u = u.norm(dim=-1, keepdim=True)
        
        exp = x * torch.cos(norm_u) + u * torch.sin(norm_u) / norm_u
        retr = self.proj(x + u)
        cond = norm_u > EPSILON
        return torch.where(cond, exp, retr)

    def log(self, x, y):
        u = y - x
        u.sub_((x * u).sum(dim=-1, keepdim=True) * x)
        dist = self.dist(x, y, keepdim=True)
        norm_u = u.norm(dim=-1, keepdim=True)
        cond = norm_u > EPSILON
        return torch.where(cond, u * dist / norm_u, u)

    def dist(self, x, y, keepdim=False):
        inner = (x * y).sum(-1, keepdim=keepdim)
        # Scale slightly down to keep things differentiable and use Euclidean distance when
        # it's an approriate approximation
        inner = inner.clamp(-1, 1)
        return acos(inner)

    def rgrad(self, x, dx):
        return dx - (x * dx).sum(dim=-1, keepdim=True) * x

    def rgrad_(self, x, dx):
        return dx.sub_((x * dx).sum(dim=-1, keepdim=True) * x)

RiemannianManifold.register_manifold(SphericalManifold)