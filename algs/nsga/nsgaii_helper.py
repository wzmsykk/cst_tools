from .nsgaii_np import nsgaii_var
import matplotlib.pyplot as plt
from typing import List
import multiprocessing
import math
import pandas
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
class fnds_callback_create_Image_dump_fnds():
    def __init__(self,savedir="") -> None:
        self.setNewSavedir(savedir)
        self.paramToOptim=["Req","Leq"]
        self.resultNames=["frequency","RoverQ","shunt_dependence"]
    def setNewSavedir(self,savedir):
        self.savedir=Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)
    def __call__(self,igen,fndslist):
        iprocess=multiprocessing.Process(target=image_worker_func,args=(self.savedir,igen,fndslist))
        iprocess.start()
        self.dump_fnds_structs(self.savedir,igen,fndslist)
        return 
    def dump_fnds_structs(self,savedir,igen,fndslist:List[List[nsgaii_var]]):
        idf=None
        _index=0
        for ind_f,front in enumerate(fndslist):
            if front is not None:
                for ind in front:
                    u={
                    "_front":ind_f,
                    "_id":ind.id,
                    "req":ind.value[0],
                    "leq":ind.value[1],
                    "freq":ind.constraint_obj[0],
                    "roq":ind.obj[0],
                    "shunt_dependence":ind.obj[1]
                    }
                    ndf=pandas.DataFrame(u,index=[_index])
                    _index+=1
                    if idf is not None:
                        idf=idf.append(ndf)
                    else:
                        idf=ndf

        idf.to_csv(savedir / ("Fnds_struct_gen_%d.csv"%igen))

def image_worker_func(savedir,igen,fndslist:List[List[nsgaii_var]]):
    x0=[]
    y0=[]
    x1=[]
    y1=[]
    x2=[]
    y2=[]
    if fndslist[0] is not None:
        for ind in fndslist[0]:
            x0.append(ind.obj[0])
            y0.append(ind.obj[1])
        plt.scatter(x0,y0,c='r',marker='o')
    if fndslist[1] is not None:
        for ind in fndslist[1]:
            x1.append(ind.obj[0])
            y1.append(ind.obj[1])
        plt.scatter(x1,y1,c='orange',marker='o')
    if fndslist[2] is not None:
        for ind in fndslist[2]:
            x2.append(ind.obj[0])
            y2.append(ind.obj[1])      
        plt.scatter(x2,y2,c='y',marker='o')

    plt.xlabel('f1')
    plt.ylabel('f2')
    #plt.axis('scaled')
    plt.savefig(savedir / ('GEN_%05d_Front.png' %igen), bbox_inches='tight')
    return