from pathlib import Path
from install_compat import resource_path


class sfpostprocess:
    def __init__(self) -> None:

        self.resultDir = None
        self.modelname = "default"
        pass

    def setResultDir(self, rDir):
        self.resultDir = Path(rDir)
    def getResult(self):
        result=self._getResult(self.resultDir / (self.modelname+".SFO"))
        return result
    def _getResult(self,ppsfile):
        qvalue=None
        shunt=None
        freq=None
        powdisp=None
        roq=None
        s_eng=None
        ttf=None
        beta=None
        
        with open(ppsfile,"r") as fp:
            lines=fp.readlines()
            for line in lines:
                #### DIRTY
                if line[0]=="Q" and line[1]==" ":
                    #### get this line!
                    rr=line.split()
                    print(rr)
                    try:
                        qvalue=rr[2]
                        shunt=rr[6]
                    except:
                        pass
                    
                elif line.startswith("Frequency"):
                    rr=line.split()
                    print(rr)
                    try:
                        freq=rr[2]
                    except:
                        pass

                elif line.startswith("Power dissipation"):
                    rr=line.split()
                    try:
                        powdisp=rr[3]
                    except:
                        pass
                    
                elif line.startswith("r/Q"):
                    rr=line.split()
                    try:
                        roq=rr[2]
                    except:
                        pass
                    
                elif line.startswith("Stored energy"):
                    rr=line.split()                    
                    try:
                        s_eng=rr[3]
                    except:
                        pass
                elif line.startswith("Transit-time factor"):
                    rr=line.split()                    
                    try:
                        ttf=rr[3]
                    except:
                        pass
                
                elif line.startswith("Beta"):
                    rr=line.split()                    
                    try:
                        beta=rr[2]
                    except:
                        pass
        
        result={
            "Q":qvalue,
            "shunt_dependence":shunt,
            "frequency":freq,
            "power_dissipation":powdisp,
            "RoverQ":roq,
            "stored_energy":s_eng,
            "TTF":ttf,
            "beta":beta
        }
        return result
    
def test():
    pass

if __name__=="__main__":
    test()