from os.path import split
import numpy as np
import matplotlib.pyplot as plt
import numpy.fft as fft
import os
from numpy.lib.shape_base import kron
from scipy.signal import find_peaks
import glob
import numpy as np
def read_file(filename):
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

    x=np.array(xl)
    y=np.array(yl)
    fp.close()
    return x,y
def read_mode_batch(resultdir):

    curr_R=None
    curr_L=None
    p = os.path.join(resultdir,"R_*_L_*")
    dirlist=glob.glob(p)
    for dir in dirlist:
        dir_name=os.path.split(dir)[1]
        mode_recog(dir,"Mode_result_%s.txt" % dir_name)


    


    pass

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
    for mode_index in range(totalmodes):
        mode_name=mode_index+1
        epath=os.path.join(result_dir,"Mode%dEField.txt"%mode_name)
        hpath=os.path.join(result_dir,"Mode%dHField.txt"%mode_name)
        efield=read_field(epath)
        hfield=read_field(hpath)
        np.save("%s_Mode%dEField.npy"%(export_name,mode_name),efield)
        np.save("%s_Mode%dHField.npy"%(export_name,mode_name),hfield)


    pass
def read_field(filepath):
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
            
    return narray
def mode_recog(result_dir="",dst_path="res.txt"):
    TM=False
    TE=False
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
            mx,my=read_file("Mode_%d_EF_M.txt" % mode_name)
            nx,ny=read_file("Mode_%d_EF_N.txt" % mode_name)
            px,py=read_file("Mode_%d_EF_P.txt" % mode_name)


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
            mx,my=read_file("Mode_%d_HF_M.txt" % mode_name)
            nx,ny=read_file("Mode_%d_HF_N.txt" % mode_name)
            px,py=read_file("Mode_%d_HF_P.txt" % mode_name)

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
    save_result(result,dst_path)

if __name__ =='__main__':
    #read_mode_batch(r"D:\cst_tools\result")
    read_field_data_batch(r"D:\cst_tools\result")