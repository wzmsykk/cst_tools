import os
from install_compat import resource_path

from csttool import cstmanager
from csttool import nsgaii_WTC
from csttool import globalconfmanager, logger
import time
from csttool import projectconfmanager
import argparse

from enum import Enum


class TaskType(Enum):
    DoNothing = 0
    Run = 1


class cst_tools_main:
    def __init__(self) -> None:
        self.parser = None
        self.args = None
        self.batchprojectdir = None
        self.taskType = 0
        self.glogger = None
        self.gconfman = None
        self.pconfman = None
        ###生成LOG文件 启动日志
        uuid_str = time.strftime("%Y-%m-%d-%H_%M_%S", time.localtime())
        os.makedirs(r".\log", exist_ok=True)
        self.glogfilepath = r"log\base_%s.log" % uuid_str
        self.glogger = logger.Logger(self.glogfilepath, level="debug")
        self.logger = self.glogger.getLogger()
        self.logger.info("日志已输出到%s", self.glogfilepath)
        ### 测试环境
        self.logger.info("数据路径%s" % str(resource_path(".")))

        # 启动全局配置管理器,读取全局配置
        self.gconfman = globalconfmanager.GlobalConfmanager(Logger=self.logger)
        self.pconfman = projectconfmanager.ProjectConfmanager(
            GlobalConfigManager=self.gconfman, Logger=self.logger
        )
        self.ReadyForActualTask = False
        # WORKER MANAGER
        self.jm = None

        # 算法/参数
        self.alg = nsgaii_WTC.myAlg_nsga(manager=None, params=None, logger=self.logger)

        # 设置默认后处理
        defaultPPSListPath = resource_path("data/WTCPPS.json")
        lst = self.readPostProcessListFromFile(defaultPPSListPath)
        self.setCurrPostProcessList(lst)

    def setProjectDir(self, dirpath):
        self.pconfman.assignProjectDir(dirpath)

    def getProjectDir(self):
        return self.pconfman.currProjectDir

    def setCSTFilePath(self, filepath):
        self.pconfman.assignInputCSTFilePath(filepath)

    def getCSTFilePath(self):
        return self.pconfman.currCSTFilePath

    def setFlags(self, startFromExisted, safe):
        self.ctn = startFromExisted
        self.safe = safe
        self.logger.info("BASE:SET CTN=%s,SAFE=%s" % (str(self.ctn), str(self.safe)))

    def setCurrPostProcessList(self, ppslist):
        return self.pconfman.setCurrPPSList(ppslist)

    def getCurrPostProcessList(self):
        return self.pconfman.getCurrPPSList()

    def readPostProcessListFromFile(self, path):
        return self.pconfman.readPPSListFromFile(path)

    def __batch_fail_and_exit(self):
        os._exit(1)

    def _success_and_exit(self):
        os._exit(0)

    def wininit(self):
        ##认为setProjectDir/setCSTFilePath

        result = self.gconfman.checkCSTENVConfig()
        if result == False:
            return False

        ###保存全局配置
        self.gconfman.saveconf()

        ###使用找到的projectTrue
        self.logger.info("开始使用project目录:%s" % str(self.getProjectDir()))

        return True

    def batchinit(self):
        # self.params=sys.argv
        ###设定命令行参数PARSER
        self.parser = argparse.ArgumentParser(description="python cst project.")
        self.parser.add_argument(
            "-p", "--projectdir", action="store", dest="projectdir", help="project目录"
        )
        self.parser.add_argument(
            "-f",
            "--cstfilepath",
            action="store",
            dest="cstfilepath",
            help="输入CST文件路径",
        )
        self.parser.add_argument(
            "-c", "--continue", action="store_true", dest="ctn", help="继续模式"
        )
        self.parser.add_argument(
            "-s", "--safe", action="store_true", dest="safe", help="安全模式"
        )
        self.args = self.parser.parse_args()

        self.ctn = self.args.ctn
        self.safe = self.args.safe

        self.setProjectDir(self.args.projectdir)
        self.setCSTFilePath(self.args.cstfilepath)

        ###验证全局配置是否有效

        result = self.gconfman.checkCSTENVConfig()
        if result == False:
            self.__batch_fail_and_exit()

        ###保存全局配置
        self.gconfman.saveconf()

        ###使用找到的project
        self.logger.info("开始使用project目录:%s" % str(self.getProjectDir()))
        return 1

    def setRunInfos(self):
        ###开始项目配置
        try:
            self.pconfman.prepareProject(self.ctn, self.safe)
        except RuntimeError:
            self.logger.error("项目配置出错")
            return 0

        ###读取完毕，显示当前全局设置
        self.gconfman.printconf()
        self.logger.info("-----------------------------------")
        ### 创建JM
        self.createJobManager()
        ### 准备计算信息
        self.algparams = self.pconfman.getParamsList()
        self.alg.setJobManager(self.jm)
        self.alg.setCSTParams(self.algparams)
        ### READY
        self.taskType = TaskType.Run  # 准备运行

    def createJobManager(self):
        # depends on a ready Pconfman
        if not self.pconfman.isReady():
            self.logger.error("pconfman 未准备完成")
            raise RuntimeError
        projectparams = self.pconfman.getParamsList()
        if self.jm is None:
            self.jm = cstmanager.manager(
                params=projectparams,
                pconfm=self.pconfman,
                gconfm=self.gconfman,
                logger=self.logger,
                maxTask=2,
            )
            self.logger.info("JOB MANAGER 创建完成")
        else:
            self.logger.warning("JOB MANAGER 已存在")

    def getAlgAttrs(self):
        return self.alg.getEditableAttrs()

    def setAlgAttrs(self, dict):
        self.alg.setEditableAttrs(dict)
        self.logger.info("ALG参数设置完毕")

    def starttask(self):
        self.status = projectconfmanager.TaskStatus.RUNNING
        self.pconfman.updateTaskStatus(self.status)
        if self.taskType == TaskType.DoNothing:
            self.logger.info("未指定任何任务。退出。")
            self.status = projectconfmanager.TaskStatus.DONE
            self.jm.stop()
            return self.status

        print()
        if self.taskType == TaskType.Run:
            if self.alg is None:
                self.logger.info("未指定计算方法。退出。")
                self.status = projectconfmanager.TaskStatus.DONE
                return self.status
            method = "GD_PARALLEL_LOCAL"
            # if method=="GD":
            #    worker=worker.worker(type='loacl',config=cstconf)
            #    x0 = gen_x_list(rlst[0])
            #    gw=adam.adam(worker,x0)
            #    gw.start()
            #    worker.stop()

            if method == "GD_PARALLEL_LOCAL":
                #self.alg.start()
                self.alg.start()
        self.jm.stop()
        self.status = projectconfmanager.TaskStatus.DONE
        self.pconfman.updateTaskStatus(self.status)
        return self.status


if __name__ == "__main__":
    # BATCH FLOW
    myapp = cst_tools_main()
    myapp.batchinit()
    myapp.setRunInfos()
    myapp.starttask()
    # UI PROGRAM FLOW SAMPLE
    # myapp=cst_tools_main()
    # myapp.setProjectDir()
    # myapp.setCSTFilePath()
    # myapp.setFlags()
    # myapp.setPostProcess()
    # attrs=myapp.getAlgAttrs()
    # OPTIONAL myapp.setAlgAttrs(attrs)
    # result=myapp.wininit()
    # myapp.setRunInfos()
    # myapp.starttask()
