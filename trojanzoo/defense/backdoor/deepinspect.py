# -*- coding: utf-8 -*-

from ..defense_backdoor import Defense_Backdoor

from trojanzoo.utils import to_list, normalize_mad
from trojanzoo.utils.output import prints, ansi, output_iter

import torch
import torch.nn as nn
import torch.optim as optim

from trojanzoo.utils import Config
env = Config.env


class DeepInspect(Defense_Backdoor):

    name: str = 'deepinspect'

    def __init__(self, sample_num: int = 500, epoch: int = 10, 
                gamma_1: float = 1.0, gamma_2: float = 0.0, **kwargs):
        super().__init__(**kwargs)

        data_shape = [self.dataset.n_channel]
        data_shape.extend(self.dataset.n_dim)
        self.data_shape: List[int] = data_shape

        self.sample_num = sample_num
        self.epoch: int = epoch

        self.gamma_1 = gamma_1
        self.gamma_2 = gamma_2

    def detect(self, **kwargs):
        super().detect(**kwargs)
        mark_list, mask_list, loss_list = self.get_potential_triggers()
        mask_norms = mask_list.flatten(start_dim=1).norm(p=1, dim=1)
        print('mask_norms: ', normalize_mad(mask_norms))
        print('loss: ', normalize_mad(loss_list))

    def get_potential_triggers(self) -> (torch.Tensor, torch.Tensor, torch.Tensor):
        mark_list, mask_list, loss_list = [], [], []
        # todo: parallel to avoid for loop
        for label in range(self.model.num_classes):
            # print('label: ', label)
            print('Class: ', output_iter(label, self.model.num_classes))
            mark, mask, loss = self.remask(
                label)
            mark_list.append(mark)
            mask_list.append(mask)
            loss_list.append(loss)
        mark_list = torch.stack(mark_list)
        mask_list = torch.stack(mask_list)
        loss_list = torch.as_tensor(loss_list)

        return mark_list, mask_list, loss_list

    def remask(self, label: int):
        nc_epoch = self.nc_epoch
        # no bound
        atanh_mark = torch.randn(self.data_shape, device=env['device'])
        atanh_mark.requires_grad_()
        atanh_mask = torch.randn(self.data_shape[1:], device=env['device'])
        atanh_mask.requires_grad_()
        mask = Uname.tanh_func(atanh_mask)    # (h, w)
        mark = Uname.tanh_func(atanh_mark)    # (c, h, w)

        optimizer = optim.Adam(
            [atanh_mark, atanh_mask], lr=0.1, betas=(0.5, 0.9))
        optimizer.zero_grad()

        cost = self.init_cost
        cost_set_counter = 0
        cost_up_counter = 0
        cost_down_counter = 0
        cost_up_flag = False
        cost_down_flag = False

        # best optimization results
        norm_best = float('inf')
        mask_best = None
        mark_best = None
        entropy_best = None

        # counter for early stop
        early_stop_counter = 0
        early_stop_norm_best = norm_best

        losses = AverageMeter('Loss', ':.4e')
        entropy = AverageMeter('Entropy', ':.4e')
        norm = AverageMeter('Norm', ':.4e')
        acc = AverageMeter('Acc', ':6.2f')

        for _epoch in range(nc_epoch):
            losses.reset()
            entropy.reset()
            norm.reset()
            acc.reset()
            epoch_start = time.perf_counter()
            for data in tqdm(self.dataset.loader['train']):
                _input, _label = self.model.get_data(data)
                batch_size = _label.size(0)
                X = _input + mask * (mark - _input)
                Y = label * torch.ones_like(_label, dtype=torch.long)
                _output = self.model(X)

                batch_acc = Y.eq(_output.argmax(1)).float().mean()
                batch_entropy = self.model.criterion(_output, Y)
                batch_norm = mask.norm(p=1)
                batch_loss = batch_entropy + cost * batch_norm

                acc.update(batch_acc.item(), batch_size)
                entropy.update(batch_entropy.item(), batch_size)
                norm.update(batch_norm.item(), batch_size)
                losses.update(batch_loss.item(), batch_size)

                batch_loss.backward()
                optimizer.step()
                optimizer.zero_grad()

                mask = Uname.tanh_func(atanh_mask)    # (h, w)
                mark = Uname.tanh_func(atanh_mark)    # (c, h, w)
            epoch_time = str(datetime.timedelta(seconds=int(
                time.perf_counter() - epoch_start)))
            pre_str = '{blue_light}Epoch: {0}{reset}'.format(
                output_iter(_epoch + 1, nc_epoch), **ansi).ljust(64)
            _str = ' '.join([
                'Loss: {:.4f},'.format(losses.avg).ljust(20),
                'Acc: {:.2f}, '.format(acc.avg).ljust(20),
                'Norm: {:.4f},'.format(norm.avg).ljust(20),
                'Entropy: {:.4f},'.format(entropy.avg).ljust(20),
                'Time: {},'.format(epoch_time).ljust(20),
            ])
            prints(pre_str, _str, prefix='{upline}{clear_line}'.format(**ansi), indent=4)

            # check to save best mask or not
            if acc.avg >= self.attack_succ_threshold and norm.avg < norm_best:
                mask_best = mask.detach()
                mark_best = mark.detach()
                norm_best = norm.avg
                entropy_best = entropy.avg

            # check early stop
            if self.early_stop:
                # only terminate if a valid attack has been found
                if norm_best < float('inf'):
                    if norm_best >= self.early_stop_threshold * early_stop_norm_best:
                        early_stop_counter += 1
                    else:
                        early_stop_counter = 0
                early_stop_norm_best = min(norm_best, early_stop_norm_best)

                if cost_down_flag and cost_up_flag and early_stop_counter >= self.early_stop_patience:
                    print('early stop')
                    break

            # check cost modification
            if cost == 0 and acc.avg >= self.attack_succ_threshold:
                cost_set_counter += 1
                if cost_set_counter >= self.patience:
                    cost = self.init_cost
                    cost_up_counter = 0
                    cost_down_counter = 0
                    cost_up_flag = False
                    cost_down_flag = False
                    print('initialize cost to %.2f' % cost)
            else:
                cost_set_counter = 0

            if acc.avg >= self.attack_succ_threshold:
                cost_up_counter += 1
                cost_down_counter = 0
            else:
                cost_up_counter = 0
                cost_down_counter += 1

            if cost_up_counter >= self.patience:
                cost_up_counter = 0
                prints('up cost from %.4f to %.4f' %
                       (cost, cost * self.cost_multiplier_up), indent=4)
                cost *= self.cost_multiplier_up
                cost_up_flag = True
            elif cost_down_counter >= self.patience:
                cost_down_counter = 0
                prints('down cost from %.4f to %.4f' %
                       (cost, cost / self.cost_multiplier_down), indent=4)
                cost /= self.cost_multiplier_down
                cost_down_flag = True
            if mask_best is None:
                mask_best = Uname.tanh_func(atanh_mask).detach()
                mark_best = Uname.tanh_func(atanh_mark).detach()
                norm_best = norm.avg
                entropy_best = entropy.avg
        atanh_mark.requires_grad = False
        atanh_mask.requires_grad = False

        self.attack.mark.mark = mark_best
        self.attack.mark.alpha_mark = mask_best
        self.attack.mark.mask = torch.ones_like(mark_best, dtype=torch.bool)
        self.attack.validate_func()
        return mark_best, mask_best, entropy_best