from math import pi

import numpy as np
import torch
from torch.distributions import Distribution, constraints

from rotations import aa_to_rmat, rmat_to_aa


class IsotropicGaussianSO3(Distribution):
    arg_constraints = {'eps': constraints.positive}

    def __init__(self, eps: torch.Tensor, mean: torch.Tensor = torch.eye(3)):
        self.eps = eps
        self._mean = mean.to(eps)
        self._mean_inv = self._mean.permute(-1, -2)  # orthonormal so inverse = Transpose
        pdf_sample_locs = pi * torch.linspace(0, 1.0, 1000)[:, None] ** 3.0  # Pack more samples near 0
        pdf_sample_vals = self._eps_ft(pdf_sample_locs)
        pdf_val_sums = pdf_sample_vals[:-1] + pdf_sample_vals[1:]
        pdf_loc_diffs = torch.diff(pdf_sample_locs, dim=0)
        self.trap = (pdf_loc_diffs * pdf_val_sums / 2).cumsum(dim=0)
        self.trap_loc = pdf_sample_locs[1:]
        super().__init__()

        print('aaa')

    def rsample(self, sample_shape=torch.Size()):
        # Consider axis-angle form.
        axes = torch.randn((*sample_shape, *self.eps.shape, 3)).to(self.eps)
        axes = axes / axes.norm(dim=-1, keepdim=True)
        # Inverse transform sampling based on numerical approximation of CDF
        unif = torch.rand((*sample_shape, *self.eps.shape))
        idx_1 = (self.trap < unif).sum(dim=0)
        idx_0 = idx_1 - 1
        trap_start = torch.gather(self.trap, 0, idx_0[None])
        trap_end = torch.gather(self.trap, 0, idx_1[None])
        weight = ((unif - trap_start) / (trap_end - trap_start))[0]
        angle_start = self.trap_loc[idx_0][..., 0]
        angle_end = self.trap_loc[idx_1][..., 0]
        angles = torch.lerp(angle_start, angle_end, weight)[..., None]
        return self._mean @ aa_to_rmat(axes, angles)

    def sample(self, sample_shape=torch.Size()):
        with torch.no_grad():
            return self.rsample(sample_shape)

    def _eps_ft_inner(self, l, t: torch.Tensor) -> torch.Tensor:
        lt_sin = torch.sin((l + 0.5) * t) / torch.sin(t / 2)
        return (2 * l + 1) * torch.exp(-l * (l + 1) * (self.eps ** 2)) * lt_sin

    def _eps_ft(self, t: torch.Tensor) -> torch.Tensor:
        maxdims = max(len(self.eps.shape), len(t.shape))
        # This is an infinite sum, approximate with 10/eps values
        l_count = min(np.round(10 / self.eps.min() ** 2).item(), 1e6)
        if l_count == 1e6:
            print("Very small eps!", self.eps.min())
        l = torch.arange(l_count).reshape((-1, *([1] * maxdims))).to(self.eps)
        inner = self._eps_ft_inner(l, t)
        vals = inner.sum(dim=0) * ((1 - t.cos()) / pi)
        vals[(t == 0).expand_as(vals)] = 0.0
        return vals

    def _np_pdf(self, t: np.array) -> float:
        t = torch.from_numpy(t)
        l_vals = self._eps_ft(t)
        return l_vals.detach().numpy()

    def log_prob(self, rotations):
        _, angles = rmat_to_aa(rotations)
        probs = self._eps_ft(angles)
        return probs.log()

    @property
    def mean(self):
        return self._mean


if __name__ == "__main__":
    epsilon = torch.tensor([0.03, 0.1, 0.5, 0.9, 3.0])
    dist = IsotropicGaussianSO3(epsilon)
    rot = dist.sample()
    print('aaaa')