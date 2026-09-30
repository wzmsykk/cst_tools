import configparser
import os
import logging
from dataclasses import replace
from pathlib import Path

from csttool.configuration import (
    GlobalSettings,
    SuperfishSettings,
    read_ini,
    write_ini_atomic,
)

from csttool.cst_installations import (
    CstInstallation,
    discover_cst_installations,
    validate_cst_installation,
)


class GlobalConfigManager:
    def __init__(
        self,
        configpath=r".\config\current.ini",
        logger: logging.Logger | None = None,
    ):
        self.projlist = []
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
        self.settings = GlobalSettings()
        self.curr_global_cfg_path = Path(configpath)
        self.confdir = self.curr_global_cfg_path.parent
        self.confdir.mkdir(parents=True, exist_ok=True)
        self.def_global_cfg_path = self.confdir / "default.ini"
        ##Generate new default conf file
        if not self.def_global_cfg_path.exists():
            self.createEmptyGlobalConfigFile(self.def_global_cfg_path)

        if not self.curr_global_cfg_path.exists():
            self.logger.info("全局配置不存在，采用默认配置 | path=%s defaults=%s", self.curr_global_cfg_path, self.def_global_cfg_path)
            self.logger.debug("读取默认配置 | path=%s", self.def_global_cfg_path)
            self.conf = read_ini(self.def_global_cfg_path)
            self.settings = GlobalSettings.from_parser(self.conf)
            self.conf = self.settings.to_parser()
            self.saveconf()
        else:
            self.logger.info("找到curr_global_cfg:%s" % str(self.curr_global_cfg_path))
            default_settings = GlobalSettings.from_parser(
                read_ini(self.def_global_cfg_path)
            )
            self.settings = GlobalSettings.from_parser(
                read_ini(self.curr_global_cfg_path), defaults=default_settings
            )
            self.conf = self.settings.to_parser()

    @property
    def conf(self):
        """Return a serialized copy of the authoritative typed settings."""
        return self.settings.to_parser()

    @conf.setter
    def conf(self, parser):
        self.settings = GlobalSettings.from_parser(parser)

    def printconf(self):
        settings = self.settings
        self.logger.debug("----------------------------------------------------------")
        self.logger.debug("全局信息:")
        self.logger.debug("data目录:%s", settings.directories.data.resolve())
        self.logger.debug("temp目录:%s", settings.directories.temp.resolve())
        self.logger.debug("log目录:%s", settings.directories.log.resolve())
        self.logger.debug("result目录:%s", settings.directories.result.resolve())
        self.logger.debug("CST版本:%s", settings.cst.version)
        self.logger.debug("CSTEXE路径:%s", settings.cst.executable or "")
        self.logger.debug("superfish版本:%s", settings.superfish.version)
        self.logger.debug("superfish路径:%s", settings.superfish.directory or "")
        self.logger.debug("----------------------------------------------------------")

    def createEmptyGlobalConfigFile(self, savepath):
        newconf = GlobalSettings().to_parser()
        self.__saveconf(newconf, savepath)
        return savepath

    def __saveconf(self, confobj, path):
        path = write_ini_atomic(path, confobj)
        self.logger.debug("全局配置已保存 | path=%s", path)

    def saveconf(self):
        """
        save current config into self.curr_global_cfg_path
        """
        self.conf = self.settings.to_parser()
        self.__saveconf(self.conf, self.curr_global_cfg_path)

    def validate_environment(self):
        # 测试CST环境位置
        result = True
        self.logger.debug("检查全局配置开始.")
        cfg = self.settings
        self.logger.debug("检查CST PATH.")
        try:
            selected = self.get_selected_cst_installation()
        except (FileNotFoundError, TypeError, ValueError):
            self.logger.warning("CST 安装配置无效，正在自动查找 | executable=%s version=%s", cfg.cst.executable, cfg.cst.version)
            self.logger.debug("查找可用 CST 安装")
            try:
                executable, version = self.findCSTenv()
                self.settings = self.settings.with_cst(version, executable)
                self.conf = self.settings.to_parser()
            except FileNotFoundError:
                self.logger.error("未找到可用 CST 安装，请选择有效的可执行文件 | config=%s", self.curr_global_cfg_path)
                self.logger.debug("检查CST PATH 失败.")
                result = False
            else:
                self.logger.info(
                    "CST 安装已自动选择 | executable=%s version=%s", self.settings.cst.executable, self.settings.cst.version
                )

        else:
            self.logger.debug("检查CST PATH 成功.")

        # 版本不再设置上限；新版 CST 由安装路径和可执行文件共同校验。
        self.logger.debug("检查CST 版本.")
        self.logger.debug("CST ENV PATH为%s", self.settings.cst.executable)
        self.logger.debug("CST 版本为%s", self.settings.cst.version)
        self.logger.debug("检查CST 版本 结束.")
        # 测试各个路径是否存在，若否则创建目录
        self.logger.debug("检查各个路径是否存在.")
        for names, pathobj in (
            ("data", self.settings.directories.data),
            ("temp", self.settings.directories.temp),
            ("log", self.settings.directories.log),
            ("result", self.settings.directories.result),
        ):
            if not pathobj.exists():
                pathobj.mkdir(parents=True, exist_ok=True)
                self.logger.info("已建立%s于%s。", names, pathobj)

        self.logger.debug("检查全局配置结束.")
        if result == False:
            self.logger.error("CST 环境校验失败 | config=%s", self.curr_global_cfg_path)
        else:
            self.logger.info("CST 环境已就绪 | version=%s executable=%s", self.settings.cst.version, self.settings.cst.executable)
        return result

    def findCSTenv(self):
        self.logger.debug("寻找CSTenv开始")
        installations = self.list_cst_installations()
        if installations:
            selected = installations[0]
            self.logger.info(
                "FOUND CST VERSION %s at %s", selected.version, selected.executable
            )
            self.logger.debug("寻找CSTenv结束")
            return str(selected.executable), str(selected.version)
        self.logger.info("CST ENV NOT FOUND")
        raise FileNotFoundError

    def list_cst_installations(self) -> tuple[CstInstallation, ...]:
        configured = (
            self.settings.cst.version,
            str(self.settings.cst.executable or ""),
        )
        return discover_cst_installations(configured=configured)

    def get_selected_cst_installation(self) -> CstInstallation:
        return validate_cst_installation(
            self.settings.cst.version,
            str(self.settings.cst.executable or ""),
        )

    def select_cst_installation(
        self, version: int | str, executable: str | Path
    ) -> CstInstallation:
        selected = validate_cst_installation(version, executable)
        self.settings = self.settings.with_cst(
            str(selected.version), selected.executable
        )
        self.conf = self.settings.to_parser()
        self.saveconf()
        self.logger.info(
            "已切换 CST 后端至 %s: %s", selected.version, selected.executable
        )
        return selected

    def findSuperfishENV(self):
        sfdir = os.getenv("SFDir")
        if sfdir is None:
            self.logger.info("Poisson Superfish ENV NOT FOUND")
            return False
        else:
            self.logger.info("FOUND Poisson Superfish ENV at %s" % (sfdir))
            self.settings = replace(
                self.settings,
                superfish=SuperfishSettings(
                    self.settings.superfish.version, Path(sfdir)
                ),
            )
            self.conf = self.settings.to_parser()
            return True
