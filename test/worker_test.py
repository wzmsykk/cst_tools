
import sys
[sys.path.append(i) for i in ['.', '..']]

import pytest
from sfworker import local_superfish_worker
from install_compat import resource_path
from cstworker import local_cstworker
from preprocess_cst import vbpreprocess
from data.superfish import elligen,elliheader
import json
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
    
def test_local_superfish_worker_full(tmp_path_factory):
    sample_input_name = {
    "R_SBP": 110,
    "R_LBP": 150,
    "Req": 262.83,
    "Leq": 266.24,
    "D2_r": 115.02,
    "D2_l": 115.02,
    "b1": 64.936,
    "a1": 64.936,
    "b3": 80,
    "a3": 27.5,
    "b4": 80,
    "a4": 27.5,
    "r2": 30,
    "r1": 30,
    "H": 10.85,
    "D1": 58.43,
    }
    tmp_dir=tmp_path_factory.mktemp("data")
    sfh = elliheader.SFHeaderGenerator()
    header = sfh.createHeaderLines()
    model = elligen.createModelByDict(sample_input_name)["cmdlines"]
    batchlines=header+model
    test_config={
        "job_info":{
            "type":"run"
        },
        "workdir":tmp_dir ,
        "resultdir":tmp_dir ,
        "SFENVPATH":r"C:\LANL",
        "input_macro":batchlines

    }
    sfworker_test=local_superfish_worker(id=0,config=test_config)
    refbatchstr=[]
    result=sfworker_test.run()
    print(result)
    with open(tmp_dir /'result.json','w') as ofp:
        json.dump(result,ofp,indent=4)
    assert result['TaskStatus']=="Success"
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
