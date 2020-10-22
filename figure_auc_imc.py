# -*- coding: utf-8 -*-

from trojanzoo.plot import *

import numpy as np
import pandas as pd
import warnings
import os
from sklearn.metrics import roc_curve, auc

warnings.filterwarnings("ignore")


def min_max_scaling(df, column_names=None):
    # copy the dataframe
    df_norm = df.copy()
    # apply min-max scaling
    local_colnames = column_names if column_names is not None else df_norm.columns
    for column in local_colnames:
        df_norm[column] = (df_norm[column] - df_norm[column].min()) / (df_norm[column].max() - df_norm[column].min())

    return df_norm


def auc_graph(name, attack):

    fig = Figure(name=name)
    ax = fig.ax
    fig.set_axis_label('x', 'Attack Success Rate')
    fig.set_axis_label('y', 'Clean Accuracy Drop')
    fig.set_axis_lim('x', lim=[0, 1.0], piece=5, margin=[0.0, 0.05],
                     _format='%.1f')
    fig.set_axis_lim('y', lim=[0, 1.0], piece=5, margin=[0.0, 0.05],
                     _format='%.1f')

    color_list = [ting_color['red_carrot'], ting_color['red_deep'], ting_color['yellow'],
                  ting_color['blue'], ting_color['blue_light'], ting_color['pink'],
                  ting_color['green'], color['brown']['brown'], color['green']['army']]
    mark_list = ['D', ',', 'o', 'v', 's', 'p', '*', 'h', 'D']

    local_data = data[data["Model"] == attack]
    x = np.array([i for i in local_data["Attack ACC"]])
    y = np.array([i for i in local_data["Difference"]])
    x = fig.normalize(x)
    y = fig.normalize(y)

    x_grid = np.linspace(0.0, 0.97, 970)
    # y_grid = fig.poly_fit(x, y, x_grid, degree=2)
    y_grid = fig.exp_fit(x, y, x_grid, increase=True, epsilon=1e-4, degree=2)

    x_line = np.linspace(0.97, 1.0, 30)
    y_line = fig.poly_fit(x[-2:], y[-2:], x_line, degree=1)

    x_grid = np.concatenate((x_grid, x_line))
    y_grid = np.concatenate((y_grid, y_line))

    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=30)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=20)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=20)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=20)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=20)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=10)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=10)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=10)[60:80]
    y_grid[960:980] = fig.avg_smooth(y_grid[900:1000], window=10)[60:80]

    local_auc = auc(x_grid, y_grid)
    fig.set_title(f'{name}     AUC {local_auc:.3f}')

    x1 = np.linspace(0, 1, 100)
    y1 = x1

    i = 0

    y_grid = np.array([max(y, 0) for y in y_grid])
    y_grid = fig.normalize(y_grid)
    fig.curve(x=x_grid, y=y_grid, color=color_list[i])
    fig.scatter(x=x, y=y, color=color_list[i], marker=mark_list[i])
    fig.curve(x=x1, y=y1, color=ting_color["grey"], linewidth=5, linestyle='--')

    fig.save("./result/auc/")


if __name__ == "__main__":
    data = pd.read_excel("./result/auc/auc_data_selected.xlsx")

    auc_graph("IMC", "imc")