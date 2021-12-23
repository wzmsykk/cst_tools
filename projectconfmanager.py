import configparser
import shutil, json
import preprocess_cst
from install_compat import resource_path
import json
import subprocess
import hashlib
import tempfile
import projectutil
import pathlib, shutil
from enum import Enum

###读取或生成ProjConf.ini文件


class TaskStatus(Enum):
    UNKNOWN = 0
    READY = 1
    RUNNING = 2
    DONE = 3


class ProjectStatusError(Exception):
    def __init__(self, message):
        self.meg = message


class ProjectConfmanager(object):
    def __init__(self, GlobalConfigManager=None, Logger=None):
        self.conf = configparser.ConfigParser()
        self.logger = Logger
        self.gconf = GlobalConfigManager.conf
        self.inputCSTFilePath = None
        self.currProjectDir = None
        self.currCSTFilePath = None
        self.CFGfilename = "project.ini"
        self.paramsfilename = "params.json"
        self.ppsfilename = "pps.json"  # 后处理设定文件
        self.currPPSList = []
        self.ready = False

    def isReady(self):
        return self.ready

    def setNotReady(self):
        self.ready = False
        return self.ready

    def __isCFGfileexist(self):
        if self.currProjectDir != None:
            if (self.currProjectDir / self.CFGfilename).exists():
                return True
        return False

    def _rap2apo(
        self, inpath
    ):  # relative or abs path to abspath object related to project dir as base dir
        if self.currProjectDir == None:
            raise AttributeError
        op = pathlib.Path(inpath)
        if not op.is_absolute():
            op = self.currProjectDir / op
        return op

    def __isDirClean(self, projectDir):
        # new clean project output dir or existed int mid file
        # dir must exist
        iDir = pathlib.Path(projectDir)
        self.logger.info("尝试打开project目录%s。" % str(iDir))
        cfgfilename = self.CFGfilename
        cfgpath = iDir / cfgfilename
        if not iDir.exists():
            raise FileNotFoundError  # dir must exist
        if not any(iDir.iterdir()):
            self.logger.info("目录%s为空。" % str(iDir))
            return True
        if not cfgpath.exists():
            self.logger.info("目录%s无旧config文件。" % str(iDir))
            return True
        self.logger.info("目录%s存在已有文件。" % str(iDir))
        return False

    def __getTaskStatus(self, projectDir):
        # 任务完成情况
        iDir = pathlib.Path(projectDir)
        cfgfilename = self.CFGfilename
        cfgpath = iDir / cfgfilename
        if not cfgpath.exists():
            self.logger.info("目录%s无旧config文件,无未完成任务。" % str(iDir))
            raise FileNotFoundError
        tempconf = configparser.ConfigParser()
        tempconf.read(cfgpath)
        status = tempconf.get("TASK", "status")
        if status == None:
            raise ValueError
        else:
            return status

    def assignProjectDir(self, projectDir):
        self.setNotReady()  # changed Path so Not Ready
        self.currProjectDir = pathlib.Path(projectDir).absolute()
        self.logger.info("PCM:currProjectDir 已设为%s" % self.currProjectDir)

    def assignInputCSTFilePath(self, CSTfilePath):
        self.setNotReady()
        self.inputCSTFilePath = pathlib.Path(CSTfilePath).absolute()
        self.logger.info("PCM:inputCSTFilePath 已设为%s" % self.inputCSTFilePath)

    def __ready(self):
        self.ready = True
        return self.ready

    def prepareProject(self, startFromExisted=False, Safe=True):
        # startFromExisted=True 从已有开始 不需要CST文件
        self.logger.info("准备项目文件")
        iProjectDir = self.currProjectDir
        iInputCSTFilePath = self.inputCSTFilePath
        if iProjectDir == None or not iProjectDir.exists():
            self.logger.error("未找到project目录%s。" % str(iProjectDir))
            raise FileNotFoundError
        if not startFromExisted:
            if iInputCSTFilePath == None or not iInputCSTFilePath.exists():
                self.logger.error("未找到输入CST文件%s。" % str(iInputCSTFilePath))
                raise FileNotFoundError
        dirClean = self.__isDirClean(iProjectDir)
        iConf = None

        if dirClean:
            if startFromExisted:
                self.logger.info("尝试从空白目录继续")
                raise ProjectStatusError("尝试从空白目录继续")
            self.logger.info("目录%s无旧文件" % str(iProjectDir))
            self.logger.info("尝试从project目录%s创建空白配置文件。" % str(iProjectDir))
            iConf = self.createNewEmptyProjectConfFile(iProjectDir)

            # 复制输入CST文件到输出文件夹
            # 且自动预处理
            dstPath = iProjectDir / iInputCSTFilePath.name
            if dstPath.exists():
                self.logger.info("目的%s已存在同名文件。" % str(dstPath))
                dstPath = iProjectDir / (
                    iInputCSTFilePath.stem + "_dst" + iInputCSTFilePath.suffix
                )
            dstStrPath = shutil.copy2(src=str(iInputCSTFilePath), dst=str(dstPath))
            self.logger.info(
                "已将输入CST文件%s复制到project目录%s。" % (str(iInputCSTFilePath), dstStrPath)
            )
            iConf = self.__autoPreProcess(iConf, dstPath)
            self.__savecfgobj(iConf)
            self.conf = iConf
            self.savePPSSettings(self.currPPSList)
            return self.__ready()
        else:
            self.logger.info("目录%s有旧文件" % str(iProjectDir))
            status = self.__getTaskStatus(iProjectDir)  # [READY RUNNING DONE]
            if status == "READY":
                result = self.__checkProjectStatus()
                if result == False:
                    raise ProjectStatusError
                if startFromExisted:
                    self.setCurrPPSList(self.readPPSList())
                else:
                    self.savePPSSettings(self.currPPSList)
                return self.__ready()
            elif status == "RUNNING":
                if not Safe:
                    self.logger.warning("发现异常结束,尝试修复并继续")
                    result = self.__checkAndRepairProject()
                    if result == False:
                        raise ProjectStatusError("FLAG_SAFE=OFF but REPAIR FAILED")
                    if startFromExisted:
                        self.setCurrPPSList(self.readPPSList())
                    else:
                        self.savePPSSettings(self.currPPSList)
                    return self.__ready()
                else:
                    self.logger.warning("发现异常结束,安全模式设置为ON,不会尝试修改")
                    self.logger.warning("结束")
                    raise ProjectStatusError("FLAG_SAFE=ON and status=RUNNING")
            elif status == "DONE":
                # SAME AS READY
                result = self.__checkAndRepairProject()
                if result == False:
                    raise ProjectStatusError
                if startFromExisted:
                    self.setCurrPPSList(self.readPPSList())
                else:
                    self.savePPSSettings(self.currPPSList)
                return self.__ready()

    def __savecfgobj(self, confobj, cfgfilename="project.ini", slient=False):
        cfgfilePath = self.currProjectDir / "project.ini"
        f = open(cfgfilePath, "w")
        confobj.write(f)
        f.close()

    def savecfg(self, cfgfilename="project.ini"):
        self.__savecfgobj(self.conf, cfgfilename)

    def createNewEmptyProjectConfFile(
        self, projectDir="", cfgfilename="project.ini", projectname=None
    ):
        # Config内所有路径都是相对于projectDir这一文件夹
        iProjectDir = pathlib.Path(projectDir)
        cfgfilepath = iProjectDir / cfgfilename
        self.logger.info("开始创建配置文件%s于%s。" % (cfgfilename, str(cfgfilepath)))
        newconf = configparser.ConfigParser()
        newconf.clear()
        cstfile = None
        currprojdir = iProjectDir
        avilprojname = currprojdir.name

        currprojname = None
        if projectname != None:
            self.logger.info("使用指定的project名%s" % projectname)
            currprojname = projectname

        else:
            self.logger.info("未指定project名,使用为默认目录名%s" % avilprojname)
            currprojname = avilprojname

        newconf.add_section("PROJECT")
        newconf.set("PROJECT", "ProjectName", currprojname)
        newconf.set("PROJECT", "ProjectType", "HOM analysis")
        newconf.set("PROJECT", "ProjectDescription", "")
        newconf.add_section("DIRS")
        # 保存为相对路径

        #############TO DO #####################

        newconf.set("DIRS", "resultdir", "result")
        newconf.set("DIRS", "tempdir", "temp")
        newconf.add_section("CST")
        newconf.set("CST", "CSTFilename", "")  # NEED TO BE FILLED IN LATER

        # file_md5=self.genMD5FromCST(cstfile)
        # newconf.set('CST','CSTFileMD5',file_md5.hexdigest())
        newconf.set("CST", "CSTFileMD5", "")  # NEED BE FILLED IN

        newconf.set("CST", "UseMpi", "False")
        newconf.set("CST", "MpiNodeList", "")
        newconf.set("CST", "UseRemoteCalculaton", "False")
        newconf.set("CST", "DCMainControlAddress", "")
        newconf.add_section("PARAMETERS")
        newconf.set("PARAMETERS", "paramfile", self.paramsfilename)
        newconf.set("PARAMETERS", "ppsfile", self.ppsfilename)
        # newconf.set('PARAMETERS','paramfile','')
        newconf.add_section("TASK")
        newconf.set("TASK", "status", "READY")  # READY RUNNING DONE

        self.logger.info("创建配置文件结束。")
        self.__savecfgobj(newconf, cfgfilename)
        return newconf
        # 保存配置文件

    def __autoPreProcess(self, confobj, cstFilePath):
        self.logger.info("根据输入的CST文件进行预处理且更新Config内容")
        savejsonname = confobj.get("PARAMETERS", "paramfile")
        confobj.set("CST", "CSTFilename", str(cstFilePath))
        savednewcstpath = self.__vbpreprocess_CST(
            confobj, projectDir=self.currProjectDir, savejsonpath=savejsonname
        )
        confobj.set("CST", "CSTFilename", str(savednewcstpath))
        file_md5 = self.genMD5FromCST(savednewcstpath)
        confobj.set("CST", "CSTFileMD5", file_md5.hexdigest())
        self.logger.info("Config内容更新完成")
        return confobj

    def __updateTaskStatusInConfObj(self, confobj, taskstatus):
        confobj.set("TASK", "status", taskstatus.name)
        return confobj

    def updateTaskStatus(self, taskstatus):
        self.conf.set("TASK", "status", taskstatus.name)
        self.__savecfgobj(self.conf)
        self.logger.info("PCM:项目状态已设为%s" % taskstatus.name)
        return taskstatus

    def printConfInfo(self, confobj, projectDir):
        self.logger.info("项目信息:")
        self.logger.info("ProjectName:%s" % confobj["PROJECT"]["ProjectName"])
        self.logger.info("ProjectType:%s" % confobj["PROJECT"]["ProjectType"])
        self.logger.info(
            "ProjectDescription:%s" % confobj["PROJECT"]["ProjectDescription"]
        )
        self.logger.info("项目result目录:%s" % confobj["DIRS"]["resultdir"])
        self.logger.info("项目temp目录:%s" % confobj["DIRS"]["tempdir"])
        self.logger.info("CST文件名:%s" % confobj["CST"]["CSTFilename"])
        self.logger.info("CSTFileMD5:%s" % confobj["CST"]["CSTFileMD5"])
        self.logger.info("使用MPI:%s" % confobj["CST"]["UseMpi"])
        self.logger.info("MPI节点文件:%s" % confobj["CST"]["MpiNodeList"])
        self.logger.info(
            "UseRemoteCalculaton:%s" % confobj["CST"]["UseRemoteCalculaton"]
        )
        self.logger.info(
            "DCMainControlAddress:%s" % confobj["CST"]["DCMainControlAddress"]
        )
        self.logger.info("参数列表文件:%s" % confobj["PARAMETERS"]["paramfile"])
        self.printparams(confobj, projectDir)

    def printParamsInfo(self, confobj, projectDir):

        paramfile = projectDir / confobj["PARAMETERS"]["paramfile"]
        f = open(paramfile, "r")
        pamlist = json.load(f)
        print(pamlist)
        f.close()

    def getParamsList(self):
        return self.__getParamsList(self.conf, self.currProjectDir)

    def __getParamsList(self, confobj, projectDir, jsonpath=None):
        """从生成的json读取Model结构参数列表 read model parameters from json filepath
            
        Parameters
        ----------
        jsonpath : string

        Returns
        -------
        pamlist : a list of json dict contains the param names and values

        """
        if jsonpath == None:
            paramfile = projectDir / confobj["PARAMETERS"]["paramfile"]
        else:
            paramfile = jsonpath
        f = open(paramfile, "r")
        pamlist = json.load(f)
        f.close()
        return pamlist

    def genMD5FromCST(self, cstfilepath):
        # 生成MD5
        fp = open(cstfilepath, "rb")
        dat = fp.read()
        file_md5 = hashlib.md5(dat)
        fp.close()
        return file_md5

    def __gen_vblines_cstpreprocess(self, oldcstpath, midpath):  # 预处理
        preps = preprocess_cst.vbpreprocess()
        preps.setResultDir(self.currProjectDir)
        pslist = []
        prep0 = {
            "method": "OpenFile",
            "config": {
                "resultName": "openfile_result",
                "resultFilename": "openfile.txt",
                "cstpath": str(oldcstpath),
            },
        }
        pslist.append(prep0)
        prep1 = {
            "method": "preparamize",
            "config": {
                "resultName": "preparamize_result",
                "resultFilename": "paramr.txt",
            },
        }
        pslist.append(prep1)
        prep2 = {
            "method": "getparamlist",
            "config": {
                "resultName": "getparamlist_result",
                "resultpath": str(midpath),
            },
        }
        pslist.append(prep2)
        newcstpath = self.currProjectDir / "processed.cst"
        opath_str = str(newcstpath)
        prep3 = {
            "method": "saveCSTProject",
            "config": {
                "resultName": "saveCSTProject_result",
                "resultFilename": "savedcst.txt",
                "outpath": opath_str,
            },
        }
        pslist.append(prep3)
        preps.appendPreProcessSteps(pslist)
        vblines = preps.createPreProcessVBCodeLines()
        # processedCSTFilePath = cstFilePath
        return vblines, newcstpath

    def __vbpreprocess_CST(self, confobj, projectDir, savejsonpath=None):
        if savejsonpath == None:
            jsonpath = projectDir / self.paramsfilename
        else:
            jsonpath = pathlib.Path(savejsonpath)
            if not jsonpath.is_absolute():
                jsonpath = projectDir / jsonpath
        self.logger.info("正在从CST文件中读取参数列表。")
        projectname = confobj["PROJECT"]["ProjectName"]
        td = pathlib.Path(confobj["DIRS"]["tempdir"])

        if td.is_absolute():
            td = confobj["DIRS"]["tempdir"]
        else:
            td = projectDir / td
        if not td.exists():
            td.mkdir()
        tempfile.tempdir = str(td)
        self.logger.info("tempdir为%s。" % tempfile.gettempdir())
        tmp_bas = tempfile.NamedTemporaryFile(mode="w", suffix=".bas", delete=False)
        tmp_txt = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp_cst = tempfile.NamedTemporaryFile(mode="wb", suffix=".cst", delete=False)
        tmp_bas_name = tmp_bas.name
        tmp_cst_name = tmp_cst.name
        tmp_txt_name = tmp_txt.name
        self.logger.info("临时文件生成成功。")
        vbasrcpath = (
            resource_path(self.gconf["BASE"]["datadir"]) / "readParamsT.vb"
        )
        vbadstpath = pathlib.Path(tempfile.gettempdir()) / tmp_bas_name
        midfilepath = pathlib.Path(tempfile.gettempdir()) / tmp_txt_name

        cstfilepath = (
            pathlib.Path(projectDir).absolute() / confobj["CST"]["CSTFilename"]
        )
        tmpcstpath = pathlib.Path(tempfile.gettempdir()).absolute() / tmp_cst_name
        # tmpcstfile
        fcst = open(cstfilepath, "rb")
        content = fcst.read()
        tmp_cst.file.write(content)

        tmp_cst.file.close()

        file_1 = open(vbasrcpath, "r")
        file_2 = tmp_bas.file
        list1 = []
        # for line in file_1.readlines():
        #     ssd = line
        #     ssd = re.sub("%PARAMDSTPATH%", str(midfilepath).replace("\\", "\\\\"), ssd)
        #     ssd = re.sub("%CSTPROJFILE%", str(tmpcstpath).replace("\\", "\\\\"), ssd)
        #     list1.append(ssd)
        # file_1.close()
        list1, newcstpath = self.__gen_vblines_cstpreprocess(
            str(tmpcstpath), str(midfilepath)
        )

        for i in range(len(list1)):
            file_2.write(list1[i])
        file_2.close()

        # command=

        command = (
            '"'
            + self.gconf["CST"]["cstexepath"]
            + '"'
            + " -m "
            + '"'
            + str(vbadstpath)
            + '"'
        )
        with subprocess.Popen(
            command, stdout=subprocess.PIPE, shell=True
        ) as self.cstProcess:
            for line in self.cstProcess.stdout:
                self.logger.info(line)

        projectutil.custom_ascii_2_json(midfilepath, jsonpath)
        return newcstpath
        pass

    def __checkAndRepairProject(
        self, cfgfilename="project.ini", slient=False, force=True
    ):
        result = True
        cfgpath = self.currProjectDir / cfgfilename
        cstfileflag = False
        cfgfileflag = False
        self.logger.info("检测并更新项目配置文件")
        self.logger.info("测试项目配置文件是否存在")
        self.logger.debug("推测项目配置文件位于%s", str(cfgpath))
        if cfgpath.exists():
            self.logger.info("测试项目配置文件存在 通过")
            cfgfileflag = True
        else:
            self.logger.error("未找到配置文件%s\n" % str(cfgpath))
            self.logger.info("测试项目配置文件存在 失败")
            result = False
        self.conf.clear()
        self.conf.read(cfgpath)
        self.logger.info("测试CST模型文件是否存在")
        cstfilepath = self.currProjectDir / self.conf["CST"]["CSTFilename"]
        self.logger.debug("推测模型文件位于%s", str(cstfilepath))
        if cstfilepath.exists():
            self.logger.info("测试CST模型文件存在 通过")
            cstfileflag = True
        else:
            self.logger.error("未找到cst文件%s\n" % str(cstfilepath))
            self.logger.info("测试CST模型文件存在 失败")
            result = False
        currCSTMD5 = self.genMD5FromCST(cstfilepath).hexdigest()
        savedCSTMD5 = self.conf["CST"]["CSTFileMD5"]
        self.logger.info("测试保存的参数列表与MD5是否与CST模型文件匹配")
        paramjsonpath = self._rap2apo(self.conf["PARAMETERS"]["paramfile"])
        ppsjsonpath = self._rap2apo(self.conf["PARAMETERS"]["ppsfile"])
        if currCSTMD5 != savedCSTMD5:
            self.logger.warning(
                "记录的CST文件MD5_%s与实际的MD5_%s不一致，已被修改" % (savedCSTMD5, currCSTMD5)
            )

            self.logger.warning("重新生成参数列表并保存MD5n/y")
            self.logger.info("正在重新生成参数列表")
            self.conf = self.__autoPreProcess(self.conf, cstfilepath)
            # self.readParametersFromCST()
            # self.conf["CST"]["CSTFileMD5"] = currCSTMD5
            self.__savecfgobj()
            self.logger.warning("已更新保存的MD5")
            self.logger.info("测试MD5 通过")
        elif not paramjsonpath.exists():
            self.logger.warning("参数列表文件_%s不存在" % str(paramjsonpath))

            self.logger.warning("重新生成并保存参数列表")
            self.conf = self.__autoPreProcess(self.conf, cstfilepath)
            # self.readParametersFromCST(paramjsonpath)
            self.__savecfgobj()
        if not ppsjsonpath.exists():
            self.logger.warning("后处理设置文件_%s不存在" % str(paramjsonpath))
            self.logger.warning("重新生成并保存参数列表")
            self.savePPSSettings(self.currPPSList)
        self.logger.info("%s检测并更新项目配置文件结束\n" % cfgfilename)
        return result

    def __checkProjectStatus(
        self, cfgfilename="project.ini", slient=False, force=False
    ):
        result = True
        cfgpath = self.currProjectDir / cfgfilename
        cstfileflag = False
        cfgfileflag = False
        self.logger.info("检测项目配置文件正确性")
        self.logger.info("测试项目配置文件是否存在")
        self.logger.debug("推测项目配置文件位于%s", str(cfgpath))
        if cfgpath.exists():
            cfgfileflag = True
            self.logger.info("测试项目配置文件 通过")
        else:
            self.logger.error("未找到项目配置文件%s\n" % str(cfgpath))
            self.logger.info("测试项目配置文件 失败")
            result = False

        self.conf.clear()
        self.conf.read(cfgpath)
        cstfilepath = self.currProjectDir / self.conf["CST"]["CSTFilename"]
        self.logger.info("测试CST模型文件是否存在")
        self.logger.debug("推测模型文件位于%s", str(cstfilepath))
        if cstfilepath.exists():
            cstfileflag = True
            self.logger.info("测试CST模型文件 通过")
        else:
            self.logger.error("未找到cst模型文件%s\n" % str(cstfilepath))
            self.logger.info("测试CST模型文件 失败")
            result = False
        currCSTMD5 = self.genMD5FromCST(cstfilepath).hexdigest()
        savedCSTMD5 = self.conf["CST"]["CSTFileMD5"]
        self.logger.info("测试保存的MD5是否与CST模型文件匹配")
        paramjsonpath = self._rap2apo(self.conf["PARAMETERS"]["paramfile"])
        if currCSTMD5 != savedCSTMD5:
            self.logger.warning(
                "记录的CST文件MD5%s与实际的%s不一致，已被修改" % (savedCSTMD5, currCSTMD5)
            )
            self.logger.info("测试MD5 失败")
            result = False
        elif not paramjsonpath.exists():
            self.logger.warning("参数列表文件_%s不存在" % str(paramjsonpath))
            result = False
        else:
            self.logger.info("测试MD5 通过")
        ppsjsonpath = self._rap2apo(self.conf["PARAMETERS"]["ppsfile"])
        if not ppsjsonpath.exists():
            self.logger.warning("后处理设置文件_%s不存在" % str(ppsjsonpath))
            result = False
        self.logger.info("%s检测项目配置文件结束\n" % cfgfilename)

        return result

    def getCurrPPSList(self):
        return self.currPPSList

    def setCurrPPSList(self, ilist):
        self.currPPSList = ilist
        return ilist

    def readPPSList(self):
        ppspath = self.currProjectDir / self.conf.get("PARAMETERS", "ppsfile")
        return self.readPPSListFromFile(ppspath)

    def readPPSListFromFile(self, ppspath):
        lst = []

        try:
            fp = open(ppspath, "r")
            lst = json.load(fp)
            fp.close()
            return lst
        except:
            self.logger.info("后处理设定读取失败")
            return lst

    def savePPSSettings(self, ppslist):
        ppspath = self.currProjectDir / self.conf.get("PARAMETERS", "ppsfile")
        try:
            fp = open(ppspath, "w")
            json.dump(ppslist, fp)
            fp.close()
            self.logger.info("后处理设定已保存至%s" % str(ppspath))
            return True
        except:
            self.logger.info("后处理设定保存失败")
            return False

