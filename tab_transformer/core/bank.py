import os
from typing import List
from logging import Logger
from yacs.config import CfgNode

import pandas as pd

from sklearn.preprocessing import RobustScaler, MinMaxScaler

import torch
from torch.utils.data import Dataset

from core.base import BaseMachine


class BankDataset(Dataset):
    def __init__(
            self,
            file: pd.DataFrame,
            cate_features: List[str],
            cont_features: List[str]
    ):
        self.file = file
        self.cate_features = cate_features
        self.cont_features = cont_features

    def __len__(self):
        return len(self.file)

    def __getitem__(self, idx):
        if torch.is_tensor(idx):
            idx = idx.tolist()

        categorical_features = self.file[self.cate_features].iloc[idx, :]
        continuous_features = self.file[self.cont_features].iloc[idx, :]
        labels = self.file[['y']].iloc[idx, :]

        sample = {
            'cate_features': categorical_features,
            'cont_features': continuous_features,
            'labels': labels
        }

        return sample


class BankPreprocessor(BaseMachine):
    def __init__(
            self,
            cfg: CfgNode,
            logger: Logger
    ):
        self.cfg = cfg
        self.logger = logger

    def info(self):
        msg = 'dataset url: https://archive.ics.uci.edu/ml/datasets/bank+marketing'
        return msg

    def load_data(self):
        self.logger.info('load_data')

        data = pd.read_csv(
            os.path.join(self.cfg.ADDRESS.DATA, 'bank/bank-full.csv'),
            sep=';', header=0)

        return data

    def preprocess(self):
        self.logger.info('preprocess')

        data = self.load_data()

        cont_features = ['age', 'balance', 'day', 'duration', 'campaign', 'pdays', 'previous']
        cate_features = list(set(data.columns).difference(set(cont_features)))
        cate_features.remove('y')

        map_records = {}

        # 1. categorical features mapping
        for f in cate_features:
            if f == 'month':
                month_list = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'oct', 'nov', 'dec']
                map_dict = {m: i for i, m in enumerate(month_list)}
                data[f] = data[f].map(map_dict)
            else:
                all_class = sorted(data[f].unique().tolist())
                map_dict = {prev: new for new, prev in enumerate(all_class)}
                data[f] = data[f].map(map_dict)

            map_records[f] = map_dict

        self.logger.info('mapped categorical features to integer index')

        # 2. scale continuous features
        scaler = RobustScaler()
        scaled = scaler.fit_transform(data[cont_features])

        scaler = MinMaxScaler()
        scaled = scaler.fit_transform(scaled)

        data = data.drop(cont_features, axis=1)
        data = pd.concat([data, pd.DataFrame(scaled, columns=cont_features)], axis=1)

        self.logger.info('scaled continuous features')

        # 3. label mapping
        data['y'] = data['y'].map({'yes': 1, 'no': 0})

        data = data[cate_features + cont_features + ['y']]

        additional_info = [map_records, cate_features, cont_features]

        return data, additional_info

    def get_dataset(self, train_ratio: float = 0.7, val_ratio: float = 0.2):
        self.logger.info('get dataset')

        data, additional_info = self.preprocess()

        data = data.sample(frac=1.0)

        points = [
            int(data.shape[0] * train_ratio),
            int(data.shape[0] * (train_ratio + val_ratio))
        ]

        dataset = {
            'train': data.iloc[0: points[0]].reset_index(drop=True),
            'val': data.iloc[points[0]: points[1]].reset_index(drop=True),
            'test': data.iloc[points[1]:].reset_index(drop=True)
        }

        self.logger.info(
            f"""
            preprocessing done
            - cate feature: {additional_info[1]}
            - cont feature: {additional_info[2]}'
            """
        )

        train_dataset = BankDataset(dataset['train'], additional_info[1], additional_info[2])
        val_dataset = BankDataset(dataset['val'], additional_info[1], additional_info[2])
        test_dataset = BankDataset(dataset['test'], additional_info[1], additional_info[2])

        return train_dataset, val_dataset, test_dataset, additional_info[0]
