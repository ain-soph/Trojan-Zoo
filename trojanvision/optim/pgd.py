#!/usr/bin/env python3

from re import A
import trojanzoo.optim

from trojanzoo.utils import add_noise, cos_sim
from trojanzoo.utils.output import prints
from trojanzoo.environ import env

import torch
import torch.autograd
from collections.abc import Callable
from typing import Iterable, Union


class PGD(trojanzoo.optim.Optimizer):
    r"""Projected Gradient Descent.
    Args:
        pgd_alpha (float): learning rate :math:`\pgd_alpha`. Default: :math:`\frac{3}{255}`.
        pgd_eps (float): the perturbation threshold :math:`\pgd_eps` in input space. Default: :math:`\frac{8}{255}`.

        norm (int): :math:`L_p` norm passed to :func:`torch.norm`. Default: ``float(inf)``.
        universal (bool): All inputs in the batch share the same noise. Default: ``False``.

        grad_method (str): gradient estimation method. Default: ``white``.
        query_num (int): number of samples in black box gradient estimation. Default: ``100``.
        sigma (float): gaussian noise std in black box gradient estimation. Default: ``0.001``.
    """

    name: str = 'pgd'

    def __init__(self, pgd_alpha: Union[float, torch.Tensor] = 2.0 / 255,
                 pgd_eps: Union[float, torch.Tensor] = 8.0 / 255, iteration: int = 7,
                 random_init: bool = False,
                 norm: Union[int, float] = float('inf'), universal: bool = False,
                 clip_min: Union[float, torch.Tensor] = 0.0,
                 clip_max: Union[float, torch.Tensor] = 1.0,
                 grad_method: str = 'white', query_num: int = 100, sigma: float = 1e-3,
                 hess_b: int = 100, hess_p: int = 1, hess_lambda: float = 1, **kwargs):
        super().__init__(iteration=iteration, **kwargs)
        self.param_list['pgd'] = ['pgd_alpha', 'pgd_eps', 'norm', 'universal']

        self.pgd_alpha = pgd_alpha
        self.pgd_eps = pgd_eps
        self.random_init = random_init

        self.norm = norm
        self.universal = universal

        self.clip_min = clip_min
        self.clip_max = clip_max

        self.grad_method: str = grad_method
        if grad_method != 'white':
            self.param_list['blackbox'] = ['grad_method', 'query_num', 'sigma']
            self.query_num: int = query_num
            self.sigma: float = sigma
            if grad_method == 'hess':
                self.param_list['hessian'] = ['hess_b', 'hess_p', 'hess_lambda']
                self.hess_b: int = hess_b
                self.hess_p: int = hess_p
                self.hess_lambda: float = hess_lambda

    def valid_noise(self, X: torch.Tensor, _input: torch.Tensor) -> torch.Tensor:
        if self.universal:
            return (X - _input).mode(dim=0)[0].detach()
        return (X - _input).detach()

    def init_noise(self, noise_shape: Iterable[int], pgd_eps: Union[float, torch.Tensor] = None,
                   random_init: bool = None, device: Union[str, torch.device] = None) -> torch.Tensor:
        pgd_eps = pgd_eps if pgd_eps is not None else self.pgd_eps
        random_init = random_init if random_init is not None else self.random_init
        device = device if device is not None else env['device']
        noise: torch.Tensor = torch.zeros(noise_shape, dtype=torch.float, device=device)
        if random_init:
            if isinstance(pgd_eps, torch.Tensor) and pgd_eps.shape[0] != 1:
                assert all([size == 1 for size in pgd_eps.shape[1:]])
                for i in range(pgd_eps.shape[0]):
                    data = noise[i, :, :] if noise.dim() == 3 else noise[:, i, :, :]
                    data.uniform_(-pgd_eps[i].item(), pgd_eps[i].item())
            else:
                pgd_eps = float(pgd_eps)
                noise.uniform_(-pgd_eps, pgd_eps)
        return noise

    def optimize(self, _input: torch.Tensor, noise: torch.Tensor = None,
                 pgd_alpha: Union[float, torch.Tensor] = None,
                 pgd_eps: Union[float, torch.Tensor] = None,
                 iteration: int = None, loss_fn: Callable[[torch.Tensor], torch.Tensor] = None,
                 output: Union[int, list[str]] = None, add_noise_fn=None,
                 random_init: bool = None,
                 clip_min: Union[float, torch.Tensor] = None,
                 clip_max: Union[float, torch.Tensor] = None,
                 **kwargs) -> tuple[torch.Tensor, int]:
        # ------------------------------ Parameter Initialization ---------------------------------- #
        clip_min = clip_min if clip_min is not None else self.clip_min
        clip_max = clip_max if clip_max is not None else self.clip_max

        pgd_alpha = pgd_alpha if pgd_alpha is not None else self.pgd_alpha
        pgd_eps = pgd_eps if pgd_eps is not None else self.pgd_eps
        iteration = iteration if iteration is not None else self.iteration
        random_init = random_init if random_init is not None else self.random_init
        loss_fn = loss_fn if loss_fn is not None else self.loss_fn
        add_noise_fn = add_noise_fn if add_noise_fn is not None else add_noise
        output = self.get_output(output)

        if noise is None:
            noise_shape = _input.shape[1:] if self.universal else _input.shape
            noise = self.init_noise(noise_shape, pgd_eps=pgd_eps, random_init=random_init, device=_input.device)
        # ----------------------------------------------------------------------------------------- #

        if 'start' in output:
            self.output_info(_input=_input, noise=noise, mode='start', loss_fn=loss_fn, **kwargs)
        a = pgd_alpha if isinstance(pgd_alpha, torch.Tensor) else torch.tensor(pgd_alpha)
        b = pgd_eps if isinstance(pgd_eps, torch.Tensor) else torch.tensor(pgd_eps)
        condition_alpha = torch.allclose(a, torch.zeros_like(a))
        condition_eps = torch.allclose(b, torch.zeros_like(b))
        if iteration == 0 or condition_alpha or condition_eps:
            return _input, None

        X = add_noise_fn(_input=_input, noise=noise, batch=self.universal,
                         clip_min=clip_min, clip_max=clip_max)
        noise.data = self.valid_noise(X, _input)
        # ----------------------------------------------------------------------------------------- #

        for _iter in range(iteration):
            if self.early_stop_check(X=X, loss_fn=loss_fn, **kwargs):
                if 'end' in output:
                    self.output_info(_input=_input, noise=noise, mode='end', loss_fn=loss_fn, **kwargs)
                return X.detach(), _iter + 1
            if self.grad_method == 'hess' and _iter % self.hess_p == 0:
                self.hess = self.calc_hess(loss_fn, X, sigma=self.sigma,
                                           hess_b=self.hess_b, hess_lambda=self.hess_lambda)
                self.hess /= self.hess.norm(p=2)
            grad = self.calc_grad(loss_fn, X)
            if self.grad_method != 'white' and 'middle' in output:
                real_grad = self.whitebox_grad(loss_fn, X)
                prints('cos<real, est> = ', cos_sim(grad.sign(), real_grad.sign()),
                       indent=self.indent + 2)
            if self.universal:
                grad = grad.mean(dim=0)
            noise.data = (noise - pgd_alpha * torch.sign(grad)).data
            noise.data = self.projector(noise, pgd_eps, norm=self.norm).data
            X = add_noise_fn(_input=_input, noise=noise, batch=self.universal,
                             clip_min=clip_min, clip_max=clip_max)
            noise.data = self.valid_noise(X, _input)

            if 'middle' in output:
                self.output_info(_input=_input, noise=noise, mode='middle',
                                 _iter=_iter, iteration=iteration, loss_fn=loss_fn, **kwargs)
        if 'end' in output:
            self.output_info(_input=_input, noise=noise, mode='end', loss_fn=loss_fn, **kwargs)
        return X.detach(), None

    def output_info(self, _input: torch.Tensor, noise: torch.Tensor, loss_fn=None, **kwargs):
        super().output_info(**kwargs)
        with torch.no_grad():
            loss = float(loss_fn(_input + noise))
            norm = noise.norm(p=self.norm)
            prints(f'L-{self.norm} norm: {norm}    loss: {loss:.5f}', indent=self.indent)

    @staticmethod
    def projector(noise: torch.Tensor, pgd_eps: Union[float, torch.Tensor],
                  norm: Union[float, int, str] = float('inf')) -> torch.Tensor:
        if norm == float('inf'):
            noise = noise.clamp(min=-pgd_eps, max=pgd_eps)
        elif isinstance(pgd_eps, float):
            norm: torch.Tensor = noise.flatten(-3).norm(p=norm, dim=-1)
            length = pgd_eps / norm.unsqueeze(-1).unsqueeze(-1)
            noise = length * noise
        else:
            norm = noise.flatten(-2).norm(p=norm, dim=-1)
            length = pgd_eps / norm.unsqueeze(-1).unsqueeze(-1)
            noise = length * noise
        return noise.detach()

    # -------------------------- Calculate Gradient ------------------------ #
    def calc_grad(self, f, X: torch.Tensor) -> torch.Tensor:
        if self.grad_method != 'white':
            return self.blackbox_grad(f, X, query_num=self.query_num, sigma=self.sigma)
        else:
            return self.whitebox_grad(f, X)

    @staticmethod
    def whitebox_grad(f, X: torch.Tensor) -> torch.Tensor:
        X.requires_grad_()
        loss = f(X)
        grad = torch.autograd.grad(loss, X)[0]
        X.requires_grad = False
        return grad

    def blackbox_grad(self, f: Callable[[torch.Tensor], torch.Tensor], X: torch.Tensor) -> torch.Tensor:
        seq = self.gen_seq(X)
        grad = self.calc_seq(f, seq)
        return grad

    # X: (1, C, H, W)
    # return: (query_num+1, C, H, W)
    def gen_seq(self, X: torch.Tensor, query_num: int = None) -> torch.Tensor:
        query_num = query_num if query_num is not None else self.query_num
        sigma = self.sigma
        shape = list(X.shape)
        shape[0] = query_num
        if self.grad_method == 'nes':
            shape[0] = shape[0] // 2
        noise = sigma * torch.normal(mean=0.0, std=1.0, size=shape, device=X.device)

        zeros = torch.zeros_like(X)
        seq = [zeros]
        if self.grad_method == 'nes':
            seq.extend([noise, -noise])
            if query_num % 2 == 1:
                seq.append(zeros)
        elif self.grad_method == 'sgd':
            seq.append(noise)
        elif self.grad_method == 'hess':
            noise = (self.hess @ noise.view(-1, 1)).view(X.shape)
            seq.append(noise)
        elif self.grad_method == 'zoo':
            raise NotImplementedError(self.grad_method)
        else:
            print('Current method: ', self.grad_method)
            raise ValueError("Argument 'method' should be 'nes', 'sgd' or 'hess'!")
        seq = torch.cat(seq).add(X)
        return seq

    def calc_seq(self, f: Callable[[torch.Tensor], torch.Tensor], seq: torch.Tensor) -> torch.Tensor:
        X = seq[0].unsqueeze(0)
        seq = seq[1:]
        noise = seq.sub(X)
        with torch.no_grad():
            g = f(seq, reduction='none')[:, None, None, None].mul(noise).sum(dim=0)
            if self.grad_method in ['sgd', 'hess']:
                g -= f(X) * noise.sum(dim=0)
            g /= len(seq) * self.sigma * self.sigma
        return g

    @staticmethod
    def calc_hess(f: Callable[[torch.Tensor], torch.Tensor], X: torch.Tensor,
                  sigma: float, hess_b: int, hess_lambda: float = 1) -> torch.Tensor:
        length = X.numel()
        hess: torch.Tensor = torch.zeros(length, length, device=X.device)
        with torch.no_grad():
            for i in range(hess_b):
                noise = torch.normal(mean=0.0, std=1.0, size=X.shape, device=X.device)
                X1 = X + sigma * noise
                X2 = X - sigma * noise
                hess += abs(f(X1) + f(X2) - 2 * f(X)) * \
                    (noise.view(-1, 1) @ noise.view(1, -1))
            hess /= (2 * hess_b * sigma * sigma)
            hess += hess_lambda * torch.eye(length, device=X.device)
            result = hess.cholesky_inverse()
        return result
