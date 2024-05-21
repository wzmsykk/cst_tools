from .mode_util_base import read_coffs,result_stats,read_field1D,read_field1D_Complex,read_maxcoords
from .mode_util_base import mode_wavenumber_mnp,main_mode_type
from .mode_util_base import mode_wavenumber_m,mode_wavenumber_n,mode_wavenumber_p
from .modes_batch_v2 import read_field3D
import numpy as np

import matplotlib.pyplot as plt
import pathlib


def mode_wavenumber_nh(rlist,fcomp,log=False): #H 边界处非0
    #find N
    nzeros=0
    
    YFR=fcomp
    #FROM MIDDLE TO START
    while YFR[-1]==0:
        YFR=YFR[:-1]#去除末尾的0元素
    while YFR[0]==0:
        YFR=YFR[1:]


    h_f=YFR.copy()
    #对h_f积分
    firstzero_found=False
    for pos,elem in enumerate(rlist):
        if elem>=0:
            firstzero_found=True
            break

    h_f_cut=h_f[pos:]
    int_h_f=np.zeros_like(h_f_cut)
    for i in range(1,len(int_h_f)):
        int_h_f[i]=int_h_f[i-1]+h_f_cut[i-1]
    h_f_fin=h_f.copy()
    h_f_fin[pos:]=int_h_f



    YFR=h_f_fin[pos:]
    if len(YFR)==0:
        return 0
    YFR=YFR-YFR[-1]
    ntps=len(YFR) #total points
    
    #平均化
    #YMR=np.zeros_like(YFR)
    #for i in range(0,len(YFR)-1):
    #    YMR[i]=(YFR[i]+YFR[i+1])/2
    #YFR=YMR


    for i in range (0,ntps-1): 
        if YFR[i]*YFR[i+1]<0:
            nzeros+=1
            if log:
                print("Z P at %d v=%f" % (i,YFR[i]))
        elif YFR[i]==0:
            nzeros+=1    
            if log:
                print("Z P at %d v=%f" % (i,YFR[i]))
    if YFR[ntps-1]==0:
        nzeros+=1
        if log:    
            print("Z P at %d v=%f" % (i,YFR[i]))
    return nzeros

def mode_wavenumber_ne(rlist,fcomp,log=False): #E 边界处为0
    #find N
    nzeros=0
    
    YFR=fcomp
    #FROM START TO END
    while YFR[-1]==0:
        YFR=YFR[:-1]#去除末尾的0元素
    while YFR[0]==0:
        YFR=YFR[1:]#去除头部的0元素

    ntps=len(YFR) #total points
    
    
    #中间处是否为0？
    mid_zero=False
    cut_range=15 #排除15个点
    threshold_zero=0.05 
    midpos=int(ntps/2)
    maxabsy=np.max(np.abs(YFR))
    if abs(YFR[midpos])/maxabsy<threshold_zero:
        if log:
            print("EZ P at MidPos %d" %midpos )
        mid_zero=True
    
    for i in list(range(0,midpos-cut_range))+list(range(midpos+cut_range,ntps-1)): 
        if YFR[i]*YFR[i+1]<0:
            nzeros+=1
            if log:
                print("EZ P at %d v=%f" % (i,YFR[i]))
        elif YFR[i]==0:
            nzeros+=1    
            if log:
                print("EZ P at %d v=%f" % (i,YFR[i]))
    if YFR[ntps-1]==0:
        nzeros+=1
        if log:    
            print("EZ_SP P at %d v=%f" % (i,YFR[i]))
    
    if mid_zero:
        nzeros=nzeros+1
    nzeros=nzeros+2
    if nzeros % 2==0:
        nzeros=nzeros/2
    else:
        nzeros=(nzeros-1)/2
    return nzeros

def mode_type_full(resultdir,modeindex):
    import pathlib
    mainmode=main_mode_type(resultdir,modeindex,10,0.2)
    rd=pathlib.Path(resultdir)

    ec_path=rd.joinpath("Mode_%d_E_Circle.txt" % modeindex)
    _,e_circle=read_field1D_Complex(ec_path)
    e_f=e_circle[:,9]
    x_c=e_circle[:,3]
    m_e=mode_wavenumber_m(x_c,e_f)

    er_path=rd.joinpath("Mode_%d_E_Radius.txt" % modeindex)
    _,e_radius=read_field1D_Complex(er_path)
    e_f=e_radius[:,9]
    e_z=e_radius[:,7]
    x_r=e_radius[:,3]
    
    n_e=mode_wavenumber_ne(x_r,e_f)
    

    ez_path=rd.joinpath("Mode_%d_E_ZLine.txt" % modeindex)
    _,e_zline=read_field1D_Complex(ez_path)
    e_f=e_zline[:,9]
    x_z=e_zline[:,3]

    e_f=np.concatenate([-e_f[::-1],e_f])
    p_e=mode_wavenumber_p(x_z,e_f)

    hc_path=rd.joinpath("Mode_%d_H_Circle.txt" % modeindex)
    _,h_circle=read_field1D_Complex(hc_path)
    h_f=h_circle[:,9]
    x_c=h_circle[:,3]
    m_h=mode_wavenumber_m(x_c,h_f)

    hr_path=rd.joinpath("Mode_%d_H_Radius.txt" % modeindex)
    _,h_radius=read_field1D_Complex(hr_path)
    h_f=h_radius[:,9]
    h_z=h_radius[:,7]
    x_r=h_radius[:,3]

    
    


    n_h=mode_wavenumber_nh(x_r,h_f)
    
    hz_path=rd.joinpath("Mode_%d_H_ZLine.txt" % modeindex)
    _,h_zline=read_field1D_Complex(hz_path)
    h_f=h_zline[:,9]
    x_z=h_zline[:,3]

    h_f_2=h_f[::-1]
    h_f=np.concatenate([h_f_2,h_f])
    p_h=mode_wavenumber_p(x_z,h_f)

    return mainmode,m_e,n_e,p_e,m_h,n_h,p_h

def mode_type_final2(resultdir,modeindex):
    mainmode,m_e,n_e,p_e,m_h,n_h,p_h=mode_type_full(resultdir,modeindex)
    if mainmode=="TM":
        M=m_h
        N=n_h
        P=p_h
        if m_h!=0 and n_h>1:
            n_h=n_h-1
    elif mainmode=="TE":
        M=m_e
        N=n_e
        P=p_e
    else:
        mainmode=main_mode_type(resultdir,modeindex,1,1)        
        if mainmode=="TM":
            M=m_h
            N=n_h
            P=p_h
        if m_h!=0 and n_h>1:
            n_h=n_h-1
        elif mainmode=="TE":
            M=m_e
            N=n_e
            P=p_e
        mainmode="HX_"+mainmode
    ml=[modeindex,mainmode,int(m_h),int(n_h),int(p_h),int(m_e),int(n_e),int(p_e),0]
    #last 0 indicates it is not manually updated 
    return ml

def findTM020index(result_dir):
    u=[]
    tm020index=-1
    for i in range(1,11):
        c=mode_type_final2(result_dir,i)
        print(mode_type_final2(result_dir,i))
        u.append(c)
        if c[1]=='HX_TM' or c[1] =='TM':
            if c[2]==0 and c[3]==2 and c[4]==0:
                tm020index=c[0]
    return tm020index
        
