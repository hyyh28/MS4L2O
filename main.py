import os
import numpy as np
import configargparse
from timeit import default_timer as timer

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

import random
import utils
import optimizers

import time

from optimizees import OPTIMIZEE_DICT


# Argument Parsing
parser = configargparse.get_arg_parser(description='Configurations for L2O experiements')

parser.add('-c', '--config', is_config_file=True, help='Config file path.')

# Optimizer options
parser.add('--optimizer', type=str, metavar='STR',
           help='What optimizer to use for the current experiment.')
parser.add('--grad-method', type=str, default='subgrad', metavar='STR',
           help='How to calculate gradients with respect to the objective func.')
parser.add('--cpu', action='store_true',
           help='Force to use CPU instead of GPU even if CUDA compatible GPU '
                'devices are available.')
parser.add('--device', type=str, default = None, help='cuda:0')
parser.add('--test', action='store_true', help='Run in test mode.')
parser.add('--state-scale', type=float, default=0.01, metavar='FLOAT',
           help='scale of the lstm states.')

# Optimizee general options
parser.add('--optimizee-type',
           choices=['QuadraticUnconstrained', 'LASSO', 'LogisticL1', 'LogisticL1CIFAR10'],
           help='Type of optimizees to be trained on.')
parser.add('--input-dim', type=int, metavar='INT',
           help='Dimension of the input (optimization variable).')
parser.add('--output-dim', type=int, metavar='INT',
           help='Dimension of the output (labels used to calculate loss).')
parser.add('--rho', type=float, default=0.1, metavar='FLOAT',
           help='Parameter for reg. term in the objective function.')
parser.add('--fixed-dict', action='store_true',
           help='Use a fixed dictionary for the optimizees')
parser.add('--sparsity', type=int, default=5, metavar='INT',
           help='Sparisty of the input variable.')
parser.add('--save-to-mat', action='store_true',
           help='save optmizees to mat file.')
parser.add('--optimizee-dir', type=str, metavar='STR',
           help='dir of optimizees.')
parser.add('--load-mat', action='store_true',
           help='load optmizees from mat file.')
parser.add('--save-sol', action='store_true',
           help='save solutions of optimizees.')
parser.add('--load-sol', action='store_true',
           help='save solutions of optimizees.')

# Model parameters
parser.add('--lstm-layers', type=int, default=2, metavar='INT',
           help='Number of layers of the neural network.')
parser.add('--lstm-hidden-size', type=int, default=256, metavar='INT',
           help='Number of layers of the neural network.')

parser.add('--rnnprop-beta1', type=float, default=0.95, metavar='FLOAT',
           help='Adam hyperparameter for RNNprop.')
parser.add('--rnnprop-beta2', type=float, default=0.95, metavar='FLOAT',
           help='Adam hyperparameter for RNNprop.')

parser.add('--p-use', action='store_true',
           help='Use the pre-conditioners generated by LSTM.')
parser.add('--p-scale', type=float, default=1.0, metavar='FLOAT',
           help='Scaling factor before the pre-conditioner.')
parser.add('--p-scale-learned', action='store_true',
           help='Learn scaling factor before the pre-conditioner '
                'as a learnable parameter')
parser.add('--p-norm', type=str, choices=['eye', 'sigmoid', 'exp', 'softplus'],
           help='Normalization applied to the pre-conditioners before they are '
                'applied to the gradients.')

parser.add('--b-use', action='store_true',
           help='Use the bias terms generated by LSTM.')
parser.add('--b-scale', type=float, default=1.0, metavar='FLOAT',
           help='Scaling factor before the bias term')
parser.add('--b-scale-learned', action='store_true',
           help='Learn scaling factor before the bias term '
                'as a learnable parameter')
parser.add('--b-norm', type=str, choices=['eye', 'sigmoid', 'exp', 'softplus'],
           help='Normalization applied to the bias terms before they are '
                'applied.')

parser.add('--b1-use', action='store_true',
           help='Use the bias terms generated by LSTM.')
parser.add('--b1-scale', type=float, default=1e-2, metavar='FLOAT',
           help='Scaling factor before the bias term')
parser.add('--b1-scale-learned', action='store_true',
           help='Learn scaling factor before the bias term '
                'as a learnable parameter')
parser.add('--b1-norm', type=str, choices=['eye', 'sigmoid', 'exp', 'softplus'],
           help='Normalization applied to the bias terms before they are '
                'applied.')

parser.add('--b2-use', action='store_true',
           help='Use the bias terms generated by LSTM.')
parser.add('--b2-scale', type=float, default=1e-2, metavar='FLOAT',
           help='Scaling factor before the bias term')
parser.add('--b2-scale-learned', action='store_true',
           help='Learn scaling factor before the bias term '
                'as a learnable parameter')
parser.add('--b2-norm', type=str, choices=['eye', 'sigmoid', 'exp', 'softplus'],
           help='Normalization applied to the bias terms before they are '
                'applied.')

parser.add('--a-use', action='store_true',
           help='Use the momentum coefficients generated by LSTM.')
parser.add('--a-scale', type=float, default=1.0, metavar='FLOAT',
           help='Scaling factor before the momentum coefficients.')
parser.add('--a-scale-learned', action='store_true',
           help='Learn scaling factor before the momentum coefficients '
                'as a learnable parameter')
parser.add('--a-norm', type=str, choices=['eye', 'sigmoid', 'exp', 'softplus'],
           help='Normalization applied to the momentum coefficients before they '
                'are applied.')

# Parameters of classic optimizers
parser.add('--step-size', type=float, default=None, metavar='FLOAT',
           help='Step size for the classic optimizers')
parser.add('--momentum1', type=float, default=None, metavar='FLOAT',
           help='decay factor of 1st order momentum (adam)')
parser.add('--momentum2', type=float, default=None, metavar='FLOAT',
           help='decay factor of 2nd order momentum (adam)')
parser.add('--eps', type=float, default=None, metavar='FLOAT',
           help='epsilon on adam optimizer')
parser.add('--hyper-step', type=float, default=None, metavar='FLOAT',
           help='Hyper step size of AdamHD')

# Data parameters
parser.add('--seed', type=int, default=118, metavar='INT',
           help='Random seed for reproducibility')

# Training parameters
# parser.add('--objective', type=str, default='GT', metavar='{OBJECTIVE,L2,L1,GT}',
#            help='Objective used for the training')
parser.add('--save-dir', type=str, default='temp', metavar='STR',
           help='Saving directory for saved checkpoints and logs')
parser.add('--ckpt-path', type=str, default=None, metavar='STR',
           help='Path to the checkpoint to be loaded.')
parser.add('--loss-save-path', type=str, default=None, metavar='STR',
           help='Path to save the testing losses.')

# Training
parser.add('--global-training-steps', type=int, default=1000,
           help='Total number of training steps considered.')
parser.add('--optimizer-training-steps', type=int, default=100,
           help='Total number of batches of optimizees generated for training.')
parser.add('--unroll-length', type=int, default=1000,
           help='Total number of training steps considered.')

parser.add('--train-batch-size', type=int, default=128, metavar='N',
           help='Batch size for training')
parser.add('--val-batch-size', type=int, default=256, metavar='N',
           help='Batch size for validation')
parser.add('--test-batch-size', type=int, default=None, metavar='N',
           help='Batch size for testing')
parser.add('--val-size', type=int, default=2048, metavar='N',
           help='Number of validation samples')
parser.add('--test-size', type=int, default=2048, metavar='N',
           help='Number of testing samples')

parser.add('--print-freq', type=int, default=200,
           help='Frequency of printing training information')
parser.add('--val-freq', type=int, default=200,
           help='Frequency of validation')
parser.add('--val-length', type=int, default=100,
           help='Total length of optimization during validation')
parser.add('--test-length', type=int, default=100,
           help='Total length of optimization during testing')

parser.add('--init-lr', type=float, default=0.1, metavar='FLOAT',
           help='Initial learning rate')
parser.add('--scheduler', type=str, default='constant', metavar='STR',
           help='Learning rate scheduler.')
parser.add('--best-wait', type=int, default=5, metavar='N',
           help='Wait time for better validation performance')

opts, _ = parser.parse_known_args()

# Save directory
opts.save_dir = os.path.join('results', opts.save_dir)
if not os.path.isdir(opts.save_dir):
    os.makedirs(opts.save_dir)
# Logging file
logger_file = os.path.join(opts.save_dir, 'train.log')
opts.logger = utils.setup_logger(logger_file)
opts.logger('Checkpoints will be saved to directory `{}`'.format(opts.save_dir))
opts.logger('Log file for training will be saved to file `{}`'.format(logger_file))

# Use cuda if it is available
if opts.cpu:
    opts.device = 'cpu'
elif opts.device is None:
    if torch.cuda.is_available():
        opts.device = 'cuda'
    else:
        opts.device = 'cpu'
        opts.logger('WARNING: No CUDA available. Run on CPU instead.')
opts.logger('Using device: {}'.format(opts.device)) # Output the type of device used
opts.dtype  = torch.float
# opts.logger('Using tau: {}'.format(opts.tau)) # Output the tau used in current exp

# Set random seed for reproducibility
torch.manual_seed(opts.seed)
random.seed(opts.seed + 7)
np.random.seed(opts.seed + 42)

# -----------------------------------------------------------------------
#              Create data for training and validation
# -----------------------------------------------------------------------
# train_seen_loader, val_seen_loader, test_seen_loader, A, W, W_gram, G = create_sc_data(opts)
# A_TEN = torch.from_numpy(A).to(device=opts.device, dtype=opts.dtype)

if opts.fixed_dict:
    W = torch.randn(opts.input_dim, opts.output_dim).to(opts.device)
else:
    W = None

# Keyword artuments for the optimizers
optimizer_kwargs = {
    'p_use': opts.p_use,
    'p_scale': opts.p_scale,
    'p_scale_learned': opts.p_scale_learned,
    'p_norm': opts.p_norm,

    'b_use': opts.b_use,
    'b_scale': opts.b_scale,
    'b_scale_learned': opts.b_scale_learned,
    'b_norm': opts.b_norm,

    'b1_use': opts.b1_use,
    'b1_scale': opts.b1_scale,
    'b1_scale_learned': opts.b1_scale_learned,
    'b1_norm': opts.b1_norm,

    'b2_use': opts.b2_use,
    'b2_scale': opts.b2_scale,
    'b2_scale_learned': opts.b2_scale_learned,
    'b2_norm': opts.b2_norm,

    'a_use': opts.a_use,
    'a_scale': opts.a_scale,
    'a_scale_learned': opts.a_scale_learned,
    'a_norm': opts.a_norm,
}

reset_state_kwargs = {
    'state_scale':opts.state_scale,
    # 'step_size': opts.step_size,
    'momentum1': opts.momentum1,
    'momentum2': opts.momentum2,
    'eps': opts.eps,
    'hyper_step': opts.hyper_step,
}

# Keyword arguments for the optimizees
optimizee_kwargs = {
    'input_dim': opts.input_dim,
    'output_dim': opts.output_dim,
    'rho': opts.rho,
    's': opts.sparsity,
    'device': opts.device,
}

if opts.optimizer == 'ProximalGradientDescent':
    optimizer = optimizers.ProximalGradientDescent()
elif opts.optimizer == 'ProximalGradientDescentMomentum':
    optimizer = optimizers.ProximalGradientDescentMomentum()
elif opts.optimizer == 'SubGradientDescent':
    optimizer = optimizers.SubGradientDescent()
elif opts.optimizer == 'Adam':
    optimizer = optimizers.Adam()
elif opts.optimizer == 'AdamHD':
    optimizer = optimizers.AdamHD()
elif opts.optimizer == 'Shampoo':
    optimizer = optimizers.Shampoo()
elif opts.optimizer == 'CoordMathLSTM':
    optimizer = optimizers.CoordMathLSTM(
        input_size  = 2,
        output_size = 1,
        hidden_size = opts.lstm_hidden_size,
        layers = opts.lstm_layers,
        **optimizer_kwargs
    )
elif opts.optimizer == 'RNNprop':
    optimizer = optimizers.RNNprop(
        input_size  = 2,
        output_size = 1,
        hidden_size = opts.lstm_hidden_size,
        layers = opts.lstm_layers,
        beta1 = opts.rnnprop_beta1,
        beta2 = opts.rnnprop_beta2,
        **optimizer_kwargs
    )
elif opts.optimizer == 'CoordBlackboxLSTM':
    optimizer = optimizers.CoordBlackboxLSTM(
        input_size  = 2,
        output_size = 1,
        hidden_size = opts.lstm_hidden_size,
        layers = opts.lstm_layers,
        **optimizer_kwargs
    )
else:
    raise ValueError(f'Invalid optimizer name {opts.optimizer}')

if not opts.test:
    config_path = os.path.join(opts.save_dir, 'config.yaml')
    parser.write_config_file(opts, [config_path])

    assert isinstance(optimizer, nn.Module), 'Only PyTorch Modules need training.'

    optimizer = optimizer.to(device=opts.device, dtype=opts.dtype)
    meta_optimizer = optim.Adam(optimizer.parameters(), lr=opts.init_lr)
    if opts.scheduler == 'cosine':
        meta_scheduler = optim.lr_scheduler.CosineAnnealingLR(
            meta_optimizer, T_max=opts.global_training_steps, eta_min=1e-5)
    elif opts.scheduler == 'constant':
        meta_scheduler = optim.lr_scheduler.ConstantLR(
            meta_optimizer, factor=1.0, total_iters=opts.global_training_steps)
    else:
        raise NotImplementedError

    training_losses = []  # initialize the array storing training loss function
    best_validation_mean = 99999999999999
    best_validation_final = 99999999999999

    for i in range(opts.global_training_steps):
        if (i+1) % opts.print_freq == 0:
            verbose = True
            opts.logger('\n=============> global training steps: {}'.format(i))
        else:
            verbose = False
        optimizer.train()

        optimizees = OPTIMIZEE_DICT[opts.optimizee_type](
            opts.train_batch_size, W, **optimizee_kwargs
        )
        optimizer.reset_state(optimizees, opts.step_size, **reset_state_kwargs)

        num_roll_segs = opts.optimizer_training_steps // opts.unroll_length
        for num_roll in range(num_roll_segs):
            global_loss = 0.0
            start = timer()

            for j in range(opts.unroll_length):
                optimizees = optimizer(optimizees, opts.grad_method)
                loss = optimizees.objective(compute_grad = True)
                global_loss += loss / opts.unroll_length

            # Train for one step the meta optimizer.
            meta_optimizer.zero_grad()
            global_loss.backward() ## retain_graph=True
            meta_optimizer.step()
            training_losses.append(global_loss.detach().cpu().item())

            # Clean up the current unrolling segments, including:
            # - Detach the current hidden and cell states.
            # - Clear the `hist` list of the optimizers to release memory
            optimizer.detach_state()
            optimizees.detach_vars()

            # optimizer.clear_hist()

            time = timer() - start
            if verbose:
                opts.logger(
                    '--> time consuming [{:.4f}s] optimizer train steps :  [{}] '
                    '| Global_Loss = [{:.4f}]'.format(
                        time,
                        (num_roll + 1) * opts.unroll_length,
                        training_losses[-1]
                    )
                )

        if (i+1) % opts.val_freq == 0:
            optimizer.eval()
            optimizees = OPTIMIZEE_DICT[opts.optimizee_type](
                opts.val_size, W, seed = opts.seed + 77, **optimizee_kwargs
            )
            optimizer.reset_state(optimizees, opts.step_size, **reset_state_kwargs)
            validation_losses = []
            for j in range(opts.val_length):
                # Fixed data samples for validation
                optimizees = optimizer(optimizees, opts.grad_method)
                loss = optimizees.objective()
                validation_losses.append(loss.detach().cpu().item())

            # if (validation_losses[-1] < best_validation_final and
            #         np.mean(validation_losses) < best_validation_mean) :
            if np.mean(validation_losses) < best_validation_mean:
                best_validation_final = validation_losses[-1]
                best_validation_mean = np.mean(validation_losses)
                opts.logger(
                    '\n\n===> best of final LOSS[{}]: =  {}, '
                    'best_mean_loss ={}'.format(
                        opts.val_length,
                        best_validation_final,
                        best_validation_mean
                    )
                )

                checkpoint_name = optimizer.name() + '.pth'
                save_path = os.path.join(opts.save_dir, checkpoint_name)
                torch.save(optimizer.state_dict(), save_path)
                opts.logger('Saved the optimizer to file: ' + save_path)

else:
    if isinstance(optimizer, nn.Module):
        checkpoint_name = optimizer.name() + '.pth'
        if not opts.ckpt_path:
            opts.ckpt_path = os.path.join(opts.save_dir, checkpoint_name)
        optimizer.load_state_dict(torch.load(opts.ckpt_path, map_location='cpu'))
        opts.logger(f'Trained weight loaded from {opts.ckpt_path}')
        optimizer.to(device=opts.device, dtype=opts.dtype).eval()
        optimizer.eval()

    if not opts.test_batch_size:
        opts.test_batch_size = opts.test_size

    num_test_batches = opts.test_size // opts.test_batch_size
    test_losses = [0.0] * (opts.test_length + 1)
    if opts.save_sol:
        test_losses_batch = np.zeros((opts.test_length + 1, opts.test_batch_size))

    time_start = time.time()
    time_opt = 0

    for i in range(num_test_batches):
        seed = opts.seed + 777 * (i+1)
        
        optimizees = OPTIMIZEE_DICT[opts.optimizee_type](
            opts.test_batch_size, W, seed=seed, **optimizee_kwargs
        )

        if opts.load_mat:
            optimizees.load_from_file(opts.optimizee_dir + '/' + str(i) + '.mat')
            opts.logger('Batch {} optimizee loaded.'.format(i))
            
        if opts.load_sol:
            optimizees.load_sol(opts.optimizee_dir + '/sol_' + str(i) + '.mat')
            opts.logger('Batch {} optimal objective loaded.'.format(i))
        
        if opts.save_to_mat:
            if not os.path.exists(opts.optimizee_dir):
                os.makedirs(opts.optimizee_dir, exist_ok=True)
            optimizees.save_to_file(opts.optimizee_dir + '/' + str(i) + '.mat')

        optimizer.reset_state(optimizees, opts.step_size, **reset_state_kwargs)
        if not opts.load_sol:
            test_losses[0] += optimizees.objective().detach().cpu().item()
        else:
            test_losses[0] += optimizees.objective_shift().detach().cpu().item()

        if opts.save_sol:
            test_losses_batch[0] = optimizees.objective_batch().cpu().numpy()

        for j in range(opts.test_length):

            time_inner_start = time.time()
            optimizees = optimizer(optimizees, opts.grad_method)
            optimizer.detach_state()
            time_inner_end = time.time()
            time_opt += (time_inner_end - time_inner_start)

            if not opts.load_sol:
                loss = optimizees.objective()
            else:
                loss = optimizees.objective_shift()

            test_losses[j+1] += loss.detach().cpu().item()
            if opts.save_sol:
                test_losses_batch[j+1] = optimizees.objective_batch().cpu().numpy()
                
        opts.logger('Batch {} completed.'.format(i))
        
        if opts.save_sol:
            if not os.path.exists(opts.optimizee_dir):
                os.makedirs(opts.optimizee_dir, exist_ok=True)
            obj_star = np.min(test_losses_batch, axis = 0)
            optimizees.save_sol(obj_star, opts.optimizee_dir + '/sol_' + str(i) + '.mat')
            opts.logger('Batch {} optimal objective saved.'.format(i))

    time_end = time.time()
    test_losses = [loss / num_test_batches for loss in test_losses]

    # output the epoch results to the terminal
    opts.logger('Testing losses:')
    for ii,t_loss in enumerate(test_losses):
        opts.logger('{}, {}'.format(ii, t_loss))
    if not opts.loss_save_path:
        opts.loss_save_path = os.path.join(opts.save_dir, 'test_losses.txt')
    else:
        opts.loss_save_path = os.path.join(opts.save_dir, opts.loss_save_path)
    opts.logger(f'testing losses saved to {opts.loss_save_path}')
    np.savetxt(opts.loss_save_path, np.array(test_losses))

    opts.logger("Total time: {}".format(time_end - time_start))
    opts.logger("Time (opt iteration): {}".format(time_opt))
    opts.logger("Time per iter per instance: {}".format(time_opt / opts.test_length / opts.test_size))

