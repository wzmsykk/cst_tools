
import numpy as np
import matplotlib.pyplot as plt
import numpy.fft as fft
import math
import pathlib
import numpy as np


def read_coffs(filename):
    resultlist=[]
    fp=open(filename,"r")
    lines=fp.readlines()
    totallines=len(lines)
    pnum=math.floor(totallines/3)
    namelist=[]
    rvlist=[]
    rnlist=[]
    dlist=[]
    expect="Name"

    for line in lines:
        
        if(expect=="Name"):
            namelist.append(line.split()[0])
            expect="Comp_Name"
        elif(expect=="Comp_Name"):
            words=line.split()
            rnlist.clear()
            for word in words:
                
                rnlist.append(word)
            expect="Comp_Value"
        elif(expect=="Comp_Value"):
            words=line.split()
            rvlist.clear()
            for word in words:
                
                rvlist.append(word)
            nvs=zip(rnlist,rvlist)
            mydict=dict( (name,value) for name,value in nvs)
            dlist.append(mydict)
            expect="Name"

    nvs=zip(namelist,dlist)
    mydict=dict( (name,value) for name,value in nvs)

    return mydict

def totalmodes(result_dir):
    curdir=pathlib.Path(result_dir)
    freqs=curdir.glob("MODE_*_Freq.txt")
    flist=list()
    for tx in freqs:
        flist.append(tx)
    totalmodes=len(flist)
    return totalmodes

def result_stats(result_dir="",printhost=True):
    curdir=pathlib.Path(result_dir)
    freqs=curdir.glob("MODE_*_Freq.txt")
    flist=list()
    for tx in freqs:
        flist.append(tx)
    statlist=list()
    totalmodes=len(flist)

    
    

    for i in range(1,totalmodes+1):
        pt="MODE_"+str(i)+"_Freq.txt"
        pt=curdir.joinpath(pt)
        fp=open(pt,"r")
        lines=fp.readlines()
        line=lines[2]
        fq=line.split()[1]
        fp.close()
        pt="MODE_"+str(i)+"_Type.txt"
        pt=curdir.joinpath(pt)
        fp=open(pt,"r")
        lines=fp.readlines()
        line=lines[0]
        tp=line.split()[1]
        fp.close()


        pt="MODE_"+str(i)+"_Coffs.txt"
        pt=curdir.joinpath(pt)
        mycoffdict=read_coffs(pt)
        cof=mycoffdict['TEM_Coffs']['value']
        
        

        #custom result
        alpha=2.5
        coff=float(cof)
        if coff<alpha and coff>1/alpha:
            mc="HX"
        elif coff<1/alpha:
            mc="TE"
        else:
            mc="TM"


        statlist.append((i,tp,fq,coff,mc))

    
    if printhost:
        uformat="MODE:{}\tType:{}\tFreq:{}\tTEMCoff:{:5f}\tcustType:{}"
        for element in statlist:
            print(uformat.format(*element))
        

    return statlist

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

def read_field1D_Complex(filename):
    
    fp=open(filename,"r")
    lines=fp.readlines()
    names=[]
    values=[]
    words=lines[0].split()
    for word in words:
        names.append(word)
    lines=lines[1:]
    mydd=[]
    length=len(names)
    for line in lines:
        words=line.split()
        mydd.clear()
        for word in words:                
            mydd.append(float(word))
        values.append(mydd[:length])


    npvalue=np.array(values)
    fp.close()
    return names,npvalue

def read_field3D(filepath,shape=(128,128,32)):
    fp=open(filepath,"r")
    #推测XYZDIMS
    lines=fp.readlines()
    xdim,ydim,zdim=shape
    narray=np.zeros((xdim,ydim,zdim,6))   
    dumpcount=5
    print("Total lines:%d" % len(lines))
    size=xdim*ydim*zdim
    print("EXPECTED SIZE:%d"% (size+2))
    line=lines[2]
    words=line.split()
    x0=float(words[0])
    xspace=abs(x0)*2/(xdim-1)
    y0=float(words[1])
    yspace=abs(y0)*2/(ydim-1)
    z0=float(words[2])
    zspace=abs(z0)*2/(zdim-1)
    header=dict()
    header["x0"]=x0
    header["y0"]=y0
    header["z0"]=z0
    header["xspace"]=xspace
    header["yspace"]=yspace
    header["zspace"]=zspace
    header["xdim"]=xdim
    header["ydim"]=ydim
    header["zdim"]=zdim
    for index in range (size):
        line=lines[index+2]
        words=line.split()
        if (index<dumpcount):
            print(words)
        i=round((float(words[0])-x0)/xspace)
        j=round((float(words[1])-y0)/yspace)
        k=round((float(words[2])-z0)/zspace)
        
        u=np.array(words[3:])
        u=u.astype(np.float)
        narray[i][j][k]=u
        # if (index<dumpcount):
        #     print("i=%d,j=%d,k=%d,u="%(i,j,k),u)
            
    return narray,header
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
    


    
def mode_wavenumber_m(flist,fcomp):
    #FIND M
    rpc=1
    my=fcomp
    nmy=np.reshape(np.repeat(np.reshape(my,(1,len(my))),rpc,axis=0),rpc*len(my))
    #print("MY_LEN=%d,NMY_LEN=%d"%(len(my),len(nmy)))
    N=len(nmy)
    fft_y=fft.rfft(my,n=my.size)
    abs_y=np.abs(fft_y)
    freqs = fft.rfftfreq(my.size, d=1./len(my))
    M_NUM = freqs[np.argmax(abs_y)]
    return M_NUM
def mode_wavenumber_n(rlist,fcomp):
    #find N
    nzeros=0
    
    YFR=fcomp
    #FROM MIDDLE TO START
    while YFR[-1]==0:
        YFR=YFR[:-1]#去除末尾的0元素
    
    

    #排除波动测试
    YSMD=np.zeros_like(YFR)
    for i in range(len(YFR)-1):
        YSMD[i]=(YFR[i]+YFR[i+1])/2
    YFR=YSMD

    ntps=len(YFR) #total points

    for i in range (math.floor(ntps/2-1),ntps-1):
        if YFR[i]*YFR[i+1]<0:
            nzeros+=1
        elif YFR[i]==0:
            nzeros+=1    
    if nzeros==0:
        nzeros=nzeros+1
    return nzeros
def mode_wavenumber_p(zlist,fcomp):
    #FIND P
    rpc=1
    my=fcomp
    nmy=np.reshape(np.repeat(np.reshape(my,(1,len(my))),rpc,axis=0),rpc*len(my))
    #print("MY_LEN=%d,NMY_LEN=%d"%(len(my),len(nmy)))
    N=len(nmy)
    fft_y=fft.rfft(my,n=my.size)
    abs_y=np.abs(fft_y)
    freqs = fft.rfftfreq(my.size, d=1./len(my))
    P_NUM = freqs[np.argmax(abs_y)]
    return P_NUM

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

def main_mode_type(resultdir,modeindex,th_upper=10,th_below=0.1):
    curdir=pathlib.Path(resultdir)

    pt="MODE_"+str(modeindex)+"_Coffs.txt"
    pt=curdir.joinpath(pt)
    coffsDict=read_coffs(pt)
    cof=coffsDict['TEM_Coffs']['value']

    #custom result

    coff=float(cof)
    if coff<th_upper and coff>th_below:
        mc="HX"
    elif coff<th_below:
        mc="TE"
    else:
        mc="TM"
    return mc


