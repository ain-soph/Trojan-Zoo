# -*- coding: utf-8 -*-

from .parser import Parser
import torch

from trojanzoo.config import Config
env = Config.env


class Parser_Main(Parser):

    name = 'main'

    @staticmethod
    def add_argument(parser):
        parser.add_argument('--device', dest='device')
        parser.add_argument('--benchmark', dest='benchmark',
                            action='store_true')
        parser.add_argument('--verbose', dest='verbose', action='store_true')

    @staticmethod
    def get_module(device: str = None, benchmark=None, verbose: bool = None):
        if verbose:
            env['verbose'] = verbose
        env['device'] = 'cpu'
        env['num_gpus'] = 0
        if device in [None, 'gpu', 'cuda'] or 'cuda' in device:
            if torch.cuda.is_available():
                # torch.set_default_tensor_type(torch.cuda.FloatTensor)
                env['device'] = 'cuda'
                env['num_gpus'] = torch.cuda.device_count()
            elif device:
                raise Exception('CUDA is not available on this device.')
        if benchmark:
            torch.backends.cudnn.benchmark = True
