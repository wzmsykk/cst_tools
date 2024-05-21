
import sys
import copy
from pathlib import Path
import unittest
from csttool.cstworker import local_cstworker
from csttool.preprocess_cst import vbpreprocess
import json

testdatapath=Path("./test/data")
class TestData(unittest.TestCase):
    def test_data(self):
        self.assertEqual(testdatapath.exists(),True)
        
class TestCSTWorker(unittest.TestCase):
    def setUp(self) -> None:
        fp=open(testdatapath / "testworker.json","r")
        self.workerconfig=json.load(fp)
        fp.close()
        self.worker=local_cstworker(1,self.workerconfig)
        return super().setUp()
    
    def test_pbox(self):
        self.worker.run()
        self.worker.stop()
        
   
     

        