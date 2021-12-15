import result
import logging

# 200
# worker 输入X得到result的工具


class testworker(object):  # 测试用worker，不经过cst Dim(X)=2
    def __init__(self, conf):
        super().__init__()
        self.conf = conf
        self.x = None
        self.resultName = None
        self.resultDir = conf["resultDir"]

    def changex(self, xlist):
        self.x = xlist.copy()

    def run(self):
        return self.x


class peuCSTworker(object):  # 伪CSTworker，返回查找表
    def __init__(self, conf):
        super().__init__()
        self.conf = conf
        self.x = None
        self.resultName = None
        self.resultDir = conf["resultDir"]

    def changex(self, xlist):
        self.x = xlist.copy()

    def run(self):
        return self.x


class worker(object):
    def __init__(self, id, type="test", config=None, logger=None):
        super().__init__()
        if logger == None:
            self.logger = logging.getLogger("main." + "worker_" + str(id))
        else:
            self.logger = logger

        self.config = config
        self.resultDir = "./"
        self.u_param_list = []
        self.u_value_list = []
        self.runName = "Default"
        self.ID = id
        if type == "test":
            self.logger.info("(DEBUG) test worker:%s" % str(self.ID))
        else:
            self.type = type
            self.logger.info(
                "created worker type %s id:%s" % (str(self.type), str(self.ID))
            )

    def setID(self, id):
        self.ID = id

    def stop(self):
        pass

    def run(self, resultname):
        self.runName = resultname  # 这次结果的名称，用于回溯
        re = resultname
        return re

    def change_uvalue(self, u_param_list, u_value_list):
        self.u_param_list = u_param_list
        self.u_value_list = u_value_list

    def runWithx(self, x, resultname):
        self.runName = resultname  # 这次结果的名称，用于回溯
        self.change_uvalue(u_param_list=[], u_value_list=x)
        re = self.run()
        return re

    def runWithParam(self, param_name_list, value_list, resultname):
        self.runName = resultname  # 这次结果的名称，用于回溯
        self.change_uvalue(u_param_list=param_name_list, u_value_list=value_list)
        re = self.run()
        return re

    def getResultDir(self):
        return self.resultDir
