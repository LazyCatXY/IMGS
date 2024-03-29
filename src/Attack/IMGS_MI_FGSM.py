import numpy as np
import torch
import torchvision
import os
import random
import numpy as np

import torch
import torch.nn.functional as F

random.seed(18)

def loss_fun(model, x, y):
    p = model.net(x.to(model.device))
    loss = torch.nn.CrossEntropyLoss()(p, y.to(model.device))
    return loss

def LMSE_filter(img, window_size):

    amplitude = img[:, 0:1, :, :]
    phase = img[:, 1:2, :, :]
    min_amplitude = torch.min(amplitude)
    max_amplitude = torch.max(amplitude)
    min_phase = torch.min(phase)
    max_phase = torch.max(phase)

    local_mean_amp = F.avg_pool2d(amplitude, window_size, stride=1, padding=window_size//2)
    local_mean_phs = F.avg_pool2d(phase, window_size, stride=1, padding=window_size//2)

    local_variance_amp = F.avg_pool2d(amplitude.pow(2), window_size, stride=1, padding=window_size//2) - local_mean_amp.pow(2)
    local_variance_phs = F.avg_pool2d(phase.pow(2), window_size, stride=1, padding=window_size//2) - local_mean_phs.pow(2)

    weight_amp = local_variance_amp / (local_variance_amp + local_mean_amp.pow(2))
    weight_phs = local_variance_phs / (local_variance_phs + local_mean_phs.pow(2))

    filtered_amplitude = weight_amp *  amplitude + (1 - weight_amp) * local_mean_amp
    filtered_amplitude = torch.clamp(filtered_amplitude, min_amplitude, max_amplitude)

    filtered_phase = weight_phs *  phase + (1 - weight_phs) * local_mean_phs
    filtered_phase = torch.clamp(filtered_phase, min_phase, max_phase)

    filtered_img = torch.cat([filtered_amplitude, filtered_phase], dim=1)
    return filtered_img

def get_random_img(path, label):
    target_name = ('2S1', 'BMP2', 'BRDM2', 'BTR60', 'BTR70', 'D7', 'T62', 'T72', 'ZIL131', 'ZSU234')
    dir_list = os.listdir(path)
    dir_list.remove(target_name[label])
    chosen_dir = random.choice(dir_list)
    path = os.path.join(path, chosen_dir)
    files = os.listdir(path)
    npy_files = [f for f in files if f.endswith('.npy')]
    random_file = random.choice(npy_files)

    data = np.load(os.path.join(path, random_file))
    data = data.transpose(2, 0, 1)
    data = torch.Tensor(data)
    data = torchvision.transforms.CenterCrop(88)(data)
    return data

def mix(x,labels):
    path = './IMGS/dataset/soc/eval_1'
    for i in range(x.shape[0]):
        x_2 = get_random_img(path,labels[i])
        x_2 = x_2.type_as(x)
        x[i][0] = x[i][0] + x_2[0] * 0.1
        x[i][1] = x[i][1] + x_2[1] * 0.3
    return x


def SIM(model, images, labels):
    grad = torch.zeros(images.shape).type_as(images)
    add_images = torch.zeros(images.shape).type_as(images)
    trans_images = images.clone()

    iterations = 1
    for i in range(iterations):
        add_images = mix(add_images, labels)
    add_images = add_images/iterations
    trans_images = trans_images + add_images

    scales = [0.7, 0.75, 0.8, 0.85, 0.9]
    for scale in scales:
        scales_images = trans_images * scale
        scales_images = scales_images.detach()
        scales_images.requires_grad = True
        model.net.zero_grad()
        loss = loss_fun(model, scales_images, labels)
        loss.backward()
        grad = grad + scales_images.grad.data
    return grad

def imgs_mi_attack(model, image, label, epsilon, num_iterations = 10, momentum=1):

    # Initialize the adversarial example to the input data
    image = image.to(model.device)
    alpha = epsilon / num_iterations
    adv_image = image + torch.Tensor(np.random.uniform(-alpha, alpha, image.shape)).type_as(image)
    g = torch.zeros(image.size(0), 1, 1, 1).cuda()

    # Loop over the number of iterations
    for _ in range(num_iterations):

        # Compute the gradient 
        adv_image = adv_image.detach()
        adv_image.requires_grad = True
        model.net.zero_grad()
        loss = loss_fun(model, adv_image, label)
        loss.backward()
        grad_0 = adv_image.grad.data

        total_grad = grad_0 + SIM(model, adv_image, label)
        total_grad = LMSE_filter(total_grad, 15)

        # Get the gradient
        g = momentum * g + (total_grad/(torch.mean(torch.abs(total_grad), dim=(1,2,3), keepdim=True))).cuda()
        
        # Update the adversarial example
        sign_grad = g.sign()
        adv_image = adv_image + alpha * sign_grad

        adv_image[:,0,:,:] = torch.min(torch.max(adv_image[:,0,:,:], image[:,0,:,:] - epsilon), image[:,0,:,:] + epsilon)
        adv_image[:,1,:,:] = torch.min(torch.max(adv_image[:,1,:,:], image[:,1,:,:] - epsilon), image[:,1,:,:] + epsilon)

        adv_image[:,0,:,:] = torch.clamp(adv_image[:,0,:,:], torch.min(image[:,0,:,:]), torch.max(image[:,0,:,:]))
        adv_image[:,1,:,:] = torch.clamp(adv_image[:,1,:,:], torch.min(image[:,1,:,:]), torch.max(image[:,1,:,:]))      

    # Return the adversarial example
    return adv_image
