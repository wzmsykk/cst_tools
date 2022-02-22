
import sys
[sys.path.append(i) for i in ['.', '..']]

import pytest
from sfworker import local_superfish_worker
from install_compat import resource_path
from cstworker import local_cstworker
from preprocess_cst import vbpreprocess

def test_local_superfish_worker_dummy(tmp_path_factory):
    tmp_dir=tmp_path_factory.mktemp("data")
    test_config={
        "job_info":{
            "type":"test"
        },
        "workdir":tmp_dir ,
        "resultdir":tmp_dir ,
        "SFENVPATH":r"C:\LANL",
    }
    sfworker_test=local_superfish_worker(id=0,config=test_config)
    refbatchstr=[]
    result=sfworker_test.run()
    assert result['TaskStatus']=="PostProcessFailure"
    
def test_cst_preprocess(tmp_path_factory):
    tmp_dir1=tmp_path_factory.mktemp("work")
    tmp_dir2=tmp_path_factory.mktamp("task")
    tmp_dir3=tmp_path_factory.mktamp("result")
    cst_preps_helper=vbpreprocess()
    cst_preps_helper.setResultDir(tmp_dir3)
    test_preprocess_config_list=[
        {
            "method":"SetVirtualRunFlag",
            "config":{
                
                "FlagValue":True
            }
        },
        {
            "method":"Preparamize",
            "config":{
                "resultName":"Preparamize_result"

            }
        },{
            "method":"Getparamlist",
            "config":{
                "resultName":"Getparamlist_result"
                

            }
        }

    ]

    
    test_worker_config={
        "cstType":"default",
        "cstPatternDir":resource_path("./data"),
        "tempDir":tmp_dir1,
        "taskFileDir":tmp_dir2,
        "resultDir":tmp_dir3,
        "cstProjPath":"./test/data/cst_worker_test_data/input.cst",
        "postProcess":[],
        "preProcess":[]
    }
    
    pass
def test_local_cst_worker(tmp_path_factory):
    tmp_dir1=tmp_path_factory.mktemp("work")
    tmp_dir2=tmp_path_factory.mktamp("task")
    tmp_dir3=tmp_path_factory.mktamp("result")
    test_config={
        "cstType":"default",
        "cstPatternDir":resource_path("./data"),
        "tempDir":tmp_dir1,
        "taskFileDir":tmp_dir2,
        "resultDir":tmp_dir3,
        "cstProjPath":"./test/data/cst_worker_test_data/input.cst",
        "postProcess":[],
        "preProcess":[]
    }

def test_remote_superfish_worker():
    pass
