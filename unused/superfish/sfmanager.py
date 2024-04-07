from sqlalchemy import true
import sfworker
import os
import threading
import queue
from install_compat import resource_path
import json

import logging
import os
import threading
import queue
from install_compat import resource_path
from pathlib import Path




class manager(object):
    def __init__(self, workdir,sfenvpath, maxTask=2, logger=None):
        if logger is None:        
            self.logger = logging.getLogger("SFManager")
        else:
            self.logger=logger
        self.workdir=workdir

        # PARALLEL
        self.maxParallelTasks = maxTask
        self.workerList = [None for _ in range(maxTask)]
        self.workerListLock=threading.Lock()
        self.mthreadList = []
        self.taskQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.ready = True
        self.sfenvpath=sfenvpath

    def mthread(self, idx):
        # Listener For Each Worker
        while True:
            if self.taskQueue.qsize() != 0:
                mtask = self.taskQueue.get()
                #print(mtask)
                iretry_cnt = mtask.get("retry_cnt",0)
                job_config=mtask.get("job_config",None)
                if iretry_cnt < 0:
                    iretry_cnt = 0
                irun_count = iretry_cnt + 1
                while irun_count > 0:
                    self.workerListLock.acquire()
                    self.workerList[idx]=self.createLocalWorker(self.getMaxAvilWorkerID(),job_config)
                    self.workerListLock.release()
                    result = self.workerList[idx].run()
                    irun_count -= 1
                    if result["TaskStatus"] == "Failure":
                        self.logger.warning(
                            "WORKER ID:%s FAILED. RESTARTING SF WORKER."
                            % str(self.workerList[idx].ID)
                        )
                        job_config=self.workerList[idx].config                     
                        if self.workerList[idx] != None:
                            self.workerList[idx].__del__()
                        continue
                    else:
                        break
                self.resultQueue.put(result)
            else:
                break
    def addTask(self,job_config):
        task_config={
            "retry_cnt":0,
            "job_config":job_config
        }
        self.taskQueue.put(task_config)
        
    def getMaxAvilWorkerID(self):
        idlist = [int(worker.ID) for worker in self.workerList if worker is not None]
        if len(idlist)<=0:
            return str(0)        
        maxid = max(idlist) + 1
        return str(maxid)
    def createLocalWorker(self, workerID,job_config):
        worker_op_path=Path(self.workdir) / str(workerID)
        worker_op_path.mkdir(exist_ok=True)
        dump_final_config_path=worker_op_path/ "config.json"
        final_config={
            "job_info":{
                "type":"run"
            },
            "workdir":str(worker_op_path),
            "input_macro":None,
            "SFENVPATH":self.sfenvpath
        }
        
        final_config.update(job_config)

        with open(dump_final_config_path,"w") as fp:
            json.dump(final_config,fp,indent=4)
        mworker_local = sfworker.local_superfish_worker(
            id=workerID, type="superfish", config=final_config, logger=self.logger
        )
        return mworker_local


    def startListening(self):
        for i in range(self.maxParallelTasks):
            ithread = threading.Thread(target=manager.mthread, args=(self, i,))
            self.mthreadList.append(ithread)

        for thread in self.mthreadList:
            thread.start()

    def stop(self):
        for iworker in self.workerList:
            ithread = threading.Thread(target=iworker.stop)
            ithread.start()
        for iworker in self.workerList:
            ithread.join()
        with self.taskQueue.mutex:
            self.taskQueue.queue.clear()
        with self.resultQueue.mutex:
            self.resultQueue.queue.clear()
        self.workerList.clear()
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


