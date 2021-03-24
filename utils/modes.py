import numpy as np
import matplotlib.pyplot as plt
import numpy.fft as fft
from scipy.signal import find_peaks
import os
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
def read_mode(mid):
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
        
def mode_recog():
    TM=False
    TE=False
    totalmodes=1
    mrtname="Mode_Result.txt"
    result=None
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
        
    friendly_print(result)

mode_recog()