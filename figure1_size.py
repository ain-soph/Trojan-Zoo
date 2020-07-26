# -*- coding: utf-8 -*-

from trojanzoo.plot import *

import numpy as np

import warnings
warnings.filterwarnings("ignore")


if __name__ == '__main__':
    fig = Figure('figure1_size')
    fig.set_axis_label('x', 'Trigger Size')
    fig.set_axis_label('y', 'Max Re-Mask Accuracy')
    fig.set_axis_lim('x', lim=[0, 50], piece=10, margin=[0, 1],
                     _format='%d')
    fig.set_axis_lim('y', lim=[0, 100], piece=5,
                     _format='%d', margin=[0.0, 0.0])
    fig.set_title(fig.name)

    color_list = [ting_color['red'], ting_color['yellow'], ting_color['green']]

    x = np.linspace(1, 7, 7)**2
    y = {
        'badnet': [67.240, 78.710, 85.060, 88.150, 90.590, 91.550, 93.230],
        'latent_backdoor': [31.950, 97.140, 99.470, 99.350, 100.000, 99.980, 94.990],
        'trojannn': [65.510, 73.170, 82.310, 96.040]
    }

    for i, (key, value) in enumerate(y.items()):
        fig.curve(x[:len(value)], value, color=color_list[i], label=key)
        fig.scatter(x[:len(value)], value, color=color_list[i])
    fig.save('./result/')