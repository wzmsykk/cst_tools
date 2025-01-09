from nsgaii_np import nsgaii_var
import matplotlib.pyplot as plt
from typing import List
import multiprocessing
import math
from math import inf
import pandas as pd
import re
from pathlib import Path
import numpy as np
class fnds_callback_create_Image():
    def __init__(self,savedir="") -> None:
        self.setNewSavedir(savedir)
        
    def setNewSavedir(self,savedir):
        self.savedir=Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)
    def __call__(self,nsgaii_obj,igen,fndslist):
        iprocess=multiprocessing.Process(target=image_worker_func,args=(self.savedir,igen,fndslist))
        iprocess.start()
        return 
class fnds_callback_dump_fnds():
    def __init__(self,savedir="") -> None:
        self.setNewSavedir(savedir)
        
    def setNewSavedir(self,savedir):
        self.savedir=Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)
    def __call__(self,nsgaii_obj,igen,fndslist):
        data_list_all=[]
        columnlist=[]
        prefix_name = ["Generation", "Index", "Front Index"]
        columnlist+=prefix_name
        for idx in range(nsgaii_obj.nval):
            columnlist.append("x_%d"%idx)
        for idx in range(nsgaii_obj.nobj):
            columnlist.append("f_%d"%idx)
        columnlist+=["Crowd Distance"]
        
        for ifnd, fnd in enumerate(fndslist):
            if fnd is not None:
                for indv in fnd:
                    data_row_list = []
                    data_row_list += [igen, indv.id, ifnd]
                    data_row_list += indv.value.tolist()
                    data_row_list += indv.obj.tolist()
                    data_row_list += [indv.crowed_dis]
                    data_list_all.append(data_row_list)
        csv = pd.DataFrame(data_list_all, columns=columnlist)
        fp = open(self.savedir / ("GEN_%d_Population.csv" % igen), "w")
        csv.to_csv(fp)
        fp.close()
        return 


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
        plt.scatter(x0,y0,c='none',marker='o', edgecolors='r')
    if fndslist[1] is not None:
        for ind in fndslist[1]:
            x1.append(ind.obj[0])
            y1.append(ind.obj[1])
        plt.scatter(x1,y1,c='none',marker='o', edgecolors='orange')
    if fndslist[2] is not None:
        for ind in fndslist[2]:
            x2.append(ind.obj[0])
            y2.append(ind.obj[1])      
        plt.scatter(x2,y2,c='none',marker='o', edgecolors='y')

    plt.xlabel('f1')
    plt.ylabel('f2')
    #plt.axis('scaled')
    plt.savefig(savedir / ('GEN_%05d_Front.png' %igen), bbox_inches='tight')
    return

def crowd_distance_stats_from_dump(savedir,gens=None):
    maxcl=[]
    mincl=[]
    avgcl=[]
    xs=[]
    savedir=Path(savedir)
    if not gens:### auto detect in save dir
        files = savedir.glob("GEN_*_Population.csv")
        if sum(1 for x in files) == 0:
            return None

        files = savedir.glob("GEN_*_Population.csv")
        maxigen = 0
        vaild = re.compile(r"GEN_(\d+)_Population.csv")
        for file in files:
            igen = int(vaild.search(file.name)[1])
            if igen > maxigen:
                maxigen = igen
        igen = maxigen
        gens=igen+1
    for igen in range(gens):
        csvpath=Path(savedir) / ("GEN_%d_Population.csv" % igen)
        df=pd.read_csv(csvpath)
        query=df[df['Front Index']<1]
        crowdlist=query["Crowd Distance"].tolist()
        filtered=[]
        for item in crowdlist:
            if item != inf:
                filtered.append(item)
        if len(filtered) ==0:
            continue
        maxc=np.max(filtered)
        minc=np.min(filtered)
        avgc=np.mean(filtered)
        maxcl.append(maxc)
        mincl.append(minc)
        avgcl.append(avgc)
        xs.append(igen)
    result=pd.DataFrame(list(zip(xs,maxcl,avgcl,mincl)),columns=["generation","max distance","avg distance","min distance"])
    result.to_csv(Path(savedir) / "Distances.csv")
    plt.plot(xs,maxcl)
    plt.plot(xs,mincl)
    plt.plot(xs,avgcl)
    plt.savefig(Path(savedir) / "Distances.png")
    plt.close()