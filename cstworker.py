import os,json,re,copy,sys,shutil
import result
import numpy as np
import time
import subprocess
import logging
import hashlib
import pathlib
import worker
import postprocess_cst


class local_cstworker(worker.worker):
    def __init__(self,id,type,config,logger):
        super().__init__(id,type,config,logger)
        
        #configs
        #cstType,cstPatternDir,tempDir,taskFileDir,resultDir,cstPath
        self.cstType=config['ProjectType']
        self.cstPatternDir=pathlib.Path(config['cstPatternDir'])
        self.tempDir=pathlib.Path(config['tempPath'])
        self.taskFileDir=pathlib.Path(config['taskFileDir'])
        self.resultDir=pathlib.Path(config['resultDir'])
        self.cstProjPath=pathlib.Path(config['cstPath'])
        
        self.paramList=copy.deepcopy(config['paramList'])
        self.postProcessSetList=config['postProcess']
        self.postProcessHelper=postprocess_cst.vbpostprocess()
        self.taskIndex=0
        self.cstStatus='off'
        self.maxWaitTime=999999
        self.maxStopWaitTime=60
        self.cstProcess=None
        self.cstlog=None

        
        
        #LOGGING#

        self.logger.info("TempDir:%s"%str(self.tempDir))
        self.logger.info("TaskFileDir:%s"%str(self.taskFileDir))

        #FINDCST
        self.currentCSTENVPATH=config['CSTENVPATH']

        ##INIT##

        cstPatternName=self.cstType+".pattern"
        cstPatternPath=self.cstPatternDir / cstPatternName
        if not cstPatternPath.exists():
            
            self.logger.error("pattern not found for %s"%self.cstType)
            self.logger.error("pattern should be in %s "% str(cstPatternPath))
            raise FileNotFoundError
        headerFilePath=self.cstPatternDir / "worker.vb"
        

        ##COPY cstProj TO TEMP

        self.tmpCstFilePath=self.tempDir / "cstproj.cst"

            ##IF tmpCstFile EXISTS, CHECK FILE MD5
        if self.tmpCstFilePath.exists():
            md5srcfile=self.getFileMD5(self.cstProjPath)
            md5dstfile=self.getFileMD5(self.tmpCstFilePath)
            if not (md5srcfile==md5dstfile):
                self.logger.warning("CstProjectFile is not consistent with the one in temp.")
                self.clearall3()    
                shutil.copyfile(src=self.cstProjPath,dst=self.tmpCstFilePath)            
        else:
            shutil.copyfile(src=self.cstProjPath,dst=self.tmpCstFilePath)
        
        mainBatchFilePath=self.createMainCSTbatch(headerFilePath,cstPatternPath)
        self.startCSTenv(mainBatchFilePath)



    def getFileMD5(self,filePath):
        with open(filePath, "rb") as fp:
            md5obj = hashlib.md5()
            md5obj.update(fp.read())
            file_md5 = md5obj.hexdigest()
            return file_md5

    def clearall3(self):
        if (self.taskFileDir.exists()):
            shutil.rmtree(self.taskFileDir)
            self.taskFileDir.mkdir()
        if (self.resultDir.exists()):
            shutil.rmtree(self.resultDir)
            self.resultDir.mkdir()
        if (self.tempDir.exists()):
            shutil.rmtree(self.tempDir)
            self.tempDir.mkdir()
        self.logger.info("Worker_(%s):old runfile removed"% self.ID)



    def startCSTenv(self,mainbatchpath):
        cstlogPath=self.tempDir / "cst.log"
        self.cstlog=open(cstlogPath,"wb",buffering=0)
        command ="start cmd /k "+"\""+self.currentCSTENVPATH + "\"" +" -m "+ str(mainbatchpath)
        command2 = "\""+self.currentCSTENVPATH + "\"" +" -m " + "\"" + str(mainbatchpath) + "\""
        if self.cstStatus=='off':
            #command2="start cmd /k "+"\""+batFilePath+"\""
            self.logger.info(command2)
            self.cstProcess=subprocess.Popen(command2, stdout=self.cstlog, stderr=self.cstlog,shell=True)
            self.logger.info(self.cstProcess)
            self.cstStatus ='on'

    def stopWork(self):
        oFilePath=self.taskFileDir / "terminate.txt"
        file=open(oFilePath,"w")
        file.close()
        self.cstStatus=='off'
        self.taskIndex=0

    def sendTaskFile(self,paramname_list,value_list,run_name):
        tf=self.taskFileDir / (str(self.taskIndex)+'.txt')
        full_param_list=copy.deepcopy(self.paramList)
        if (len(paramname_list)==0 and len(value_list)>0) :
            for i in range(min(len(full_param_list),len(value_list))):
                full_param_list[i]['value']=value_list[i]
        elif (len(paramname_list)>0 and len(value_list)>0):
            for i in range(len(paramname_list)):
                for idict in full_param_list:
                    if(idict["name"]==paramname_list[i]):
                        idict.update({"value":value_list[i]}) 
        f1=open(tf,"w")
        f1.write(run_name+'\n')    

        for i in range(len(full_param_list)):
            f1.write(str(full_param_list[i]['name'])+'\n')
            f1.write(str(full_param_list[i]['value'])+'\n')
        f1.close()
    

    def createMainCSTbatch(self,hFilePath,mFilePath):
        oFilePath=self.tempDir/"main.bas"
        
        ###saveVBConfigs
        cFilePath=self.tempDir/"configs.txt"
        file_c=open(cFilePath,'w')
        file_c.write(self.cstType+'\n')
        file_c.write(str(self.resultDir.absolute())+'\n')
        file_c.write(str(self.tmpCstFilePath.absolute())+'\n')
        file_c.write(str(self.taskFileDir.absolute())+'\n')
        file_c.close()

        ###
        file_1 = open(hFilePath,'r', encoding='utf-8') #worker.vb
        file_2 = open(mFilePath,'r', encoding='utf-8') #PROJECT TYPE SPECIFIC.vb
        list1 = []
        for line in file_1.readlines():
            ssd=line
            ssd=re.sub('\'EXTERN\'','',ssd)
            ssd=re.sub('%CONFIGFILEPATH%',str(cFilePath.absolute()).replace('\\','\\\\'),ssd)
            list1.append(ssd)
        file_1.close()
        list2 = []
        for line in file_2.readlines():
            ss=line
            list2.append(ss)
        file_2.close()
        file_new = open(oFilePath,'w')
        for i in range(len(list1)):
            file_new.write(list1[i])
        for i in range(len(list2)):
            file_new.write(list2[i])
        
        ##POST PROCESS        
        self.postProcessHelper.appendPostProcessSteps(self.postProcessSetList)
        list3=self.postProcessHelper.createPostProcessVBCodeLines() #POSTPROCESS.vb.
        for i in range(len(list3)):
            file_new.write(list3[i])
        ##POST PROCESS ENDS
        file_new.close()
        return oFilePath

    def change_uvalue(self,u_param_list,u_value_list):
        self.u_param_list=u_param_list
        self.u_value_list=u_value_list

    

    def run(self):
        if self.cstStatus=='off':
            raise BaseException
        pathc = self.resultDir / self.runName
        self.postProcessHelper.setResultDir(pathc.absolute())
        #WAIT RESULTS
        flagPath=self.taskFileDir / (str(self.taskIndex)+".success")
        if flagPath.exists():
            self.logger.info("WorkerID:%r Run:%r Name:%r Already Finished."%(self.ID,self.taskIndex,self.runName))
        else:
            self.sendTaskFile(self.u_param_list,self.u_value_list,self.runName)
            
            
            waitTime=0
            startTime=time.time()
            self.logger.info("WorkerID:%r Run:%r Name:%r started."%(self.ID,self.taskIndex,self.runName))
            self.logger.info("Start Time:%r"% time.ctime())
            while not flagPath.exists():
                #ADD process check HERE
                rcode =self.cstProcess.poll()
                if rcode is None:
                    pass
                    
                else:
                    self.logger.error("CST ENV stopped")
                    self.logger.error("WORKER FINISHED")
                    runResult={'TaskIndex':self.taskIndex,'TaskStatus':'Failure','RunName':self.runName,'PostProcessResult':None}
                    return runResult
                    #os._exit(0)
                time.sleep(1)
                currentTime=time.time()
                escapedTime=currentTime-startTime
                if (escapedTime>self.maxWaitTime):
                    raise TimeoutError
                
            
            self.logger.info("WorkerID:%r Run:%r Name:%r success."%(self.ID,self.taskIndex,self.runName))
            self.logger.info("ElapsedTime:%r"%escapedTime)
            self.logger.info("End Time:%r"%time.ctime())
        self.taskIndex+=1
        postProcessResult=self.postProcessHelper.readAllResults()
        runResult={'TaskIndex':self.taskIndex,'TaskStatus':'Success','RunName':self.runName,'PostProcessResult':postProcessResult}
        #runResult=result.readModeResult(pathc,1)
        return runResult

    def stop(self):
        self.logger.info("Stopping CST, Please Wait")
        secs=0
        if not self.cstlog is None:
            self.cstlog.close()
        rcode =self.cstProcess.poll()
        if rcode is None:
            self.stopWork()
        while secs<self.maxStopWaitTime :
            rcode =self.cstProcess.poll()
            if rcode is None:
                time.sleep(1)
                secs+=1
                self.logger.info("%r secs"%(secs))
            else:
                self.logger.info("Stop success")
                return True
        self.logger.error("failed to stop cst, try killing the process.")
        self.kill()
        time.sleep(10)
        if not self.cstProcess is None:
            self.logger.warning("cst killed.")
            return True
        else:
            self.logger.error("killing failed")
            return False

    def kill(self):
        if not self.cstlog is None:
            self.cstlog.close()
        if self.cstProcess is None:
            self.cstProcess.kill()
    
    def __del__(self):
        self.kill()
    def start(self):
        self.run()



