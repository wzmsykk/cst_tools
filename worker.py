import logging
from pathlib import Path
from typing import Dict, Union, Optional
from abc import ABCMeta, abstractmethod

from logger import Logger

# 200
# worker 输入X得到result的工具


class worker(metaclass=ABCMeta):
    """abstruct worker class"""

    def __init__(
        self,
        id: int,
        config: Optional[Dict] = None,
        logger: Optional[Logger] = None,
        type: str = "Test",
    ) -> None:
        if logger == None:
            self.logger = logging.getLogger("main." + "worker_" + str(id))
        else:
            self.logger = logger

        self.config = config
        self.workDir = Path("./")
        self.resultDir = Path("./")
        self.runParams: Dict = None
        self.runName = "Default"
        self._ID = id
        if str(type).lower() == "test":
            self.logger.info("(DEBUG) test worker:%s" % str(self.ID))
        else:
            self.type = type
            self.logger.info(
                "created worker type %s id:%s" % (str(self.type), str(self.ID))
            )

    @property
    def resultDir(self) -> Path:
        """worker output result dir"""
        return self._resultDir

    @resultDir.setter
    def resultDir(self, value: Union[str, Path]) -> None:
        self._resultDir = value

    @property
    def workerDir(self) -> Path:
        """worker working dir"""
        return self._workerDir

    @workerDir.setter
    def workerDir(self, value: Union[str, Path]) -> None:
        self.workerDir = value

    @property
    def ID(self) -> int:
        """read only worker id"""
        return self._ID

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def run(self, resultname: str, *args, **kwargs) -> Dict:
        self.runName = resultname  # 这次结果的名称，用于回溯
        runResult = {
            "RunName": self.runName,
            "TaskStatus": "Success",
            "ResultData": None,  #### Dummy
        }
        return runResult

    
    def runWithParam(self, resultname: str, *args, **kwargs) -> Dict:
        self.runName = resultname  # 这次结果的名称，用于回溯
        self.runParams = kwargs["params"]
        re = self.run()
        return re

   

class testworker(worker):  # 测试用worker
    def __init__(self, id: int, config: Optional[Dict] = None, logger: Optional[Logger] = None, type: str = "Test") -> None:
        super().__init__(id, config, logger, type)

    def runWithParam(self, resultname: str, *args, **kwargs) -> Dict:
        return super().runWithParam(resultname, *args, **kwargs)

    def run(self, resultname: str, *args, **kwargs) -> Dict:
        return super().run(resultname, *args, **kwargs)

