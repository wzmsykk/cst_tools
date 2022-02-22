import cstworker, sfworker
import os
import threading
import queue
from install_compat import resource_path
import pathlib
from typing import List,Dict

from worker import worker

class xmanager(object):
    def __init__(self, gconfm, pconfm, params, logger, maxTask=2):
        super().__init__()

        self.logger = logger
        self.pconfm = pconfm
        self.gconf = gconfm.conf
        self.pconf = pconfm.conf
        self.cstPatternDir = resource_path(self.gconf["BASE"]["datadir"])
        self.currProjectDir = pathlib.Path(pconfm.currProjectDir).absolute()

        tp = pathlib.Path(self.pconf["DIRS"]["tempdir"])
        if tp.is_absolute():
            self.tempPath = tp
        else:
            self.tempPath = self.currProjectDir / tp

        self.taskFileDir = self.tempPath
        if not self.tempPath.exists():
            self.tempPath.mkdir()
        rd = pathlib.Path(self.pconf["DIRS"]["resultdir"])
        if rd.is_absolute():
            self.resultDir = rd
        else:
            self.resultDir = self.currProjectDir / rd

        if not self.resultDir.exists():
            self.resultDir.mkdir()

        ##### CST SPECIFIC SETTINGS
        self.cstProjPath = self.currProjectDir / self.pconf["CST"]["CSTFilename"]
        self.cstType = self.pconf["PROJECT"]["ProjectType"]
        self.paramList = params

        ##### SF SPECIFIC SETTINGS
        ##@##TODO

        # PARALLEL
        self.maxParallelTasks = maxTask
        self.cstWorkerList:List[worker] = []
        self.mthreadList = []
        self.taskQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.startCSTWorkers()
        self.ready = True

    def getResultDir(self):
        return self.resultDir

    def mthread(self, idx):
        # Listener For Each Worker
        while True:
            if self.taskQueue.qsize() != 0:

                mtask = self.taskQueue.get()
                print(mtask)
                iretry_cnt = mtask["retry_cnt"]
                if iretry_cnt < 0:
                    iretry_cnt = 0
                irun_count = iretry_cnt + 1
                while irun_count > 0:
                    
                    if mtask["backend"]=="CST":
                        result = self.cstWorkerList[idx].runWithParam(
                            mtask["pname_list"], mtask["v_list"], mtask["job_name"]
                        )
                        irun_count -= 1
                    elif mtask["backend"]=="Superfish":
                        
                        result = None
                    if result["TaskStatus"] == "Failure":
                        self.logger.warning(
                            "WORKER ID:%s FAILED. RESTARTING CST ENV."
                            % str(self.cstWorkerList[idx].ID)
                        )
                        newWorkerID = self.getMaxAvilCSTWorkerID()
                        nworker = self.createLocalCSTWorker(newWorkerID)
                        if self.cstWorkerList[idx] != None:
                            self.cstWorkerList[idx].__del__()
                        self.cstWorkerList[idx] = nworker
                    else:
                        break
                self.resultQueue.put(result)
            else:
                break

    def createLocalCSTWorker(self, workerID):
        ### Persistant worker
        mconf = {}
        mconf["tempPath"] = str(self.tempPath / ("worker_" + workerID))
        mconf["CSTENVPATH"] = self.gconf["CST"]["cstexepath"]
        mconf["ProjectType"] = self.cstType
        mconf["cstPatternDir"] = str(self.cstPatternDir)
        mconf["resultDir"] = str(self.resultDir)
        mconf["cstPath"] = str(self.cstProjPath)
        mconf["paramList"] = self.paramList
        os.makedirs(mconf["tempPath"], exist_ok=True)
        print(mconf["tempPath"])
        mconf["taskFileDir"] = str(self.taskFileDir / ("worker_" + workerID))
        mconf["postProcess"] = self.pconfm.getCurrPPSList()
        mcstworker_local = cstworker.local_cstworker(
            id=workerID, type="local", config=mconf, logger=self.logger
        )
        return mcstworker_local

    def createLocalSFWorker(self, workerID):
        ### One Time Worker
        mconf = {}
        mconf["tempPath"] = str(self.tempPath / ("worker_" + workerID))
        mconf["SFENVPATH"] = self.gconf["CST"]["cstexepath"]
        mconf["resultDir"] = str(self.resultDir)
        os.makedirs(mconf["tempPath"], exist_ok=True)
        print(mconf["tempPath"])
        mconf["postProcess"] = None  ## No Custom postProcess
        msfworker_local = sfworker.local_superfish_worker(
            id=workerID, type="local", config=mconf, logger=self.logger
        )
        return msfworker_local

    def startCSTWorkers(self):
        workerID = 0
        for i in range(self.maxParallelTasks):
            self.cstWorkerList.append(self.createLocalCSTWorker(str(workerID)))
            print("created cstworker. ID=", workerID)
            workerID += 1

    def getMaxAvilCSTWorkerID(self):
        idlist = [int(worker.ID) for worker in self.cstWorkerList]
        maxid = max(idlist) + 1
        return str(maxid)

    def startListening(self):
        if self.ready == False:
            self.startCSTWorkers()
        for i in range(self.maxParallelTasks):
            ithread = threading.Thread(target=xmanager.mthread, args=(self, i,))
            self.mthreadList.append(ithread)

        for thread in self.mthreadList:
            thread.start()

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

    def addCSTTask(self, param_dict={}, job_name="default", retry_cnt=0):
        mtask = {}

        mtask["pname_list"] = param_dict.keys()
        mtask["v_list"] = param_dict.values()
        mtask["job_name"] = job_name
        mtask["retry_cnt"] = retry_cnt
        mtask["backend"] = "CST"
        self.taskQueue.put(mtask)

    def addSFTask(
        self,
        param_dict=None,
        job_name="default",
        retry_cnt=0,
        sfmodelgen=None,
        sfheadergen=None,
    ):
        mtask = {}

        mtask["param_dict"] = param_dict
        mtask["job_name"] = job_name
        mtask["retry_cnt"] = retry_cnt
        mtask["modelGenerator"] = sfmodelgen
        mtask["headerGenerator"] = sfheadergen
        mtask["backend"] = "Superfish"
        self.taskQueue.put(mtask)

    def addTask(
        self, param_dict={}, job_name="default", retry_cnt=0, workerType="CST", *argc
    ):
        if workerType == "CST":
            self.addCSTTask(param_dict, job_name, retry_cnt)

        elif workerType == "Superfish":
            self.addSFTask(param_dict, job_name, retry_cnt, *argc)

    def runWithx(self, x, job_name):
        self.addCSTTask(value_list=x, job_name=job_name)
        self.startListening()
        self.synchronize()
        result = self.getFirstResult()
        return result

    def runWithParam(self, name_list, value_list, job_name, retry_cnt=0):
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
        self.addCSTTask(
            param_name_list=name_list,
            value_list=value_list,
            job_name=job_name,
            retry_cnt=retry_cnt,
        )
        self.startListening()
        self.synchronize()
        result = self.getFirstResult()
        return result

