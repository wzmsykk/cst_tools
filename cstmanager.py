import cstworker
import time,os
import threading
import queue
import copy
import pathlib

class manager(object):
    def __init__(self,gconfm,pconfm,params,logger,maxTask=2):
        super().__init__()
        
        self.logger=logger
        self.gconf=gconfm.conf
        self.pconf=pconfm.conf
        self.cstPatternDir=pathlib.Path(self.gconf['BASE']['datadir']).absolute()
        self.currProjectDir=pathlib.Path(pconfm.currProjectDir).absolute()

        tp=pathlib.Path(self.pconf['DIRS']['tempdir'])
        if tp.is_absolute():
            self.tempPath=tp
        else:
            self.tempPath=self.currProjectDir / tp

        self.taskFileDir=self.tempPath
        if not self.tempPath.exists():
            self.tempPath.mkdir()
        rd=pathlib.Path(self.pconf['DIRS']['resultdir'])
        if rd.is_absolute():
            self.resultDir=rd
        else:
            self.resultDir=self.currProjectDir / rd

        if not self.resultDir.exists():
            self.resultDir.mkdir()
        self.cstProjPath=self.currProjectDir / self.pconf['CST']['CSTFilename']
        self.cstType=self.pconf['PROJECT']['ProjectType']
        self.paramList=params

        
        #PARALLEL
        self.maxParallelTasks=maxTask
        self.cstWorkerList=[]
        self.mthreadList=[]
        self.taskQueue=queue.Queue()
        self.resultQueue=queue.Queue()
        self.startWorkers()
        self.ready=True
    
    def getResultDir(self):
        return self.resultDir

    def mthread(self,idx):
        #Listener For Each Worker
        while True:
            if (self.taskQueue.qsize()!=0):

                mtask=self.taskQueue.get()
                print(mtask)
                resultvalue=self.cstWorkerList[idx].runWithParam(mtask['pname_list'],mtask['v_list'],mtask['job_name'])
                result={}
                result['value']=resultvalue
                result['name']=mtask['job_name']
                self.resultQueue.put(result)
            else:
                break
            



    def createLocalWorker(self,workerID):
        mconf={}
        mconf['tempPath']=str(self.tempPath / ("worker_"+workerID))
        mconf['CSTENVPATH']=self.gconf['CST']['cstexepath']
        mconf['ProjectType']=self.cstType
        mconf['cstPatternDir']=str(self.cstPatternDir)
        mconf['resultDir']=str(self.resultDir)
        mconf['cstPath']=str(self.cstProjPath)
        mconf['paramList']=self.paramList
        os.makedirs(mconf['tempPath'],exist_ok=True)
        print(mconf['tempPath'])
        mconf['taskFileDir']=str(self.taskFileDir/("worker_"+workerID))
        mcstworker_local=cstworker.local_cstworker(id=workerID, type="local",config=mconf,logger=self.logger)
        return mcstworker_local
    def startWorkers(self):
        workerID=0
        for i in range(self.maxParallelTasks):            
            self.cstWorkerList.append(self.createLocalWorker(str(workerID)))
            print("created cstworker. ID=",workerID)
            workerID+=1
    def startListening(self):
        if self.ready==False:
            self.startWorkers()
        for i in range(self.maxParallelTasks):
            ithread=threading.Thread(target=manager.mthread,args=(self,i,))
            self.mthreadList.append(ithread)

        for thread in self.mthreadList:
            thread.start()
    def stop(self):
        for iworker in self.cstWorkerList:
            ithread=threading.Thread(target=iworker.stop)
            ithread.start()
        for iworker in self.cstWorkerList:
            ithread.join()
        with self.taskQueue.mutex:
            self.taskQueue.queue.clear()
        with self.resultQueue.mutex:
            self.resultQueue.queue.clear()
        self.cstWorkerList.clear()
        self.mthreadList.clear()
        self.ready=False
        self.logger.info('MANAGER 终止结束')
        

    def synchronize(self):
        #WAIT UNTIL ALL TASK FINISHED
        for thread in self.mthreadList:
            thread.join()
        self.mthreadList=[]

    def getFullResults(self):
        mlist=[]
        for i in range(self.resultQueue.qsize()):
            mlist.append(self.resultQueue.get())
        return mlist

    def getFirstResult(self):
        return self.resultQueue.get()
    def addTask(self,param_name_list=[],value_list=[],job_name="default"):
        mtask={}
        mtask['pname_list']=param_name_list
        mtask['v_list']=value_list
        mtask['job_name']=job_name
        self.taskQueue.put(mtask)

    def runWithx(self,x,job_name):
        self.addTask(value_list=x,job_name=job_name)
        self.startListening()
        self.synchronize()
        result=self.getFirstResult()
        return result['value']

    
    def runWithParam(self,name_list,value_list,job_name):
        """提供参数列表运行CST  (阻塞)
            run with user provided parameters (Synchronized)

        Paramaters
        ----------
        name_list : list 
            A list of Parameter names.

        value_list : list
            A list of Parameter values.

        job_name : string 
            User defined job name for this run.

        Returns
        -------
        result : list
            A list of Run results.

        """
        self.addTask(param_name_list=name_list, value_list=value_list,job_name=job_name)
        self.startListening()
        self.synchronize()
        result=self.getFirstResult()
        return result['value']

