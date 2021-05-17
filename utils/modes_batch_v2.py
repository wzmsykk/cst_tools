from os.path import split
import numpy as np
import matplotlib.pyplot as plt
import numpy.fft as fft
import os
from numpy.lib.shape_base import kron
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

def xycoord_xycomp_to_rfcoord_rfcomp(xlist,ylist,xcomplist,ycomplist):

    rlist=np.sqrt(np.square(xlist)+np.square(ylist))
    flist=np.arctan2(ylist,xlist)

    rcomplist=xcomplist*np.cos(flist)+ycomplist*np.sin(flist)
    fcomplist=xcomplist*np.sin(flist)+ycomplist*np.cos(flist)

    return rlist,flist,rcomplist,fcomplist

def read_maxcoords(filename):
    fp=open(filename,"r")
    lines=fp.readlines()
    er=lines[0].split()[1]
    ef=lines[1].split()[1]
    ez=lines[2].split()[1]
    hr=lines[3].split()[1]
    hf=lines[4].split()[1]
    hz=lines[5].split()[1]
    return er,ef,ez,hr,hf,hz

def rfcoord_xycomp_to_rfcoord_rfcomp(rlist,flist,xcomplist,ycomplist):
    
    rcomplist=xcomplist*np.cos(flist)+ycomplist*np.sin(flist)
    fcomplist=xcomplist*np.sin(flist)+ycomplist*np.cos(flist)

    return rlist,flist,rcomplist,fcomplist

def read_mode_batch(resultdir):


    p = os.path.join(resultdir,"R_*_L_*")
    dirlist=glob.glob(p)
    for dir in dirlist:
        dir_name=os.path.split(dir)[1]
        mode_recog(dir,"Mode_result_%s.npy" % dir_name)


    


    pass

def friendly_print_onemode(result,idx):
    Mcount=result[idx][1]
    Ncount=None
    Pcount=None
    if(result[idx][0]==0):
        str0="TM"
        print("MODE %s is %s_%d_NP"%(str(idx+1).zfill(3),str0,result[idx][1]))
    elif(result[idx][0]==1):
        str0="TE"
        print("MODE %s is %s_%d_NP"%(str(idx+1).zfill(3),str0,result[idx][1]))
    elif(result[idx][0]==2):
        str0="HX"
        print("MODE %s is HX"%(str(idx+1).zfill(3)))
    return str0,Mcount,Ncount,Pcount
    
def friendly_print(result):
    str0=""
    
    for i in range(result.shape[0]):
        if(result[i][0]==0):
            str0="TM"
            print("MODE %s is %s_%d_NP"%(str(i+1).zfill(3),str0,result[i][1]))
        elif(result[i][0]==1):
            str0="TE"
            print("MODE %s is %s_%d_NP"%(str(i+1).zfill(3),str0,result[i][1]))
        elif(result[i][0]==2):
            str0="HX"
            print("MODE %s is HX"%(str(i+1).zfill(3)))
    return str0
def save_result(result,dst_path):
    str0=""
    fp=open(dst_path,"w")
    for i in range(result.shape[0]):
        if(result[i][0]==0):
            str0="TM"
            fp.write("MODE %s is %s_%d_NP\n"%(str(i+1).zfill(3),str0,result[i][1]))
        elif(result[i][0]==1):
            str0="TE"
            fp.write("MODE %s is %s_%d_NP\n"%(str(i+1).zfill(3),str0,result[i][1]))
        elif(result[i][0]==2):
            str0="HX"
            fp.write("MODE %s is HX\n"%(str(i+1).zfill(3)))     
    fp.close()
    
def save_np_mode_result(result,dst_path):
    np.save(dst_path,result)  
def read_field_data_batch(resultdir):
    p = os.path.join(resultdir,"R_*_L_*")
    dirlist=glob.glob(p)
    for dir in dirlist:
        dir_name=os.path.split(dir)[1]
        convert_field_to_nparray(dir,dir_name)



def convert_field_to_nparray(result_dir="",export_name="Export"):
    totalmodes=1
    mrtname=os.path.join(result_dir,"Mode_Result.txt")
    print("Now Processing Path:%s"%result_dir)
    if(os.path.exists(mrtname)):
        print("Found Mode Result")
        fp=open(mrtname)
        lines=fp.readlines()
        lines=lines[1:]
        totalmodes=len(lines)
        print("TOTALMODES:%d"%totalmodes)
        
    else:
        print('NO FOUND')
        return None
    result=mode_recog(result_dir)
    for mode_index in range(totalmodes):
        mode_name=mode_index+1
        epath=os.path.join(result_dir,"Mode%dEField.txt"%mode_name)
        hpath=os.path.join(result_dir,"Mode%dHField.txt"%mode_name)
        efield,eheader=read_field3D(epath)
        eheader["fieldtype"]="EField"
        eheader["ModeIndex"]=mode_index
        eheader["ModeName"]="Mode_"+str(mode_name)
        modetypestr,Mcount,Ncount,Pcount=friendly_print_onemode(result,mode_index)
        eheader["ModeType"]=modetypestr
        eheader["M"]=Mcount
        eheader["N"]=Ncount
        eheader["P"]=Pcount
        hfield,hheader=read_field3D(hpath)
        hheader["fieldtype"]="HField"
        hheader["ModeIndex"]=mode_index
        hheader["ModeName"]="Mode_"+str(mode_name)
        hheader["ModeType"]=modetypestr
        hheader["M"]=Mcount
        hheader["N"]=Ncount
        hheader["P"]=Pcount
        np.save("%s_Mode%dEField.npy"%(export_name,mode_name),efield)
        np.save("%s_Mode%dHField.npy"%(export_name,mode_name),hfield)
        with open("%s_Mode%dEField.json"%(export_name,mode_name),"w") as fe:
            json.dump(eheader,fe)
        with open("%s_Mode%dHField.json"%(export_name,mode_name),"w") as fh:
            json.dump(hheader,fh)

    pass
def read_field3D(filepath):
    fp=open(filepath,"r")
    xdim=128
    ydim=128
    zdim=8
    narray=np.zeros((128,128,8,6))   
    lines=fp.readlines()
    dumpcount=5
    print("Total lines:%d" % len(lines))
    size=128*128*8
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
    for index in range (128*128*8):
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
        if (index<dumpcount):
            print("i=%d,j=%d,k=%d,u="%(i,j,k),u)
            
    return narray,header
def mode_recog(result_dir="",dst_path="res.txt"):

    totalmodes=1
    mrtname=os.path.join(result_dir,"Mode_Result.txt")
    result=None
    print("Now Processing Path:%s"%result_dir)
    if(os.path.exists(mrtname)):
        print("Found Mode Result")
        fp=open(mrtname)
        lines=fp.readlines()
        lines=lines[1:]
        totalmodes=len(lines)
        print("TOTALMODES:%d"%totalmodes)
        result=np.zeros((totalmodes,4))
        for i in range(0,totalmodes):
            word=lines[i].split()[1]
            if (word=="TM"):
                result[i][0]=0
            elif(word=="TE"):
                result[i][0]=1
            elif(word=="HX"):
                result[i][0]=2

    else:
        print('NO FOUND')
        return None
    oldcwd=os.getcwd()
    os.chdir(result_dir)
    for mode_index in range(totalmodes):
        
        mode_name=mode_index+1
        #判断MNP
        if (result[mode_index][0]==0):
            #print("MODE %d IS TM" % (mode_index))
            mx,my=read_field1D("Mode_%d_EF_M.txt" % mode_name)
            nx,ny=read_field1D("Mode_%d_EF_N.txt" % mode_name)
            px,py=read_field1D("Mode_%d_EF_P.txt" % mode_name)


            #FIND M
            rpc=1
            nmy=np.reshape(np.repeat(np.reshape(my,(1,len(my))),rpc,axis=0),rpc*len(my))
            #print("MY_LEN=%d,NMY_LEN=%d"%(len(my),len(nmy)))
            N=len(nmy)
            fft_y=fft.rfft(my,n=my.size)
            abs_y=np.abs(fft_y)
            freqs = fft.rfftfreq(my.size, d=1./len(my))
            max_freq = freqs[np.argmax(abs_y)]
            result[mode_index][1]=max_freq
            
            #for (mi in range(len(mx)):
                



        elif (result[mode_index][0]==1):
            mx,my=read_field1D("Mode_%d_HF_M.txt" % mode_name)
            nx,ny=read_field1D("Mode_%d_HF_N.txt" % mode_name)
            px,py=read_field1D("Mode_%d_HF_P.txt" % mode_name)

            #FIND M
            rpc=1
            nmy=np.reshape(np.repeat(np.reshape(my,(1,len(my))),rpc,axis=0),rpc*len(my))
            #print("MY_LEN=%d,NMY_LEN=%d"%(len(my),len(nmy)))
            N=len(nmy)
            fft_y=fft.rfft(my,n=my.size)
            abs_y=np.abs(fft_y)
            freqs = fft.rfftfreq(my.size, d=1./len(my))
            max_freq = freqs[np.argmax(abs_y)]
            result[mode_index][1]=max_freq
    os.chdir(oldcwd)
    friendly_print(result)
    #save_result(result,dst_path)
    #save_np_result(result,dst_path)
    return result



def result_stats(result_dir=""):
    curdir=pathlib.Path(result_dir)
    freqs=curdir.glob("MODE_*_Freq.txt")
    flist=list()
    for tx in freqs:
        flist.append(tx)
    statlist=list()
    totalmodes=len(flist)

    
    

    for i in range(1,totalmodes):
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
        fp=open(pt,"r")
        lines=fp.readlines()
        line=lines[0]
        cof=line.split()[1]
        fp.close()

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

    

    uformat="MODE:{}\tType:{}\tFreq:{}\tTEMCoff:{:5f}\tcustType:{}"
    for element in statlist:
        print(uformat.format(*element))
        

    return totalmodes
if __name__ =='__main__':
    #read_mode_batch(r"D:\cst_tools\result")
    ##convert_field_to_nparray(r"D:\cst_tools\result\R_230.000000_L_160.000000")
    #read_field_data_batch(r"D:\cst_tools\result")

    result_stats(result_dir=r"\\172.1.10.232\pillbox_modes")
    