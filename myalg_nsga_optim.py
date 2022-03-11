"""produce LHS sample"""
###修改内容
###runWithX 修改为 runWithParam 需要提供param_name_list 和 value_list 作为参数
###addTask 同上
###初值需要自己写，留空[]则为默认
###
from asyncio import tasks
from enum import Flag
from pickletools import uint1
from random import random
import logging

import math
import numpy as np
import sfmanager
import time
import pandas as pd
from algs.nsga.nsgaii_np import nsgaii
from algs.nsga.nsgaii_helper import fnds_callback_create_Image,fnds_callback_create_Image_dump_fnds
import data.superfish.elligen as sfmodel
import data.superfish.elliheader as sfheader


class sf_parallel_model():
    def __init__(self,initial_value=np.ones(30)) -> None:
        self.name='superfish_parallel_run'
        self.initial_value=initial_value
        self.min_var=initial_value*0.9
        self.max_var=initial_value*1.1
        self.sfmanager
    def create_var_boundary(self):
        return None,None
    def __call__(self,invars_list):
        ####f1=fx, f2=g(x)h(x)        
            
        outvars_list=invars_list
        return outvars_list
    def check_boundary(self,invars_list):
        flaglist=[]
        for i in range(len(invars_list)):
            flag=True
            invars=invars_list[i]
            for i in range(self.n):
                xi=invars[i]
                if not np.sum((xi<self.max_var) and (xi>self.min_var)): ### Not in between those values
                    flag=False
            flaglist.append(flag)
        return flaglist
    def test_var(self):
        x1=np.random.random(size=len(self.initial_value))
        interval=self.max_var-self.min_var
        return self.min_var+x1*interval
    @classmethod
    def best_solution_check(cls,var):
        #### Not best yet
        return False
class myAlg01():
    def __init__(self, manager: sfmanager.manager = None,logger=None):
        if logger is None:
            self.logger=logging.getLogger("NSGA_DEMO")
        self.manager=manager

        # 读写
        # self.mode_location = 'result\\'
        self.log = None
        self.ready = False          
        self.default_model_params = {
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
        self.paramToOptim=["Req","Leq"]
        self.resultNames=["frequency","RoverQ"]
        ##OTHERS
        self.nsga:nsgaii=nsgaii()
        self.nsga.nobj = 2    ### OPTIM TARGETS FREQ, R over Q
        self.nsga.nval = len(self.paramToOptim)  ###OPTIM VARIBLES Req,Leq
        self.nsga.pmut_real = 0.1
        self.nsga.eta_m = 1  ## coff for mutation
        self.nsga.popsize = 5
        self.nsga.generation = 5
        self.nsga.min_realvar = self.getDefaultParamArray()*0.9
        self.nsga.max_realvar = self.getDefaultParamArray()*1.1
    def getDefaultParamArray(self):
        u=[self.default_model_params[item] for item in self.paramToOptim]
        return np.array(u)
    def createModelParamsFromArray(self,inArr):
        modelparams=self.default_model_params.copy()
        for i in range(len(self.paramToOptim)):
            modelparams[self.paramToOptim[i]]=inArr[i]
        return modelparams
    def createSFJob(self,index,modelparams:dict):
        final_model_params=self.default_model_params.copy()
        
        final_model_params.update(modelparams)
        sfh = sfheader.SFHeaderGenerator()
        header = sfh.createHeaderLines()
        model = sfmodel.createModelByDict(final_model_params)["cmdlines"]
        batchlines=header+model
        job_config={
            "job_info":{
                "type":"run",
                "index":index
            },
            "input_macro":batchlines
        }
        return job_config
    def call(self,invar_list):
        for index,invar in enumerate(invar_list):
            outpardict=self.createModelParamsFromArray(invar)
            jobdef=self.createSFJob(index,outpardict)
            self.manager.addTask(jobdef)
        self.manager.startListening()
        self.manager.synchronize()
        results=self.manager.getFullResults()
        sortedlist=sorted(results,key=lambda x:x["job_info"]["index"])
        pps=[r["PostProcessResult"] for r in sortedlist]
        processed=[]
        for u in pps:
            v=[]
            for key in self.resultNames:
                v.append(float(u[key]))
            v[0]=(v[0]-500)**2
            v[1]=-v[1]
            v=np.array(v)
            processed.append(v)
        return processed
    def start(self,callback=None):
        fin_pop=self.nsga.nsgaii_generation_parallel(self.call,fnds_callback=callback)
        return fin_pop


if __name__ == "__main__":
    logfilepath = r"log\myalgtest.log"
    import logger
    glogger = logger.Logger(logfilepath, level="debug")
    ilogger = glogger.getLogger()
    isf=sfmanager.manager(workdir="./temp",sfenvpath=r"C:\LANL",logger=ilogger,maxTask=10)
    callback=fnds_callback_create_Image_dump_fnds("./result")
    myAlg=myAlg01(isf,logger=ilogger)
    fin_pop=myAlg.start(callback)

