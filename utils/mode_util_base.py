from os.path import split
import numpy as np
import matplotlib.pyplot as plt
import numpy.fft as fft
import math
from numpy.lib.shape_base import kron
from numpy.lib.type_check import nan_to_num
from scipy.signal import find_peaks
import glob
import pathlib
import numpy as np
import json

def read_field1D(filename):
    xl=[]
    yl=[]
    fp=open(filename,"r")
    lines=fp.readlines()
    lines=lines[2:]
    for line in lines:
        words=line.split()
        if(len(words)<2):
            break
        else:
            xl.append(float(words[0]))
            yl.append(float(words[1]))

    xpos=np.array(xl)
    value=np.array(yl)
    fp.close()
    return xpos,value



def read_maxcoords(filename):
    fp=open(filename,"r")
    lines=fp.readlines()
    er=float(lines[0].split()[1])
    ef=float(lines[1].split()[1])
    ez=float(lines[2].split()[1])
    hr=float(lines[3].split()[1])
    hf=float(lines[4].split()[1])
    hz=float(lines[5].split()[1])
    return er,ef,ez,hr,hf,hz


def xycoord_xycomp_to_rfcoord_rfcomp(xlist,ylist,xcomplist,ycomplist):

    rlist=np.sqrt(np.square(xlist)+np.square(ylist))
    flist=np.arctan2(ylist,xlist)

    rcomplist=xcomplist*np.cos(flist)+ycomplist*np.sin(flist)
    fcomplist=-xcomplist*np.sin(flist)+ycomplist*np.cos(flist)

    return rlist,flist,rcomplist,fcomplist

def rfcoord_xycomp_to_rfcoord_rfcomp(rlist,flist,xcomplist,ycomplist):
    
    rcomplist=xcomplist*np.cos(flist)+ycomplist*np.sin(flist)
    fcomplist=-xcomplist*np.sin(flist)+ycomplist*np.cos(flist)

    return rlist,flist,rcomplist,fcomplist


def rcomp_fcomp_alone_zaxis_line(resultdir,modeindex):
    dir=pathlib.Path(resultdir)
    EZXpath=dir.joinpath("Mode_{}_EZ_X.txt".format(modeindex))
    EZYpath=dir.joinpath("Mode_{}_EZ_Y.txt".format(modeindex))
    HZXpath=dir.joinpath("Mode_{}_HZ_X.txt".format(modeindex))
    HZYpath=dir.joinpath("Mode_{}_HZ_Y.txt".format(modeindex))
    maxcoordpath=dir.joinpath("Mode_{}_Coords.txt".format(modeindex))
    ex,excomp=read_field1D(EZXpath)
    _,eycomp=read_field1D(EZYpath)

    hx,hxcomp=read_field1D(HZXpath)
    _,hycomp=read_field1D(HZYpath)
    er,ef,ez,hr,hf,hz=read_maxcoords(maxcoordpath)
    hr_list=np.empty_like(hx)
    hr_list[:]=hr
    hf_list=np.empty_like(hx)
    hf_list[:]=hf
    er_list=np.empty_like(ex)
    er_list[:]=er
    ef_list=np.empty_like(ex)
    ef_list[:]=ef

    erl,efl,erc,efc=rfcoord_xycomp_to_rfcoord_rfcomp(er_list,ef_list,excomp,eycomp)
    hrl,hfl,hrc,hfc=rfcoord_xycomp_to_rfcoord_rfcomp(hr_list,hf_list,hxcomp,hycomp)
    return ex,erc,efc,hx,hrc,hfc

def rcomp_fcomp_alone_xyplane_circle(resultdir,modeindex):
    dir=pathlib.Path(resultdir)
    ECXpath=dir.joinpath("Mode_{}_EC_X.txt".format(modeindex))
    ECYpath=dir.joinpath("Mode_{}_EC_Y.txt".format(modeindex))
    HCXpath=dir.joinpath("Mode_{}_HC_X.txt".format(modeindex))
    HCYpath=dir.joinpath("Mode_{}_HC_Y.txt".format(modeindex))
    maxcoordpath=dir.joinpath("Mode_{}_Coords.txt".format(modeindex))

    et,excomp=read_field1D(ECXpath)
    _,eycomp=read_field1D(ECYpath)

    ht,hxcomp=read_field1D(HCXpath)
    _,hycomp=read_field1D(HCYpath)

    er,ef,ez,hr,hf,hz=read_maxcoords(maxcoordpath)

    ef_list=et/np.max(et)*2*math.pi
    hf_list=ht/np.max(ht)*2*math.pi

    hr_list=np.empty_like(ht)
    hr_list[:]=hr
    er_list=np.empty_like(et)
    er_list[:]=er

    erl,efl,erc,efc=rfcoord_xycomp_to_rfcoord_rfcomp(er_list,ef_list,excomp,eycomp)
    hrl,hfl,hrc,hfc=rfcoord_xycomp_to_rfcoord_rfcomp(hr_list,hf_list,hxcomp,hycomp)

    return et,erc,efc,ht,hrc,hfc

def rcomp_fcomp_alone_xyplane_radius(resultdir,modeindex):
    dir=pathlib.Path(resultdir)
    ERXpath=dir.joinpath("Mode_{}_ER_X.txt".format(modeindex))
    ERYpath=dir.joinpath("Mode_{}_ER_Y.txt".format(modeindex))
    HRXpath=dir.joinpath("Mode_{}_HR_X.txt".format(modeindex))
    HRYpath=dir.joinpath("Mode_{}_HR_Y.txt".format(modeindex))
    maxcoordpath=dir.joinpath("Mode_{}_Coords.txt".format(modeindex))

    et,excomp=read_field1D(ERXpath)
    _,eycomp=read_field1D(ERYpath)

    ht,hxcomp=read_field1D(HRXpath)
    _,hycomp=read_field1D(HRYpath)

    er,ef,ez,hr,hf,hz=read_maxcoords(maxcoordpath)

    er_list=et
    hr_list=ht
    
    ef_list=np.empty_like(et)
    ef_list[:]=ef
    hf_list=np.empty_like(ht)
    hf_list[:]=hf

    erl,efl,erc,efc=rfcoord_xycomp_to_rfcoord_rfcomp(er_list,ef_list,excomp,eycomp)
    hrl,hfl,hrc,hfc=rfcoord_xycomp_to_rfcoord_rfcomp(hr_list,hf_list,hxcomp,hycomp)

    return et,erc,efc,ht,hrc,hfc
    


    

def mode_wavenumber_mnp(XC,YFC,XR,YFR,XZ,YFZ):
    '''
    XR length along the radius
    YFR tangental component of the field along the radius curve
    XC length along the circle
    YFC tangental component of the field along the circle curve
    XZ length along the line parallel to the z-axis
    YFZ tangental component of the field along the line curve
    '''
    #FIND M
    rpc=1
    my=YFC
    nmy=np.reshape(np.repeat(np.reshape(my,(1,len(my))),rpc,axis=0),rpc*len(my))
    #print("MY_LEN=%d,NMY_LEN=%d"%(len(my),len(nmy)))
    N=len(nmy)
    fft_y=fft.rfft(my,n=my.size)
    abs_y=np.abs(fft_y)
    freqs = fft.rfftfreq(my.size, d=1./len(my))
    M_NUM = freqs[np.argmax(abs_y)]


    #寻找N_零点个数
    nzeros=0
    ntps=len(XR) #total points
    for i in range (ntps-1):
        if YFR[i]*YFR[i+1]<0:
            nzeros+=1
        elif YFR[i]==0:
            nzeros+=1
    
    #M=0 曲线无0点 N_NUM=1
    if M_NUM==0 and nzeros==0:
        N_NUM=1
    else:
        N_NUM=nzeros


    #寻找P_零点个数? 周期个数?
    m2=np.abs(np.mean(YFZ))**2
    if YFZ[0]*YFZ[-1]>0 and YFZ[0]*YFZ[-1]/m2>0.9:
        P_NUM=0
    else:
        rpc=1
        
        my=np.concatenate([-YFZ,YFZ])
        
        

        nmy=np.reshape(np.repeat(np.reshape(my,(1,len(my))),rpc,axis=0),rpc*len(my))
        #print("MY_LEN=%d,NMY_LEN=%d"%(len(my),len(nmy)))
        fft_y=fft.rfft(my,n=my.size)
        abs_y=np.abs(fft_y)
        freqs = fft.rfftfreq(my.size, d=1./len(my))
        P_NUM = freqs[np.argmax(abs_y)]

    return M_NUM,N_NUM,P_NUM

def main_mode_type(resultdir,modeindex,threshold=10):
    curdir=pathlib.Path(resultdir)

    pt="MODE_"+str(modeindex)+"_Coffs.txt"
    pt=curdir.joinpath(pt)
    fp=open(pt,"r")
    lines=fp.readlines()
    line=lines[0]
    cof=line.split()[1]
    fp.close()

    #custom result
    alpha=threshold
    coff=float(cof)
    if coff<alpha and coff>1/alpha:
        mc="HX"
    elif coff<1/alpha:
        mc="TE"
    else:
        mc="TM"
    return mc


