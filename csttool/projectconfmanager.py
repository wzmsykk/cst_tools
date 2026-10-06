import configparser
import hashlib
import json
import logging
from pathlib import Path
import shutil
import stat
from dataclasses import replace
from enum import Enum
from install_compat import resource_path
from .cst_preprocessor import CstProjectPreprocessor
from .configuration import (
    ProjectSettings,
    read_json,
    read_ini,
    write_ini_atomic,
    write_json_atomic,
)


###读取或生成ProjConf.ini文件


class TaskStatus(Enum):
    UNKNOWN = 0
    READY = 1
    RUNNING = 2
    DONE = 3
    STOP_REQUESTED = 4
    INTERRUPTED = 5
    FAILED = 6
    RECOVERY_REQUIRED = 7


class ProjectStatusError(Exception):
    """The persisted project state cannot satisfy the requested operation."""


class ProjectConfigManager:
    def __init__(
        self,
        GlobalConfigManager=None,
        logger: logging.Logger | None = None,
    ):
        self.conf = configparser.ConfigParser()
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
        self._global_config_manager = GlobalConfigManager
        self.global_settings = GlobalConfigManager.settings
        self.settings: ProjectSettings | None = None
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

    def _rap2apo(
        self, inpath
    ):  # relative or abs path to abspath object related to project dir as base dir
        if self.currProjectDir == None:
            raise AttributeError
        op = Path(inpath)
        if not op.is_absolute():
            op = self.currProjectDir / op
        return op

    def __isDirClean(self, projectDir):
        # new clean project output dir or existed int mid file
        # dir must exist
        iDir = Path(projectDir)
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
        iDir = Path(projectDir)
        cfgfilename = self.CFGfilename
        cfgpath = iDir / cfgfilename
        if not cfgpath.exists():
            self.logger.info("目录%s无旧config文件,无未完成任务。" % str(iDir))
            raise FileNotFoundError
        settings = ProjectSettings.from_parser(read_ini(cfgpath))
        return settings.task_status

    def assignProjectDir(self, projectDir):
        self.setNotReady()  # changed Path so Not Ready
        self.currProjectDir = Path(projectDir).absolute()
        self.logger.info("PCM:currProjectDir 已设为%s" % self.currProjectDir)

    def assignInputCSTFilePath(self, CSTfilePath):
        self.setNotReady()
        self.inputCSTFilePath = Path(CSTfilePath).absolute()
        self.logger.info("PCM:inputCSTFilePath 已设为%s" % self.inputCSTFilePath)

    def __ready(self):
        self.ready = True
        return self.ready

    def prepareProject(self, startFromExisted=False, *, mesh_cells_per_wavelength=20):
        # startFromExisted=True 从已有开始 不需要CST文件
        self.setNotReady()
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
            input_mode = iInputCSTFilePath.stat().st_mode
            if not input_mode & stat.S_IWRITE:
                iInputCSTFilePath.chmod(input_mode | stat.S_IWRITE)
                self.logger.info("已清除输入 CST 文件的只读属性：%s", iInputCSTFilePath)
        dirClean = self.__isDirClean(iProjectDir)
        iConf = None

        if dirClean:
            if startFromExisted:
                self.logger.info("尝试从空白目录继续")
                raise ProjectStatusError("尝试从空白目录继续")
            self.logger.info("目录%s无旧文件" % str(iProjectDir))
            self.logger.info("尝试从project目录%s创建空白配置文件。" % str(iProjectDir))
            # Publish project.ini only after preprocessing succeeds. An empty
            # READY configuration would make the next attempt look like a resume.
            iConf = ProjectSettings(
                name=iProjectDir.name,
                cells_per_wavelength=int(mesh_cells_per_wavelength),
            ).to_parser()

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
                "已将输入CST文件%s复制到project目录%s。"
                % (str(iInputCSTFilePath), dstStrPath)
            )
            iConf = self.__autoPreProcess(iConf, dstPath, mesh_cells_per_wavelength)
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
                self._validate_fixed_mesh(mesh_cells_per_wavelength)
                if startFromExisted:
                    self.setCurrPPSList(self.readPPSList())
                else:
                    self.savePPSSettings(self.currPPSList)
                return self.__ready()
            elif status == "RUNNING":
                self.logger.warning("项目状态仍为 RUNNING，必须先执行显式会话恢复")
                raise ProjectStatusError("project status is RUNNING; recovery required")
            elif status in {"DONE", "INTERRUPTED"}:
                # SAME AS READY
                result = self.__checkAndRepairProject()
                if result == False:
                    raise ProjectStatusError
                self._validate_fixed_mesh(mesh_cells_per_wavelength)
                if startFromExisted:
                    self.setCurrPPSList(self.readPPSList())
                else:
                    self.savePPSSettings(self.currPPSList)
                return self.__ready()
            elif status in {"FAILED", "RECOVERY_REQUIRED", "STOP_REQUESTED"}:
                raise ProjectStatusError(
                    "project requires explicit recovery before execution: " + status
                )

    def __savecfgobj(self, confobj, cfgfilename="project.ini", slient=False):
        cfgfilePath = self.currProjectDir / cfgfilename
        settings = ProjectSettings.from_parser(confobj)
        normalized = settings.to_parser()
        write_ini_atomic(cfgfilePath, normalized)
        self.settings = settings
        if confobj is self.conf:
            self.conf = normalized

    def savecfg(self, cfgfilename="project.ini"):
        self.__savecfgobj(self.conf, cfgfilename)

    def createNewEmptyProjectConfFile(
        self, projectDir="", cfgfilename="project.ini", projectname=None
    ):
        # Config内所有路径都是相对于projectDir这一文件夹
        iProjectDir = Path(projectDir)
        cfgfilepath = iProjectDir / cfgfilename
        self.logger.info("开始创建配置文件%s于%s。" % (cfgfilename, str(cfgfilepath)))
        currprojdir = iProjectDir
        avilprojname = currprojdir.name

        currprojname = None
        if projectname != None:
            self.logger.info("使用指定的project名%s" % projectname)
            currprojname = projectname

        else:
            self.logger.info("未指定project名,使用为默认目录名%s" % avilprojname)
            currprojname = avilprojname

        newconf = ProjectSettings(name=currprojname).to_parser()

        self.logger.info("创建配置文件结束。")
        self.__savecfgobj(newconf, cfgfilename)
        return newconf
        # 保存配置文件

    def __autoPreProcess(self, confobj, cstFilePath, mesh_cells_per_wavelength=None):
        self.logger.info("根据输入的CST文件进行预处理且更新Config内容")
        settings = ProjectSettings.from_parser(confobj)
        savejsonname = settings.parameter_file
        settings = replace(settings, cst_filename=Path(cstFilePath))
        confobj = settings.to_parser()
        if mesh_cells_per_wavelength is None:
            mesh_cells_per_wavelength = settings.cells_per_wavelength
        savednewcstpath = self._preprocess_cst_project(
            confobj,
            projectDir=self.currProjectDir,
            savejsonpath=savejsonname,
            mesh_cells_per_wavelength=mesh_cells_per_wavelength,
        )
        project_digest = self.file_digest(savednewcstpath, "sha256")
        confobj = replace(
            settings,
            cst_filename=Path(savednewcstpath).name,
            project_digest=project_digest,
            digest_algorithm="sha256",
            cells_per_wavelength=int(mesh_cells_per_wavelength),
        ).to_parser()
        self.logger.info("Config内容更新完成")
        return confobj

    def updateTaskStatus(self, taskstatus):
        settings = getattr(self, "settings", None) or ProjectSettings.from_parser(
            self.conf
        )
        self.settings = replace(settings, task_status=taskstatus.name)
        self.conf = self.settings.to_parser()
        self.__savecfgobj(self.conf)
        self.logger.info("PCM:项目状态已设为%s" % taskstatus.name)
        return taskstatus

    def printConfInfo(self, confobj, projectDir):
        settings = ProjectSettings.from_parser(confobj)
        self.logger.info("项目信息:")
        self.logger.info("ProjectName:%s", settings.name)
        self.logger.info("ProjectDescription:%s", settings.description)
        self.logger.info("项目result目录:%s", settings.directories.result)
        self.logger.info("项目temp目录:%s", settings.directories.temp)
        self.logger.info("CST文件名:%s", settings.cst_filename)
        self.logger.info(
            "CST工程摘要(%s):%s",
            settings.digest_algorithm,
            settings.project_digest,
        )
        self.logger.info("使用MPI:%s", settings.use_mpi)
        self.logger.info("MPI节点文件:%s", settings.mpi_node_list)
        self.logger.info("使用远程计算:%s", settings.use_remote_calculation)
        self.logger.info("控制器地址:%s", settings.dc_main_control_address)
        self.logger.info("参数列表文件:%s", settings.parameter_file)
        self.printParamsInfo(confobj, projectDir)

    def printParamsInfo(self, confobj, projectDir):

        paramfile = projectDir / ProjectSettings.from_parser(confobj).parameter_file
        pamlist = read_json(paramfile)
        print(pamlist)

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
            paramfile = projectDir / ProjectSettings.from_parser(confobj).parameter_file
        else:
            paramfile = jsonpath
        return read_json(paramfile)

    def file_digest(self, cstfilepath, algorithm="sha256"):
        digest = hashlib.new(algorithm)
        with Path(cstfilepath).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def genMD5FromCST(self, cstfilepath):
        """Compatibility adapter for callers that still expect a hash object."""
        digest = hashlib.md5()
        with Path(cstfilepath).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest

    def _preprocess_cst_project(
        self,
        confobj,
        projectDir,
        savejsonpath=None,
        *,
        mesh_cells_per_wavelength=20,
    ):
        """Create and validate a prepared project without modifying its source."""
        # Installation selection replaces the immutable global settings object.
        self.global_settings = self._global_config_manager.settings
        settings = ProjectSettings.from_parser(confobj)
        if savejsonpath is None:
            jsonpath = projectDir / self.paramsfilename
        else:
            jsonpath = Path(savejsonpath)
            if not jsonpath.is_absolute():
                jsonpath = projectDir / jsonpath

        td = settings.directories.temp
        if not td.is_absolute():
            td = projectDir / td
        source_project = Path(projectDir).absolute() / settings.cst_filename
        candidate = Path(projectDir).absolute() / "processed.cst"
        suffix = 1
        while candidate.exists() or candidate == source_project:
            candidate = Path(projectDir).absolute() / f"processed_{suffix}.cst"
            suffix += 1
        macro_template = (
            resource_path(self.global_settings.directories.data)
            / "preprocess_hom_parameters_v1.vb"
        )
        preprocessor = CstProjectPreprocessor(
            self.global_settings.cst.executable,
            macro_template,
            logger=self.logger,
        )
        result = preprocessor.preprocess(
            source_project,
            candidate,
            jsonpath,
            td,
            mesh_cells_per_wavelength=mesh_cells_per_wavelength,
        )
        self.logger.info(
            "CST 工程参数预处理完成: %s (%d parameters)",
            result.project_path,
            len(result.parameters),
        )
        return result.project_path

    def _validate_fixed_mesh(self, requested_cells):
        if not (self.conf.has_section("mesh") or self.conf.has_section("MESH")):
            self.logger.warning(
                "旧项目未记录固定网格设置；保持工程现状，不在恢复时修改 mesh"
            )
            return
        settings = getattr(self, "settings", None) or ProjectSettings.from_parser(
            self.conf
        )
        configured_cells = settings.cells_per_wavelength
        if configured_cells != int(requested_cells):
            raise ProjectStatusError(
                "固定网格每波长单元数与已有项目不一致；请新建项目以更改 mesh"
            )

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
        self.conf = read_ini(cfgpath)
        self.settings = ProjectSettings.from_parser(self.conf)
        self.logger.info("测试CST模型文件是否存在")
        cstfilepath = self._require_cst_project_file(cfgpath)
        self.logger.debug("推测模型文件位于%s", str(cstfilepath))
        if cstfilepath.exists():
            self.logger.info("测试CST模型文件存在 通过")
            cstfileflag = True
        else:
            self.logger.error("未找到cst文件%s\n" % str(cstfilepath))
            self.logger.info("测试CST模型文件存在 失败")
            result = False
        current_digest = self.file_digest(cstfilepath, self.settings.digest_algorithm)
        saved_digest = self.settings.project_digest
        self.logger.info("测试参数列表与CST工程摘要是否匹配")
        paramjsonpath = self._rap2apo(self.settings.parameter_file)
        ppsjsonpath = self._rap2apo(self.settings.postprocess_file)
        if current_digest != saved_digest:
            self.logger.warning(
                "记录的CST工程摘要%s与实际摘要%s不一致，已被修改",
                saved_digest,
                current_digest,
            )

            self.logger.warning("重新生成参数列表并保存工程摘要")
            self.logger.info("正在重新生成参数列表")
            self.conf = self.__autoPreProcess(self.conf, cstfilepath)
            # self.readParametersFromCST()
            self.__savecfgobj(self.conf)
            self.logger.warning("已更新保存的工程摘要")
            self.logger.info("工程摘要测试通过")
        elif not paramjsonpath.exists():
            self.logger.warning("参数列表文件_%s不存在" % str(paramjsonpath))

            self.logger.warning("重新生成并保存参数列表")
            self.conf = self.__autoPreProcess(self.conf, cstfilepath)
            # self.readParametersFromCST(paramjsonpath)
            self.__savecfgobj(self.conf)
        if not ppsjsonpath.exists():
            self.logger.warning("后处理设置文件_%s不存在" % str(paramjsonpath))
            self.logger.warning("重新生成并保存参数列表")
            self.savePPSSettings(self.currPPSList)
        self.logger.info("%s检测并更新项目配置文件结束\n" % cfgfilename)
        return result

    def _require_cst_project_file(self, cfgpath):
        if self.settings.cst_filename is None:
            raise ProjectStatusError(
                f"项目配置 {cfgpath} 缺少 CST 模型文件名（[cst] project_file）；"
                "项目可能尚未完成预处理。请使用原始 CST 文件在新的项目目录重新创建项目。"
            )
        cstfilepath = self.currProjectDir / self.settings.cst_filename
        if not cstfilepath.is_file():
            raise ProjectStatusError(
                f"项目配置 {cfgpath} 指定的 CST 模型文件不存在或不是文件：{cstfilepath}"
            )
        return cstfilepath

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

        self.conf = read_ini(cfgpath)
        self.settings = ProjectSettings.from_parser(self.conf)
        cstfilepath = self._require_cst_project_file(cfgpath)
        self.logger.info("测试CST模型文件是否存在")
        self.logger.debug("推测模型文件位于%s", str(cstfilepath))
        if cstfilepath.exists():
            cstfileflag = True
            self.logger.info("测试CST模型文件 通过")
        else:
            self.logger.error("未找到cst模型文件%s\n" % str(cstfilepath))
            self.logger.info("测试CST模型文件 失败")
            result = False
        current_digest = self.file_digest(cstfilepath, self.settings.digest_algorithm)
        saved_digest = self.settings.project_digest
        self.logger.info("测试保存的工程摘要是否与CST模型文件匹配")
        paramjsonpath = self._rap2apo(self.settings.parameter_file)
        if current_digest != saved_digest:
            self.logger.warning(
                "记录的CST工程摘要%s与实际的%s不一致，已被修改",
                saved_digest,
                current_digest,
            )
            self.logger.info("工程摘要测试失败")
            result = False
        elif not paramjsonpath.exists():
            self.logger.warning("参数列表文件_%s不存在" % str(paramjsonpath))
            result = False
        else:
            self.logger.info("工程摘要测试通过")
        ppsjsonpath = self._rap2apo(self.settings.postprocess_file)
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
        settings = self.settings or ProjectSettings.from_parser(self.conf)
        ppspath = self.currProjectDir / settings.postprocess_file
        return self.readPPSListFromFile(ppspath)

    def readPPSListFromFile(self, ppspath):
        try:
            result = read_json(ppspath)
            if not isinstance(result, list):
                raise ValueError("postprocess configuration must be a list")
            return result
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self.logger.warning("后处理设定读取失败: %s", exc)
            return []

    def savePPSSettings(self, ppslist):
        settings = self.settings or ProjectSettings.from_parser(self.conf)
        ppspath = self.currProjectDir / settings.postprocess_file
        try:
            write_json_atomic(ppspath, ppslist)
            self.logger.info("后处理设定已保存至%s" % str(ppspath))
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.logger.error("后处理设定保存失败: %s", exc)
            return False


# Compatibility alias for callers using the historical spelling.
ProjectConfmanager = ProjectConfigManager
