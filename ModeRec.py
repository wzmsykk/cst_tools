from utils import mode_util_sample
from utils.mode_util_base import read_coffs,result_stats
from matplotlib import pyplot as plt
x=[]
y=[]
xclean=[]
y020=[]
y110=[]
ye111=[]
for L in range (60,130,10):
    fdir=r"F:\Project\EigenModeRecg\L%d\ResultFirst10"%L
    slist=result_stats(fdir)
    for mode in slist:
        x.append(float(L))
        y.append(float(mode[2]))
    index020=mode_util_sample.findTM020index(fdir)
    index110=mode_util_sample.findTM110index(fdir)
    indexe111=mode_util_sample.findTE111index(fdir)
    print(indexe111)
    xclean.append(L)
    y020.append(float(slist[index020-1][2]))
    y110.append(float(slist[index110-1][2]))
    ye111.append(float(slist[indexe111-1][2]))
    
plt.scatter(x=x,y=y,s=10)
plt.xlabel("L")
plt.ylabel("freq")
plt.plot(xclean,y020,label="TM020")
plt.plot(xclean,y110,label="TM110")
plt.plot(xclean,ye111,label="TE111")
plt.legend()
plt.show()

for L in range (60,130,10):
    fdir=r"F:\Project\EigenModeRecg\L%d\ResultFirst10"%L
    for id in range(1,11):
        print(L,mode_util_sample.mode_type_final2(fdir,id))