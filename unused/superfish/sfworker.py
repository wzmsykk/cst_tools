from pathlib import Path

import json
import worker
import time
import unused.superfish.postprocess_sf as postprocess_sf
import subprocess

class local_superfish_worker(worker.worker):
    def __init__(self, id:int, type="superfish", config:dict={}, logger=None):
        super().__init__(id, type=type, config=config, logger=logger)
        ## configs
        self.config=config
        self.job_info = self.config.get("job_info",None)
        self.workDir = Path(self.config.get("workdir",""))
        self.input_macro = self.config.get("input_macro",[]) ###Main macro of .sf
        
        # LOGGING#
        self.logger.info("LOCAL POISSON SUPERFISH WORKER ID:%s" % str(id))
        self.logger.info("WorkDir:%s" % str(self.workDir.absolute()))
        #self.logger.info("TaskFileDir:%s" % str(self.taskFileDir))
        
        # FINDSF
        self.currentSFENVPATH = Path(self.config["SFENVPATH"])
        self.postProcessHelper= postprocess_sf.sfpostprocess()

        self.outname="run" +".log"
        self.outpath=self.workDir / (self.outname)
        self.maxWaitTime=999999
        self.sfProcess=None
        self.sfFileName="MAIN.SF"
    def startSF(self, sfbatchpath):
        command = (
            "start cmd /k "
            + str(sfbatchpath)
        )
        self.logger.info(command)
        self.sfProcess = subprocess.Popen(
            str(sfbatchpath),shell=False
        )
        self.logger.info(self.sfProcess)
        

    def createMainBatch(self,run_name):
        bFilePath= self.workDir / "mainsf.bat"
        sfFilePath= self.workDir / self.sfFileName

        autofishpath_str=str(self.currentSFENVPATH / "autofish")



       

        ### create sf proj
        cmda=self.input_macro
        with open(sfFilePath,"w") as fp:
            for line in cmda:
                print(line,file=fp)

        ### create cmd batch call
        cmds=[]
        cmds.append("cd " +str(self.workDir))
        cmds.append("start /W  \" \"  \""+autofishpath_str+"\"  "+self.sfFileName)
        cmds.append("echo %errorlevel% >" + str(self.outname))
        with open(bFilePath,"w") as fp:
            for line in cmds:
                print(line,file=fp)
        
        ### FIN
        return bFilePath


        

    
    def run(self):

        pathc=self.workDir 
        self.postProcessHelper.setResultDir(pathc.absolute())
        
        outpath = self.outpath
        startTime = time.time()
        if outpath.exists():
            self.logger.info(
            "WorkerID:%r Name:%r Already Finished."
                % (self.ID, self.runName)
            )
        else:
            batchfile=self.createMainBatch(self.runName)
            self.startSF(batchfile)
            
            self.logger.info(
                "WorkerID:%r Name:%r started."
                % (self.ID, self.runName)
            )    
        self.logger.info("Start Time:%r" % time.ctime())
        while not outpath.exists():
            # ADD process check HERE
            rcode = self.sfProcess.poll()
            if rcode is None:
                pass

            else:
                self.logger.error("SF Process stopped")
                self.logger.error("WORKER FINISHED")
                runResult = {
                    
                    "TaskStatus": "Failure",
                    "RunName": self.runName,
                    "PostProcessResult": None,
                }
                return runResult
                # os._exit(0)
            time.sleep(1)
            currentTime = time.time()
            escapedTime = currentTime - startTime
            if escapedTime > self.maxWaitTime:
                raise TimeoutError

            
            
        try:
            postProcessResult = self.postProcessHelper.getResult()
            
        except FileNotFoundError:
            postProcessResult = None
            runResult = {
            "job_info":self.job_info,
            "TaskStatus": "PostProcessFailure",
            "RunName": self.runName,
            "PostProcessResult": postProcessResult,
        }
            self.logger.info(
                "WorkerID:%r Name:%r Failed."
                % (self.ID, self.runName)
            )
        else:
            runResult = {
            "job_info":self.job_info,
            "TaskStatus": "Success",
            "RunName": self.runName,
            "PostProcessResult": postProcessResult,
        }
            self.logger.info(
                "WorkerID:%r Name:%r success."
                % (self.ID, self.runName)
            )
        self.logger.info("ElapsedTime:%r" % escapedTime)
        self.logger.info("End Time:%r" % time.ctime())
        with open(self.workDir / "runresult.json","w") as fp:
            json.dump(runResult,fp,indent=4)
        return runResult

    def stop(self):
        self.logger.info("Stopping Superfish Worker ID:%d, Please Wait" % self.ID) 
        secs = 0
        rcode = self.sfProcess.poll()
        if rcode is None:
            self.stopWork()
        while secs < self.maxStopWaitTime:
            rcode = self.sfProcess.poll()
            if rcode is None:
                time.sleep(1)
                secs += 1
                self.logger.info("%r secs" % (secs))
            else:
                self.logger.info("Worker ID:%d Stop success" % self.ID)
                return True
        self.logger.error("failed to stop Superfish, try killing the process.")
        self.kill()
        time.sleep(10)
        if not self.sfProcess is None:
            self.logger.warning("Superfish killed.")
            return True
        else:
            self.logger.error("killing failure")
            return False

    def kill(self):
        
        if self.sfProcess:
            self.sfProcess.kill()

    def __del__(self):
        self.kill()

    def start(self):
        self.run()

        




