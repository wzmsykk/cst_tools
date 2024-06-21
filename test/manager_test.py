
import sys
import copy
from pathlib import Path
import unittest
from csttool.cstworker import local_cstworker
from csttool.cstmanager import manager
from csttool.globalconfmanager import GlobalConfmanager
from csttool.projectconfmanager import ProjectConfmanager
from csttool.logger import Logger
import json


testdatapath=Path("./test/data")
outputpath=Path("./temp")
class TestData(unittest.TestCase):
    def test_data(self):
        self.assertEqual(testdatapath.exists(),True)
        
class TestCSTManager(unittest.TestCase):
    def setUp(self) -> None:
        self.logf=Logger(outputpath / "testmg.log")
        self.log=self.logf.getLogger()
        self.gconfman = GlobalConfmanager(configpath=testdatapath / "testconfig.ini",Logger=self.log)
        self.pconfman = ProjectConfmanager(GlobalConfigManager=self.gconfman,Logger=self.log)
        tmpprojdir=outputpath / "testman"
        tmpprojdir.mkdir(exist_ok=True)
        self.pconfman.assignProjectDir(tmpprojdir)
        self.pconfman.assignInputCSTFilePath(testdatapath / "Pillbox" / "Pillbox.cst")
        self.pconfman.prepareProject(Safe=False)
        self.cstm=manager(gconfm=self.gconfman,pconfm=self.pconfman,params=None)
        return super().setUp()
    
    def test_emptymng(self):
        
        self.cstm.startProcessing()
        self.cstm.addTask()
        self.cstm.synchronize()
        result=self.cstm.getFullResults()
        print(result)
        
    
   
     

        