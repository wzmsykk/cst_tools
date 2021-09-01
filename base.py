import os
import pathlib
import sys
import shutil 
import result
import copy
import json
import numpy as np
import worker,cstmanager
import projectutil
import adam,myAlgorithm_pop,myAlgo_pop_win
import globalconfmanager,logger,time
import projectconfmanager
import argparse

from enum import Enum
class TaskType(Enum):
    DoNothing=0
    Run=1
    

class cst_tools_main:
    def __init__(self) -> None:
        self.parser=None
        self.args=None
        self.batchprojectdir=None
        self.taskType=0
        self.glogger=None
        self.gconfman=None
        self.pconfman=None
        ###生成LOG文件 启动日志
        uuid_str = time.strftime("%Y-%m-%d-%H_%M_%S",time.localtime()) 
        os.makedirs(r".\log",exist_ok=True)
        self.glogfilepath =r'log\base_%s.log' % uuid_str
        self.glogger=logger.Logger(self.glogfilepath,level='debug')
        self.logger=self.glogger.getLogger()
        self.logger.info("日志已输出到%s",self.glogfilepath)
        #启动全局配置管理器,读取全局配置 
        self.gconfman=globalconfmanager.GlobalConfmanager(Logger=self.logger)
        self.pconfman=projectconfmanager.ProjectConfmanager(GlobalConfigManager=self.gconfman,Logger=self.logger)
        self.ReadyForActualTask=False
        self.projectDir=None
        self.cstFilePath=None
        #WORKER MANAGER
        self.jm=None

        #算法/参数
        self.algparams=None
        self.alg=None


      
    def setProjectDir(self,dirpath):
        self.projectDir=dirpath

    def setCSTFilePath(self,filepath):
        self.cstFilePath=filepath
    def setFlags(self,startFromExisted,safe):
        self.ctn=startFromExisted
        self.safe=safe
    def __batch_fail_and_exit(self):
        os._exit(1)
    def _success_and_exit(self):
        os._exit(0)
    

    def wininit(self):
        result=self.gconfman.checkConfig()
        if result==False:
            return False

        if (self.projectDir!=None):
            self.logger.error("未指定project目录")
            return False


        ###检查并取得当前project
        self.gconfman.checkCurrProject()
        self.gconfman.saveconf()

        ###使用找到的project
        self.currprojdir=self.gconfman.conf['PROJECT']['currprojdir']
        self.logger.info("开始使用project目录:%s" % self.currprojdir)

        ###准备项目配置
        self.pconfman=projectconfmanager.ProjectConfmanager(GlobalConfigManager=self.gconfman,Logger=self.logger)
        self.pconfman.prepareProject(self.ctn,self.safe)
        #self.pconfman.setProjectDir(self.currprojdir)
        # if self.taskType==TaskType.GenerateAndRunProject or self.taskType==TaskType.GenerateProjectFromCST:    
        #     self.pconfman.openProjectDir(self.currprojdir)
        # elif self.taskType==TaskType.RunFromExistingProject:
        #     self.pconfman.openProjectDirReadOnly(self.currprojdir)

        ###读取完毕，显示当前全局设置
        self.gconfman.printconf()
    def batchinit(self):
        #self.params=sys.argv
        ###设定命令行参数PARSER
        self.parser = argparse.ArgumentParser(description='python cst project.')
        self.parser.add_argument("-p", "--projectdir",
                        action="store", dest="projectdir", help="project目录")
        self.parser.add_argument("-f", "--cstfilepath",
                        action="store", dest="cstfilepath", help="输入CST文件路径")
        self.parser.add_argument("-c", "--continue", action="store_true", dest="ctn", help="继续模式")
        self.parser.add_argument("-s", "--safe", action="store_true", dest="safe", help="安全模式")
        self.args=self.parser.parse_args()
        
        self.ctn=self.args.ctn
        self.safe=self.args.safe

        self.setProjectDir(self.args.projectdir)        
        self.setCSTFilePath(self.args.cstfilepath)


        
        ###验证全局配置是否有效
        
        result=self.gconfman.checkConfig()
        if result==False:
            self.__batch_fail_and_exit()

        if (self.projectDir!=None):
            self.logger.info("使用命令行定义的project目录:%s" % self.projectDir)
            self.gconfman.conf['PROJECT']['currprojdir']=self.projectDir
        else:
            self.logger.error("未指定project目录")
            self.__batch_fail_and_exit()


        ###检查并取得当前project
        self.gconfman.checkCurrProject()
        self.gconfman.saveconf()

        ###使用找到的project
        self.currprojdir=self.gconfman.conf['PROJECT']['currprojdir']
        self.logger.info("开始使用project目录:%s" % self.currprojdir)

        ###开始项目配置
        self.pconfman.assignProjectDir(self.currprojdir)
        self.pconfman.assignInputCSTFilePath(self.cstFilePath)
        self.pconfman.prepareProject(self.ctn,self.safe)
        #self.pconfman.setProjectDir(self.currprojdir)
        # if self.taskType==TaskType.GenerateAndRunProject or self.taskType==TaskType.GenerateProjectFromCST:    
        #     self.pconfman.openProjectDir(self.currprojdir)
        # elif self.taskType==TaskType.RunFromExistingProject:
        #     self.pconfman.openProjectDirReadOnly(self.currprojdir)

        ###读取完毕，显示当前全局设置
        self.gconfman.printconf()
        self.logger.info("-----------------------------------")

    def createJobManager(self): 
        #depends on a ready Pconfman 
        if not self.pconfman.isReady():
            self.logger.error('pconfman 未准备完成')
            raise RuntimeError
        projectparams=self.pconfman.getParamsList()
        if self.jm is None:
            self.jm=cstmanager.manager(params=projectparams,pconfm=self.pconfman,gconfm=self.gconfman,logger=self.logger,maxTask=2)
            self.logger.info("JOB MANAGER 创建完成")
        else:
            self.logger.warning("JOB MANAGER 已存在")
    def prepareAlgorithmAndParams_Batch(self):
        if not self.pconfman.isReady():
            self.logger.error('pconfman 未准备完成')
            raise RuntimeError
        self.algparams=self.pconfman.getParamsList()
        self.alg=myAlgorithm_pop.myAlg01(manager=self.jm,params=self.algparams) 

    def prepareAlgorithmAndParams_Win(self):  
        if self.alg==None:      
            self.alg=myAlgo_pop_win.myAlg01_win_wrapper(Logger=self.logger)         
        
        return self.alg.getAttrsDict()
        
    def changeAlgSetting(self,paramdict):
        methodnameList=['changeCalcParams']
        for methodname in methodnameList:
            method=getattr(self.alg,methodname)
            if method:
                break
        method(paramdict)
    def pretask_win(self,manager):
        if not self.pconfman.isReady():
            self.logger.error('pconfman 未准备完成')
            raise RuntimeError
        self.alg.assignCSTWorkManager(manager)
        self.algparams=self.pconfman.getParamsList()
        self.alg.assignCSTVariable(self.algparams)

    def starttask(self):
        self.status=projectconfmanager.TaskStatus.RUNNING
        self.pconfman.updateTaskStatus(self.status)
        if  self.taskType==TaskType.DoNothing:
            self.logger.info("未指定任何任务。退出。")
            self.status=projectconfmanager.TaskStatus.DONE
            return self.status
        


        if self.taskType==TaskType.Run:

            method="GD_PARALLEL_LOCAL"
            #if method=="GD":
            #    worker=worker.worker(type='loacl',config=cstconf)
            #    x0 = gen_x_list(rlst[0])
            #    gw=adam.adam(worker,x0) 
            #    gw.start()
            #    worker.stop()


            if method=="GD_PARALLEL_LOCAL":
                
                import myCSTFields_simple
                #gw=myCSTFields_simple.MyCuts_Pillbox(manager=mym,params=params) 
                #assign manager

                #gw=myAlgorithm.myAlg01_pillbox(manager=mym,x0=x0) 
                self.alg.start()
        self.jm.stop()
        self.status=projectconfmanager.TaskStatus.DONE
        self.pconfman.updateTaskStatus(self.status)
        return self.status
        
       

if __name__ =='__main__':
    # BATCH FLOW
    myapp=cst_tools_main()

    myapp.batchinit()
    myapp.createJobManager()
    myapp.prepareAlgorithmAndParams_Batch()   
    myapp.starttask()
    # UI PROGRAM FLOW SAMPLE
    # myapp=cst_tools_main()
    # myapp.setProjectDir()
    # myapp.setCSTFilePath()
    # myapp.setFlags()
    # result=myapp.wininit()
    # 
    # alg default=myapp.prepareAlgorithmAndParams_Win()    
    #   CHANGE ALG SETTINGS OPTIONAL
    #   (OPTIONAL)myapp.changeAlgSetting()
    #
    # myapp.createJobManager()
    # myapp.pretask_win()
    # myapp.starttask()