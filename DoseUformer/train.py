# -*- encoding: utf-8 -*-
import os
import sys

import torch
import yaml
from monai.utils import set_determinism

# from attrdict import AttrDict
if os.path.abspath('..') not in sys.path:
    sys.path.insert(0, os.path.abspath('..'))

from DataLoader.dataloader_DoseUformer import get_loader
from NetworkTrainer.network_trainer import NetworkTrainer
from model import SwinTU3D
from online_evaluation import online_evaluation
from loss import Loss


def load_config(path, config_name):
    with open(os.path.join(path, config_name)) as file:
        config = yaml.safe_load(file)
        # cfg = AttrDict(config)
        # print(cfg.project_name)

    return config


def main(configs):
    print('This script modified from Shuolin Liu !')

    # set a fixed seed
    set_determinism(configs['training']['seed'])

    #  Start training
    trainer = NetworkTrainer(name=configs['project_name'])
    trainer.setting.project_name = configs['project_name']
    trainer.setting.output_dir = configs['output_dir']

    # setting.network is an object
    trainer.setting.network = SwinTU3D(patch_size=configs['model']['patch_size'],
                                       depths=configs['model']['depths'],
                                       norm_layer=torch.nn.LayerNorm)

    trainer.setting.max_iter = configs['training']['iterations']

    trainer.setting.train_loader = get_loader(
        batch_size=configs['training']['loader']['batch_size'],
        num_samples_per_epoch=configs['training']['loader']['batch_size'] * 500,  # an epoch
        phase=configs['training']['loader']['phase'],
        num_works=4
    )

    trainer.setting.eps_train_loss = 0.01
    trainer.setting.lr_scheduler_update_on_iter = True
    trainer.setting.loss_function = Loss()
    trainer.setting.online_evaluation_function_val = online_evaluation

    # filter the relative position bias table params
    relative_params = list(filter(
        lambda kv: 'relative_position_bias_table' in kv[0], trainer.setting.network.named_parameters()))
    base_params = list(filter(
        lambda kv: 'relative_position_bias_table' not in kv[0], trainer.setting.network.named_parameters()))

    trainer.setting.optimizer = torch.optim.AdamW([
        {'params': [param[1] for param in relative_params], 'weight_decay': 0.},
        {'params': [param[1] for param in base_params], }],
        lr=configs['training']['optimizer']['lr'], weight_decay=configs['training']['optimizer']['weight_decay'],
        betas=(0.9, 0.999), eps=1e-08, amsgrad=True)

    trainer.setting.lr_scheduler_type = configs['training']['lr_scheduler']['type']  # cosine
    trainer.setting.lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(trainer.setting.optimizer,
                                                                              T_max=configs['training']['iterations'],
                                                                              eta_min=1e-7,
                                                                              last_epoch=-1)

    # trainer.set_optimizer(optimizer_type='Adam',
    #                       cfgs={
    #                           'lr': 3e-4,
    #                           'weight_decay': 1e-4
    #                       }
    #                       )
    #
    # trainer.set_lr_scheduler(lr_scheduler_type='cosine',
    #                          cfgs={
    #                              'T_max': args.max_iter,
    #                              'eta_min': 1e-7,
    #                              'last_epoch': -1
    #                          }
    #                          )

    if not os.path.exists(trainer.setting.output_dir):
        os.mkdir(trainer.setting.output_dir)
    trainer.set_GPU_device(configs['list_GPU_ids'])

    # added by Chenchen Hu
    if configs['pre_trained']['status'] and os.path.exists(configs['pre_trained']['model_path']):
        trainer.init_trainer(ckpt_file=configs['pre_trained']['model_path'],
                             list_GPU_ids=configs['list_GPU_ids'],
                             only_network=False)

    trainer.run()


if __name__ == '__main__':
    CONFIG_PATH = '../Configs'
    cfgs = load_config(CONFIG_PATH, config_name='default_config.yaml')
    main(cfgs)
