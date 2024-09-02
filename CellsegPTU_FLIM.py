# -*- coding: utf-8 -*-
"""
Created on Sun Sep  1 00:43:05 2024

@author: narai
"""
import numpy as np
import matplotlib.pyplot as plt
from plantseg.predictions.functional.predictions import unet_predictions
from sklearn.model_selection import ParameterGrid
from tqdm import tqdm
from plantseg.segmentation.functional.segmentation import mutex_ws
from PTU_ScanRead import PTU_ScanRead, Process_Frame, mHist2

#%%

filename = r'D:\Collabs\fromYuexuan\Yuexuan_ptu_testfile.ptu'
cnum = 1 # by default
max_cell_Area = 5000 # in pixels

head, im_sync, im_tcspc, im_chan, im_line, im_col, im_frame = PTU_ScanRead(filename)
dind = np.unique(im_chan) # unique detector channels
nFrames = head['ImgHdr_MaxFrames']
if 'PIENumPIEWindows' in head:
    cnum = head['PIENumPIEWindows'] # number of PIE cycles - this effects the tcspc channels

mem_PIE = 2 # laser pulse for membrane channel
mem_det = 2 # detector id for membrane channel
auto_PIE = 1 # laser pulse for autofluorescence channel
auto_det = 1 # detector id for autofluorescence channel

param_grid = {
    "beta": [ round(x,1) for x in np.arange(0.5,0.95,0.05)],
    "post_minsize": [ round(x,1) for x in np.arange(190,210,10)],
}
params = list(ParameterGrid(param_grid))

resolution = 0.1 # ns for tcspc
for nz in range(nFrames):
    ind = np.where(im_frame == nz)[0]
    tag, tau, tcspc_pix,_ = Process_Frame(im_sync[ind], im_col[ind], im_line[ind], im_chan[ind],
                                        im_tcspc[ind], head, cnum = cnum, resolution = resolution)
    pos = np.argmax(np.sum(tcspc_pix[:,:,:,mem_det*mem_PIE-1],axis = (0,1)))
    nCh = pos +  int(np.ceil(5/resolution))
    img_mem = np.sum(tcspc_pix[:,:,pos:pos + nCh-1,mem_det*mem_PIE-1],axis = 2) # time gated image
    # here the image reconstructed can be done in various ways - time gated, filtered with respect to a particular tcspc decay value etc. 
    
    # img_mem = tag[:,:,mem_det-1,mem_PIE-1]
    img_np_scaled = (img_mem - np.min(img_mem)).astype(float)
    img_np_scaled /= np.max(img_np_scaled)
    pred = unet_predictions(img_np_scaled[np.newaxis:,:],"confocal_2D_unet_ovules_ds2x", 'pioneering-rhino', patch=[1,512,512])
    res = []
    for param in tqdm(params, desc="Post processing"):
        beta = param["beta"]
        post_mini_size = param["post_minsize"]

        # for the mutex_ws function,  beta parameter for GASP. A small value will steer the segmentation towards under-segmentation
        mask = mutex_ws(pred,superpixels=None,beta=beta,post_minsize=post_mini_size,n_threads=6)
        # mask = dt_watershed(pred[0,:,:], n_threads=6) 
        
        
       
        res.append({
            "name": 'try',
            "beta": beta,
            "post_mini_size": post_mini_size,
            "pred": pred[0,:,:],
            "mask": mask,
            # "overlay": imgout,
            # "props": props,
            # "props_df": props_df
            })
        
        tmp = [np.unique(d['mask'], return_counts=True) for d in res]
        ncells = [len(unique) for unique, counts in tmp] # number of cells detected for each parameter
        idx = np.argmax(ncells) # gives the first position of maximum cells detected
        beta = res[idx]['beta']
        post_mini_size = res[idx]['post_mini_size']
        CellId, CellArea = tmp[idx]
        cidx = CellArea<max_cell_Area
        CellId = CellId[cidx]
        CellArea = CellArea[cidx]
        Cnum = np.argsort(CellId)
        maskt = res[idx]["mask"][0]
        mask = 0*maskt
        for j in range(len(Cnum)):
            mask[maskt == CellId[Cnum[j]]] = j
        
        im_mask = mask[im_line, im_col] # this is now a vector that assigns a mask value to each photon dependin on its im_col and im_line
        tmpCh = np.ceil(head['MeasDesc_GlobalResolution'] / head['MeasDesc_Resolution']) # total number of channels in the original tcspc histogram
        
        ind = (im_chan == dind[auto_det-1]) & (im_tcspc<tmpCh/cnum*auto_PIE) & (im_tcspc>=((auto_PIE-1))*tmpCh/cnum)
        idx = np.where(ind)[0]
        Resolution = max(head['MeasDesc_Resolution'] * 1e9, resolution)  # resolution of 0.256 ns to calculate average lifetimes
        chDiv = np.ceil(1e-9 * Resolution / head['MeasDesc_Resolution'])
        SyncRate = 1.0 / head['MeasDesc_GlobalResolution']
        Ngate = round(head['MeasDesc_GlobalResolution'] / head['MeasDesc_Resolution'] * (head['MeasDesc_Resolution'] / Resolution / cnum) * 1e9)
        # tcspc_cell =  np.zeros((len(Cnum), Ngate), dtype=np.uint32)
        # print(len(idx))
        tcspc_cell = mHist2(im_mask[idx].astype(np.int64), 
                                    (im_tcspc[idx] / chDiv).astype(np.int64) - int((auto_PIE-1)*tmpCh/cnum/chDiv), 
                                    np.arange(len(Cnum)), 
                                    np.arange(Ngate))[0]  # tcspc histograms for all the pixels at once!
    
    
        
        fig, axs = plt.subplots(1,4,figsize=(20,10))
        axs = axs.ravel()
        fig.suptitle(res[idx]["name"])
        
        axs[0].imshow(img_mem,cmap="gray")
        axs[0].set_title('Rescaled Input')
        axs[0].axis('off')
        
        axs[1].imshow(res[idx]["pred"])
        axs[1].set_title('PlangSeg Pred')
        axs[1].axis('off')
        
        axs[2].imshow(res[idx]["mask"][0])
        axs[2].set_title('Label')
        axs[2].axis('off')
        
        axs[3].imshow(res[idx]["overlay"])
        axs[3].set_title('Outline')
        axs[3].axis('off')
            