#!/usr/bin/env python3

from art.estimators.classification import PyTorchClassifier  # type: ignore
from art.attacks.inference.membership_inference import MembershipInferenceBlackBox as Attack  # type: ignore
from trojanzoo.utils.data import dataset_to_list
from trojanzoo.utils.tensor import to_numpy
import trojanvision.environ
import trojanvision.datasets
import trojanvision.models
from trojanvision.utils import summary
import torch
import torch.nn as nn
import numpy as np
from sklearn import metrics
import argparse


import sys
sys.path.append('/home/rbp5354/workspace/XAutoDL/lib')

try:
    from nats_bench import create  # type: ignore
    from models import get_cell_based_tiny_net  # type: ignore
except Exception:
    pass


class MembershipInferenceAttackModel(nn.Module):
    """
        Implementation of a pytorch model for learning a membership inference attack.
        The features used are probabilities/logits or losses for the attack training data along with
        its true labels.
    """

    def __init__(self, num_classes, num_features=None):

        self.num_classes = num_classes
        if num_features:
            self.num_features = num_features
        else:
            self.num_features = num_classes

        super().__init__()

        self.features = nn.Sequential(
            nn.Linear(self.num_features, 512),
            nn.ReLU(),
            nn.Linear(512, 100),
            nn.ReLU(),
            nn.Linear(100, 64),
            nn.ReLU(),
        )

        # self.labels = nn.Sequential(
        #     nn.Linear(self.num_classes, 256), nn.ReLU(), nn.Linear(256, 64), nn.ReLU(),
        # )

        self.combine = nn.Linear(64, 1)

        self.output = nn.Sigmoid()

    def forward(self, x_1, label):
        out_x1 = self.features(x_1)
        is_member = self.combine(out_x1)
        return self.output(is_member)


class MembershipInferenceBlackBox(Attack):
    def __init__(
        self,
        classifier,
        input_type: str = "prediction",
        attack_model_type: str = "nn",
        attack_model=None,
    ):
        """
        Create a MembershipInferenceBlackBox attack instance.
        :param classifier: Target classifier.
        :param attack_model_type: the type of default attack model to train, optional. Should be one of `nn` (for neural
                                  network, default), `rf` (for random forest) or `gb` (gradient boosting). If
                                  `attack_model` is supplied, this option will be ignored.
        :param input_type: the type of input to train the attack on. Can be one of: 'prediction' or 'loss'. Default is
                           `prediction`. Predictions can be either probabilities or logits, depending on the return type
                           of the model.
        :param attack_model: The attack model to train, optional. If none is provided, a default model will be created.
        """

        super(Attack, self).__init__(estimator=classifier)
        self.input_type = input_type
        self.attack_model_type = attack_model_type
        self.attack_model = attack_model
        self._check_params()
        self.default_model = True
        if self.attack_model_type == "nn":
            self.epochs = 100
            self.batch_size = 100
            self.learning_rate = 0.0001

    def _check_params(self) -> None:
        if self.input_type not in ["prediction", "loss"]:
            raise ValueError("Illegal value for parameter `input_type`.")

        if self.attack_model_type not in ["nn", "rf", "gb"]:
            raise ValueError("Illegal value for parameter `attack_model_type`.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    trojanvision.environ.add_argument(parser)
    trojanvision.datasets.add_argument(parser)
    trojanvision.models.add_argument(parser)
    args = parser.parse_args()

    env = trojanvision.environ.create(**args.__dict__)
    dataset = trojanvision.datasets.create(**args.__dict__)
    if env['verbose']:
        summary(env=env, dataset=dataset)

    api = create('/data/rbp5354/nats/NATS-tss-v1_0-3ffb9-full', 'tss', fast_mode=True, verbose=False)

    # config = api.get_net_config(12, 'cifar10')
    # params = api.get_net_param(12, 'cifar10', None)

    # network = get_cell_based_tiny_net(config)
    # network.load_state_dict(next(iter(params.values())))

    f1_score_list: list[float] = []
    accuracy_list: list[float] = []
    recall_list: list[float] = []
    precision_list: list[float] = []
    counter = 0
    for idx in range(5000):
        info = api.get_more_info(idx, 'cifar10', hp="200")
        test_acc: float = info['test-accuracy']
        valid_acc, latency, _, _ = api.simulate_train_eval(
            idx, dataset='cifar10', hp='200')
        if test_acc > 92:
            print(f'{counter+1:<5d} {idx=:<5d} {test_acc=:<10.3f} {valid_acc=:<10.3f}')
            args.model_index = idx
            model = trojanvision.models.create(dataset=dataset, **args.__dict__)
            loss, real_acc = model._validate(indent=8)
            if real_acc <= 92:
                continue

            counter += 1
            if counter > 100:
                break
            fm_model = nn.Sequential(model._model.normalize, model._model.features,
                                     model._model.pool, model._model.flatten)
            if 'darts' in model.name:
                class Feature(nn.Module):
                    def __init__(self, features):
                        super().__init__()
                        self.features = features

                    def forward(self, x):
                        return self.features(x)[0]

                fm_model = nn.Sequential(model._model.normalize, Feature(model._model.features),
                                         model._model.pool, model._model.flatten)
            classifier = PyTorchClassifier(
                model=fm_model,
                loss=model.criterion,
                input_shape=(3, 32, 32),
                nb_classes=model._model.classifier[0].in_features,
            )
            attack_model = MembershipInferenceAttackModel(num_classes=model.num_classes,
                                                          num_features=model._model.classifier[0].in_features)
            attack = MembershipInferenceBlackBox(classifier, attack_model=attack_model)
            x_train, y_train = dataset_to_list(dataset.get_dataset('train'))
            x_train, y_train = to_numpy(torch.stack(x_train)), to_numpy(y_train)
            x_valid, y_valid = dataset_to_list(dataset.get_dataset('valid'))
            x_valid, y_valid = to_numpy(torch.stack(x_valid)), to_numpy(y_valid)

            x_train, y_train = x_train[:1000], y_train[:1000]
            x_valid, y_valid = x_valid[:1000], y_valid[:1000]

            attack.fit(x_train[100:], y_train[100:], x_valid[100:], y_valid[100:])
            result = np.concatenate((attack.infer(x_train[:100], y_train[:100]),
                                     attack.infer(x_valid[:100], y_valid[:100])))
            y_truth = np.concatenate(([1] * len(x_train[:100]), [0] * len(x_valid[:100])))
            f1_score = metrics.f1_score(result, y_truth)
            accuracy = metrics.accuracy_score(result, y_truth)
            recall = metrics.recall_score(result, y_truth)
            precision = metrics.precision_score(result, y_truth)
            f1_score_list.append(f1_score)
            accuracy_list.append(accuracy)
            recall_list.append(recall)
            precision_list.append(precision)
            print('        F1 score: '.rjust(30), f1_score)
            print('        Accuracy score: '.rjust(30), accuracy)
            print('        Recall score: '.rjust(30), recall)
            print('        Precision score: '.rjust(30), precision)
            print()
            print('    Current F1 score: '.rjust(30),
                  f'{np.mean(f1_score_list):<10.3f}({np.std(f1_score_list):<10.3f})')
            print('    Current Accuracy score: '.rjust(30),
                  f'{np.mean(accuracy_list):<10.3f}({np.std(accuracy_list):<10.3f})')
            print('    Current Recall score: '.rjust(30),
                  f'{np.mean(recall_list):<10.3f}({np.std(recall_list):<10.3f})')
            print('    Current Precision score: '.rjust(30),
                  f'{np.mean(precision_list):<10.3f}({np.std(precision_list):<10.3f})')
