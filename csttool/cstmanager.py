from . import cstworker
import os
import threading
import queue
from install_compat import resource_path
import pathlib
import logging
from time import sleep


class manager(object):
    def __init__(self, gconfm, pconfm, params, logger=None, maxTask=2):
        super().__init__()
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
        self.pconfm = pconfm
        self.gconf = gconfm.conf
        self.pconf = pconfm.conf
        self.cstPatternDir = resource_path(self.gconf["BASE"]["datadir"])
        self.currProjectDir = pathlib.Path(pconfm.currProjectDir).absolute()

        tp = pathlib.Path(self.pconf["DIRS"]["tempdir"])
        if tp.is_absolute():
            self.tempDir = tp
        else:
            self.tempDir = self.currProjectDir / tp

        self.taskFileDir = self.tempDir
        if not self.tempDir.exists():
            self.tempDir.mkdir()
        rd = pathlib.Path(self.pconf["DIRS"]["resultdir"])
        if rd.is_absolute():
            self.resultDir = rd
        else:
            self.resultDir = self.currProjectDir / rd

        if not self.resultDir.exists():
            self.resultDir.mkdir()
        self.cstProjPath = self.currProjectDir / self.pconf["CST"]["CSTFilename"]
        self.cstType = self.pconf["PROJECT"]["ProjectType"]
        self.paramList = params

        # PARALLEL
        self.maxParallelTasks = maxTask
        self.cstWorkerList:list[cstworker.local_cstworker] = [] 
        self.cstWorkerStatus:list = [] #"ALIVE" "DEAD"
        self.WorkerListMutex=threading.Lock()
        self.mthreadList:list[threading.Thread] = []
        self.taskQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.startFirstWorkers()
        self.ready = True

    def getResultDir(self):
        return self.resultDir
    def mthread(self, idx):
        # Listener For Each Worker
        while True:
            targetWorker=self.cstWorkerList[idx]
            if self.cstWorkerStatus=="DEAD":
                break
            if self.taskQueue.qsize() != 0:                
                mtask = self.taskQueue.get()
                self.logger.debug("WORKER:%s, Received Task:%s"%(targetWorker.ID,str(mtask)))
                iretry_cnt = mtask["retry_cnt"]
                if iretry_cnt < 0:
                    iretry_cnt = 0
                irun_count = iretry_cnt + 1
                while irun_count > 0:
                    result = targetWorker.runWithParam(
                        resultname= mtask["job_name"],params=mtask["params"]
                    )
                    irun_count -= 1
                    if result["TaskStatus"] == "Failure":
                        self.logger.warning(
                            "WORKER ID:%s FAILED. RESTARTING CST ENV."
                            % str(targetWorker.ID)
                        )
                        newWorkerIndexInList = self.addNewLocalWorkerToList()
                        nworker = self.cstWorkerList[newWorkerIndexInList]
                        oldWorkerIndexInList = idx
                        if targetWorker != None:
                            self.killLocalWorkerFromList(oldWorkerIndexInList)
                        targetWorker = nworker
                        idx = newWorkerIndexInList
                    else:
                        break
                self.resultQueue.put(result)
            else:
                break

    def createLocalWorker(self, workerID):
        workerID_str=str(workerID)
        mconf = {}
        mconf["tempDir"] = str(self.tempDir / ("worker_" + workerID_str))
        mconf["CSTENVPATH"] = self.gconf["CST"]["cstexepath"]
        mconf["ProjectType"] = self.cstType
        mconf["cstPatternDir"] = str(self.cstPatternDir)
        mconf["resultDir"] = str(self.resultDir)
        mconf["cstPath"] = str(self.cstProjPath)
        mconf["paramList"] = self.paramList
        os.makedirs(mconf["tempDir"], exist_ok=True)
        self.logger.debug("WORKERID:%s, Temp Dir:%s"%(workerID_str, mconf["tempDir"]))
        mconf["taskFileDir"] = str(self.taskFileDir / ("worker_" + workerID_str))
        mconf["postProcess"] = self.pconfm.getCurrPPSList()
        mcstworker_local = cstworker.local_cstworker(
            id=workerID_str, type="local", workerconfig=mconf, logger=self.logger
        )
        return mcstworker_local
    def addNewLocalWorkerToList(self):
        self.WorkerListMutex.acquire()
        avilid=self.getMaxAvilWorkerID()
        self.cstWorkerList.append(self.createLocalWorker(avilid))
        self.cstWorkerStatus.append("ALIVE")
        listindex=len(self.cstWorkerList)-1
        self.WorkerListMutex.release()
        return listindex
    def killLocalWorkerFromList(self,index):
        self.WorkerListMutex.acquire()
        self.cstWorkerStatus[index]="DEAD"
        self.cstWorkerList[index].__del__()
        self.WorkerListMutex.release()
        return
    def startFirstWorkers(self):
        workerID = 0
        for i in range(self.maxParallelTasks):
            newWorker=self.createLocalWorker(workerID)
            self.WorkerListMutex.acquire()
            self.cstWorkerList.append(newWorker)
            self.cstWorkerStatus.append("ALIVE")
            self.WorkerListMutex.release()
            self.logger.info("Created cstworker. ID=%s", str(workerID))
            workerID += 1

    def getMaxAvilWorkerID(self):
        idlist = [int(worker.ID) for worker in self.cstWorkerList]
        maxid = max(idlist) + 1
        return str(maxid)


    def startProcessing(self):
        if self.ready == False:
            self.startFirstWorkers()
        #self.logger.debug("WorkerListLength:%s"%len(self.cstWorkerList))
        for i in range(len(self.cstWorkerList)):
            self.logger.debug("index:%s,Status:%s"%(i,self.cstWorkerStatus[i]))
            if self.cstWorkerStatus[i] == "ALIVE":
                
                ithread = threading.Thread(target=manager.mthread, args=(self, i,))
                self.mthreadList.append(ithread)

        for thread in self.mthreadList:
            thread.start()
        for thread in self.mthreadList:
            thread.join()
        self.mthreadList = []
        
    def stop(self):
        for iworker in self.cstWorkerList:
            ithread = threading.Thread(target=iworker.stop)
            ithread.start()
        for iworker in self.cstWorkerList:
            ithread.join()
        with self.taskQueue.mutex:
            self.taskQueue.queue.clear()
        with self.resultQueue.mutex:
            self.resultQueue.queue.clear()
        self.cstWorkerList.clear()
        self.mthreadList.clear()
        self.ready = False
        self.logger.info("MANAGER 终止结束")

    def synchronize(self):
        # WAIT UNTIL ALL TASK FINISHED
        for thread in self.mthreadList:
            thread.join()
        self.mthreadList = []

    def getFullResults(self):
        mlist = []
        for i in range(self.resultQueue.qsize()):
            mlist.append(self.resultQueue.get())
        return mlist

    def getFirstResult(self):
        return self.resultQueue.get()

    def addTask(
        self, params:dict, job_name:str, retry_cnt:int=0
    ):
        mtask = {}
        mtask["params"] = params
        mtask["job_name"] = job_name
        mtask["retry_cnt"] = retry_cnt
        self.taskQueue.put(mtask)

    def runWithx(self, x, job_name):
        self.addTask(value_list=x, job_name=job_name)
        self.startProcessing()
        self.synchronize()
        result = self.getFirstResult()
        return result

    def runWithParam(self, params, job_name, retry_cnt=0):
        """提供参数列表运行CST  (阻塞)
            run with user provided parameters (Synchronized)

        Paramaters
        ----------
        params : dict
            A dict of Param name/value pairs

        job_name : string 
            User defined job name for this run.

        Returns
        -------
        result : list
            A list of Run results.

        """
        self.addTask(
            params=params,
            job_name=job_name,
            retry_cnt=retry_cnt,
        )
        self.startProcessing()
        self.synchronize()
        result = self.getFirstResult()
        return result