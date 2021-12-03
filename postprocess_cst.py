from pathlib import Path
import json
from collections import OrderedDict, defaultdict

from result import result

class vbpostprocess():
    
    def __init__(self) -> None:

        self.resultDir=None
        self.postProcessDataDir=Path("data/postprocess").absolute()
        self.postProcessDocList=list()
        self.postProcessID=0
        self.ml_tools=None
        pass
    def setResultDir(self,rDir):
        self.resultDir=Path(rDir)
    def reset(self):
        self.resultDir=None
        self.postProcessDocList.clear()
        self.postProcessID=0
    def appendPostProcessSteps(self,pslist):
        for doc in pslist:
            params=doc['params']
            if doc['method']=='R_over_Q':                
                iModeNumber=doc['params']['iModeNumber']
                xoffset=doc['params']['xoffset']
                yoffset=doc['params']['yoffset']
                self.R_over_Q_zaxis(iModeNumber,xoffset,yoffset,doc['resultName'])
            elif doc['method']=='Shunt_Inpedence':
                iModeNumber=doc['params']['iModeNumber']
                xoffset=doc['params']['xoffset']
                yoffset=doc['params']['yoffset']
                self.Shunt_Inpedence_zaxis(iModeNumber,xoffset,yoffset,doc['resultName'])
            elif doc['method']=='Q_Factor':
                iModeNumber=doc['params']['iModeNumber']
                self.Q_Factor(iModeNumber,doc['resultName'])
            elif doc['method']=='Q_Ext':
                iModeNumber=doc['params']['iModeNumber']
                self.Q_Ext(iModeNumber,doc['resultName'])
            elif doc['method']=='Total_Loss':
                iModeNumber=doc['params']['iModeNumber']
                self.Total_Loss(iModeNumber,doc['resultName'])
            elif doc['method']=='Loss_Enclosure':
                iModeNumber=doc['params']['iModeNumber']
                self.Loss_Enclosure(iModeNumber,doc['resultName'])
            elif doc['method']=='Loss_Volume':
                iModeNumber=doc['params']['iModeNumber']
                self.Loss_Volume(iModeNumber,doc['resultName'])
            elif doc['method']=='Loss_Surface':
                iModeNumber=doc['params']['iModeNumber']
                self.Loss_Surface(iModeNumber,doc['resultName'])
            elif doc['method']=='Total_Energy':
                iModeNumber=doc['params']['iModeNumber']
                self.Total_Energy(iModeNumber,doc['resultName'])
            elif doc['method']=='Frequency':
                iModeNumber=doc['params']['iModeNumber']
                self.Frequency(iModeNumber,doc['resultName'])
            elif doc['method']=='Mode_Recog':
                iModeNumber=doc['params']['iModeNumber']
                self.mode_rec(iModeNumber,doc['resultName'])
    def getUsedFileNameList(self):
        namelist=list()
        for doc in self.postProcessDocList:
            namelist.append(doc["resultFilename"])
        return namelist
    def readAllResults(self):
        resultList=[]
        for doc in self.postProcessDocList:
            d={}
            d['id']=doc['id']
            d['resultName']=doc['resultName']
            d['value']=doc['readoutmethod'](doc["resultFilename"])
            d['params']=doc['params']
            resultList.append(d)
        return resultList

    def createPostProcessVBCodeLines(self):
        lst=[]
        importFileList=[]
        for doc in self.postProcessDocList:
            importFile=doc["import"]
            importFileList.append(importFile)
        importFileSet=set(importFileList)
        for vbheaderfileName in importFileSet:
            importFilePath=self.postProcessDataDir/vbheaderfileName
            fp=open(importFilePath,"r")
            for line in fp.readlines():
                lst.append(line)
            lst.append("\n")
        lst.append("\nSub CustomPostProcess\n")
        for doc in self.postProcessDocList:
            funcString="    "+doc['funcString']
            lst.append(funcString)
        lst.append("End Sub\n")
        return lst
    def readFile(self,path):
        d={}
        fp=open(path,"r")
        lines=fp.readlines()
        expect="Name"
        k=""
        v=""
        for line in lines:
            if not line.strip():
                continue
            if expect=="Name":            
                k=str(line).strip()
                expect="Value"
            elif expect=="Value":
                v=str(line).strip()
                d.update({k:v})
                expect="Name"
        return d

    def R_over_Q_zaxis(self,iModeNumber,xoffset,yoffset,resultName):
        
        
        
        resultFilename="Mode_%d_ROQ_xoffset_%f_yoffset_%f_%s.txt" % (iModeNumber,xoffset,yoffset,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():            
            resultFilename="Mode_%d_ROQ_xoffset_%f_yoffset_%f_%s_%d.txt"% (iModeNumber,xoffset,yoffset,str(resultName),i)
        
        #iModeNumber As Integer,queryKey As String,axis As Integer,xoffset As Double,yoffset As Double,zoffset As Double, outputPath As String
        funcString="EigenResult_Complex_output({iMode},\"R over Q\",3,{xoffset},{yoffset},0,outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),xoffset=str(xoffset),yoffset=str(yoffset),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
            "xoffset":xoffset,
            "yoffset":yoffset
        })

        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Complex.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.R_over_Q_zaxis_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def R_over_Q_zaxis_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
        
        pass
    def Shunt_Inpedence_zaxis(self,iModeNumber,xoffset,yoffset,resultName):
       
        
        resultFilename="Mode_%d_SI_xoffset_%f_yoffset_%f_%s.txt" % (iModeNumber,xoffset,yoffset,str(resultName))
        i=0

        while resultFilename in self.getUsedFileNameList():            
            resultFilename="Mode_%d_SI_xoffset_%f_yoffset_%f_%d.txt"% (iModeNumber,xoffset,yoffset,str(resultName),i)
        funcString="EigenResult_Complex_output({iMode},\"Shunt Inpedence\",3,{xoffset},{yoffset},0,outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),xoffset=str(xoffset),yoffset=str(yoffset),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
            "xoffset":xoffset,
            "yoffset":yoffset
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Complex.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Shunt_Inpedence_zaxis_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1
    
    def Shunt_Inpedence_zaxis_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])

    def Q_Factor(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Q_Factor_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Q_Factor_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Q-Factor\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Q_Factor_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Q_Factor_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
    def Q_Ext(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Q_Ext_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Q_Ext_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Q_Ext\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Q_Ext_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Q_Ext_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
    def Frequency(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Frequency_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Frequency_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Frequency\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Frequency_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Frequency_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
    def Total_Loss(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Total_Loss_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Total_Loss_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Total Loss\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Total_Loss_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Total_Loss_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
    def Loss_Enclosure(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Loss_Enclosure_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Loss_Enclosure_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Loss_Enclosure\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Loss_Enclosure_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Loss_Enclosure_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
    def Loss_Volume(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Loss_Volume_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Loss_Volume_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Loss_Volume\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Loss_Volume_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Loss_Volume_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])

    def Loss_Surface(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Loss_Surface_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Loss_Surface_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Loss_Surface\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Loss_Surface_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Loss_Surface_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
    def Total_Energy(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Total_Energy_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Total_Energy_%s_%d.txt" % (iModeNumber,str(resultName),i)
        funcString="EigenResult_Simple_output({iMode},\"Total Energy\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.Total_Energy_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1

    def Total_Energy_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        d=self.readFile(rpath)
        return float(d['value'])
    def mode_rec(self,iModeNumber,resultName):
        resultFilename="Mode_%d_Mode_Info_%s.txt" % (iModeNumber,str(resultName))
        i=0
        while resultFilename in self.getUsedFileNameList():  
            resultFilename="Mode_%d_Mode_Info_%s_%d.txt" % (iModeNumber,str(resultName),i)
        #TODO
        funcString="EigenResult_Simple_output({iMode},\"Total Energy\",outFullDir,\"{rFilename}\")\n".format(iMode=str(iModeNumber),rFilename=str(resultFilename))
        
        paramdoc={}
        paramdoc.update({
            "iModeNumber":iModeNumber,
        })
        doc=dict()
        doc.update({"id":self.postProcessID})
        doc.update({"import":"EigenResult_Simple.vb"})
        doc.update({"resultName":resultName})
        doc.update({"resultFilename":resultFilename})
        doc.update({"funcString":funcString})
        doc.update({"readoutmethod":self.mode_rec_readout})
        doc.update({"params":paramdoc})
        self.postProcessDocList.append(doc)
        self.postProcessID+=1
    def mode_rec_readout(self,resultFilename):
        rpath=self.resultDir / resultFilename
        #d=self.readFile(rpath)
        #init torch
        return float(d['value'])

if __name__=='__main__':
    vbp=vbpostprocess()
    import json
    fp=open("template/defaultPPS.json","r")
    r=json.load(fp)
    
    vbp.appendPostProcessSteps(r)
    fp=open("temp/a.txt","w")
    list=vbp.createPostProcessVBCodeLines()
    for line in list:
        fp.write(line)
    fp.close()
    dir=Path(r"project\HOM analysis\result\frequency000000_700_800")
    vbp.setResultDir(dir)
    # aa=vbp.readFile(dir/"Mode_1_ROQ_xoffset_0.000000_yoffset_0.000000_ROQ.txt")
    # print(aa)
    # bb=vbp.Q_Factor_readout("Mode_1_Q_Factor_Q.txt")
    # print(bb)
    import numpy as np
    cc=vbp.readAllResults()
    print(np.array(cc))

