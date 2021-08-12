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
import adam,myAlgorithm_pop,myAlgorithm
import globalconfmanager,logger,time
import projectconfmanager
import argparse

from enum import Enum
class TaskType(Enum):
    DoNothing=0
    GenerateProjectFromCST=1
    RunFromExistingProject=2
    GenerateAndRunProject=3
class ToolsStatus(Enum):
    IDLE=0
    RUNNING=1
    FIZZLED=2
    COMPLETED=3
class cst_tools_main:
    def __init__(self) -> None:
        self.params=None
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
    def startGlobalConfig(self): 
        self.gconfman=globalconfmanager.GlobalConfmanager(Logger=self.logger)
        self.ReadyForActualTask=False
        self.projectDir=None
        self.status=ToolsStatus.IDLE
        ###验证全局配置  
        ###self.gconfman.checkConfig()
    def setProjectDir(self,dirpath):
        dp=pathlib.Path(dirpath)
        if not dp.exists():
            self.logger.error('Dirpath is not EXIST')
        else:
            self.logger.info('项目目录已设为%s'%str(dp))
            self.projectDir=dirpath
    def _fail_and_exit(self):
        os._exit(1)
    def _success_and_exit(self):
        os._exit(0)
    

    def initAfterDirAndTaskTypeSet(self):
        result=self.gconfman.checkConfig()
        if result==False:
            self._fail_and_exit()

        if (self.projectDir!=None):
            self.glogger.logger.info("使用命令行定义的project目录:%s" % self.projectDir)
            self.gconfman.conf['PROJECT']['currprojdir']=self.projectDir
        else:
            self.glogger.logger.error("未指定project目录")
            self._fail_and_exit()


        ###检查并取得当前project
        self.gconfman.checkCurrProject()
        self.gconfman.saveconf()

        ###使用找到的project
        self.currprojdir=self.gconfman.conf['PROJECT']['currprojdir']
        self.glogger.logger.info("开始使用project目录:%s" % self.currprojdir)

        ###启动项目配置管理器
        self.pconfman=projectconfmanager.ProjectConfmanager(GlobalConfigManager=self.gconfman,Logger=self.logger)
        #self.pconfman.setProjectDir(self.currprojdir)
        # if self.taskType==TaskType.GenerateAndRunProject or self.taskType==TaskType.GenerateProjectFromCST:    
        #     self.pconfman.openProjectDir(self.currprojdir)
        # elif self.taskType==TaskType.RunFromExistingProject:
        #     self.pconfman.openProjectDirReadOnly(self.currprojdir)

        ###读取完毕，显示当前全局设置
        self.gconfman.printconf()
    def batchinit(self):
        self.params=sys.argv
        ###设定命令行参数PARSER
        self.parser = argparse.ArgumentParser(description='python cst project.')
        self.parser.add_argument("-p", "--projectdir",
                        action="store", dest="projectdir", help="project目录")

        self.parser.add_argument("-r", "--runonly", action="store_true", dest="runonly", help="仅运行已生成的项目")
        self.parser.add_argument("-g", "--genonly", action="store_true", dest="genonly", help="仅从cst文件生成项目")
        self.args=self.parser.parse_args()
        self.projectDir=self.args.projectdir
        runonly=self.args.runonly
        genonly=self.args.genonly


        self.setProjectDir(r".\project\pillbox_ay")
          


        if runonly==True and genonly ==True:
            self.glogger.logger.error("输入参数-r/-g冲突,结束。")
            self._fail_and_exit()
        elif runonly==True:
            self.taskType=TaskType.RunFromExistingProject
        elif genonly==True:
            self.taskType=TaskType.GenerateProjectFromCST
        else:
            self.taskType=TaskType.GenerateAndRunProject
        ###验证全局配置是否有效
        
        result=self.gconfman.checkConfig()
        if result==False:
            self._fail_and_exit()

        if (self.projectDir!=None):
            self.glogger.logger.info("使用命令行定义的project目录:%s" % self.projectDir)
            self.gconfman.conf['PROJECT']['currprojdir']=self.projectDir
        else:
            self.glogger.logger.error("未指定project目录")
            self._fail_and_exit()


        ###检查并取得当前project
        self.gconfman.checkCurrProject()
        self.gconfman.saveconf()

        ###使用找到的project
        self.currprojdir=self.gconfman.conf['PROJECT']['currprojdir']
        self.glogger.logger.info("开始使用project目录:%s" % self.currprojdir)

        ###启动项目配置管理器
        self.pconfman=projectconfmanager.ProjectConfmanager(GlobalConfigManager=self.gconfman,Logger=self.logger)
        #self.pconfman.setProjectDir(self.currprojdir)
        # if self.taskType==TaskType.GenerateAndRunProject or self.taskType==TaskType.GenerateProjectFromCST:    
        #     self.pconfman.openProjectDir(self.currprojdir)
        # elif self.taskType==TaskType.RunFromExistingProject:
        #     self.pconfman.openProjectDirReadOnly(self.currprojdir)

        ###读取完毕，显示当前全局设置
        self.gconfman.printconf()
        #self.pconfman.printconf()
    

    def starttask(self):
        self.status=ToolsStatus.RUNNING
        if  self.taskType==TaskType.DoNothing:
            self.glogger.logger.info("未指定任何任务。退出。")
            self.status=ToolsStatus.COMPLETED
            return self.status
        if self.taskType==TaskType.RunFromExistingProject:
            try:
                self.pconfman.openProjectDirReadOnly(self.currprojdir)
            except:
                self.status=ToolsStatus.FIZZLED
                return self.status

        elif self.taskType==TaskType.GenerateProjectFromCST or self.taskType==TaskType.GenerateAndRunProject:
            try:
                self.pconfman.openProjectDir(self.currprojdir)
            except:
                self.status=ToolsStatus.FIZZLED
                return self.status


        if self.taskType==TaskType.RunFromExistingProject or self.taskType==TaskType.GenerateAndRunProject:

            params=self.pconfman.getParamsList()
            method="GD_PARALLEL_LOCAL"
            #if method=="GD":
            #    worker=worker.worker(type='loacl',config=cstconf)
            #    x0 = gen_x_list(rlst[0])
            #    gw=adam.adam(worker,x0) 
            #    gw.start()
            #    worker.stop()


            if method=="GD_PARALLEL_LOCAL":
                x0 = projectutil.convert_json_params_to_list(params)
                mym=cstmanager.manager(params=params,pconfm=self.pconfman,gconfm=self.gconfman,logger=self.logger,maxTask=2)
                import myCSTFields_simple
                #gw=myCSTFields_simple.MyCuts_Pillbox(manager=mym,params=params) 
                gw=myAlgorithm_pop.myAlg01(manager=mym,params=params) 
                #gw=myAlgorithm.myAlg01_pillbox(manager=mym,x0=x0) 
                gw.start()
                mym.stop()

        self.status=ToolsStatus.COMPLETED
        return self.status
        
       

if __name__ =='__main__':
    myapp=cst_tools_main()
    myapp.startGlobalConfig()
    myapp.batchinit()
    myapp.starttask()