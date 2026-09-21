
import sys
import copy
from pathlib import Path
import unittest
from csttool.cstworker import local_cstworker
from csttool.cstmanager import CSTManager
from csttool.globalconfmanager import GlobalConfmanager
from csttool.projectconfmanager import ProjectConfmanager
from csttool.logging_config import ApplicationLogSession
import json
import pytest


pytestmark = pytest.mark.integration


testdatapath=Path("./test/data")
outputpath=Path("./temp")
class TestData(unittest.TestCase):
    def test_data(self):
        self.assertEqual(testdatapath.exists(),True)
        
class TestCSTManager(unittest.TestCase):
    def setUp(self) -> None:
        self.logf = ApplicationLogSession(outputpath / "testmg.log")
        self.log = self.logf.logger
        self.gconfman = GlobalConfmanager(configpath=testdatapath / "testconfig.ini", logger=self.log)
        self.pconfman = ProjectConfmanager(GlobalConfigManager=self.gconfman, logger=self.log)
        tmpprojdir=outputpath / "testman"
        tmpprojdir.mkdir(exist_ok=True)
        self.pconfman.assignProjectDir(tmpprojdir)
        self.pconfman.assignInputCSTFilePath(testdatapath / "Pillbox" / "Pillbox.cst")
        self.pconfman.prepareProject()
        self.cstm=CSTManager(gconfm=self.gconfman,pconfm=self.pconfman,params=None)
        return super().setUp()

    def tearDown(self) -> None:
        self.logf.close()
        return super().tearDown()
    
    def test_emptymng(self):
        
        self.cstm.startProcessing()
        self.cstm.addTask()
        self.cstm.synchronize()
        result=self.cstm.getFullResults()
        print(result)
        
    
   
     

