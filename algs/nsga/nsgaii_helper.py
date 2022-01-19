import nsgaii
import matplotlib.pyplot as plt
from typing import List
import multiprocessing
from pathlib import Path
class fnds_callback_create_Image():
    def __init__(self,savedir="") -> None:
        self.setNewSavedir(savedir)
        
    def setNewSavedir(self,savedir):
        self.savedir=Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)
    def __call__(self,igen,fndslist):
        iprocess=multiprocessing.Process(target=image_worker_func,args=(self.savedir,igen,fndslist))
        iprocess.start()
        return 
def image_worker_func(savedir,igen,fndslist:List[List[nsgaii.nsgaii_var]]):
    x0=[]
    y0=[]
    x1=[]
    y1=[]
    x2=[]
    y2=[]
    if fndslist[0] is not None:
        for ind in fndslist[0]:
            x0.append(ind.result[0])
            y0.append(ind.result[1])
        plt.scatter(x0,y0,c='r',marker='o')
    if fndslist[1] is not None:
        for ind in fndslist[1]:
            x1.append(ind.result[0])
            y1.append(ind.result[1])
        plt.scatter(x1,y1,c='orange',marker='o')
    if fndslist[2] is not None:
        for ind in fndslist[2]:
            x2.append(ind.result[0])
            y2.append(ind.result[1])      
        plt.scatter(x2,y2,c='y',marker='o')

    plt.xlabel('f1')
    plt.ylabel('f2')
    #plt.axis('scaled')
    plt.savefig(savedir / ('GEN_%05d_Front.png' %igen), bbox_inches='tight')
    return