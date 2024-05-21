"""produce LHS sample"""
###修改内容
###runWithX 修改为 runWithParam 需要提供param_name_list 和 value_list 作为参数
###addTask 同上
###初值需要自己写，留空[]则为默认
###
import os
from .myAlgorithm import myAlg
from random import random, seed, shuffle, choices,sample
import math
import numpy as np
from . import cstmanager
from algs.nsga import nsgaii_helper,targetfunc,nsgaii_np
from utils import mode_util_sample
import time
import pandas as pd

class tm020cav(targetfunc.commonfunc):
    def __init__(self,nofdvs=2) -> None:
        super().__init__(nofdvs)
        self.name='zdt1'
        # input 2-dims 
        # Req 180-200mm
        # Leq 60-120mm
        
        # output 4-dims
        # freq 1500Mhz
        # R over Q
        # Q
        # Shunt-dep
    def create_var_boundary(self):
        max_var=[None for _ in range(self.n)]
        min_var=[None for _ in range(self.n)]
        min_var[0] = 180
        max_var[0] = 200
        min_var[1] = 60
        max_var[1] = 120
        return min_var,max_var
    def __call__(self,invars):
        ####f1=fx, f2=g(x)h(x)               
        freq,roq,q,shuntd=1500,0,0,0
        freqdis=abs(1500-freq)
        return freq,freqdis,roq,q,shuntd
    def check_boundary(self,invars):
        flag=True
        return flag
    def test_var(self):
        invars=[]
        x1=random()
        invars.append(x1)
        for i in range(1,self.n):
            xi=random()
            invars.append(xi)
        return invars
    @classmethod
    def best_solution_check(cls,var):
        return True


class myAlg_nsga(myAlg):
    def __init__(self, manager: cstmanager.manager = None, params=None):
        super().__init__(manager, params)
        self.parameter_range = 0
        self.CSTparams = params

        self.state_x0 = []
        self.state_y0 = 0

        # 读写
        # self.mode_location = 'result\\'
        self.log = None
        self.mode_location = None
        self.relative_location = None  # 在setManager后实现
        self.ready = False
        # y函数,
        #self.yFunc = yfunction.yfunc(yfunction.myYFunc01)

        ##OTHERS
        self.manager = None
        if manager is not None:
            self.setJobManager(manager)
        # self.results=result.result

        # input 2-dims 
        # Req 180-200mm
        # Leq 60-120mm
        
        # output 4-dims
        # freq 1500Mhz
        # R over Q
        # Q
        # Shunt-dep
        
        self.input_name = ["nmodes", "Leq", "Req"]
        self.input_min = [10, 60, 180]  ##初始值
        self.input_max = [10, 120, 200]  ##初始值

        self.csv_input_name = self.input_name + ["mode"]

        self.output_name = [
            "frequency",
            "R_divide_Q",
            "R_divide_Q_5mm",
            "R_divide_Q_10mm",
            "Q-factor",
            "Shunt_Inpedence",
        ]
        self.output_name = None
        self.text_name = ["Frequency", "R_Q", "Q", "Shunt_Inpedence"]
        self.accu_list = pd.DataFrame(
            [[0, 1500, 1e-5], [1500, 4100, 1e-4]],
            columns=["f_down", "f_up", "accuracy"],
        )
        self.cell_list = pd.DataFrame(
            [[0, 1300, 20], [1300, 2000, 15], [2000, 4100, 10]],
            columns=["f_down", "f_up", "cell"],
        )

        # self.dimension_input = len(self.input_name)
        # self.dimension_output = len(self.output_name)

        self.delta_frequency = 50

        self.end_frequency = 2500
        self.continue_flag = [0, 3738.9532]  # [是否继续，上次做完的最后一次频率]

    def checkAndSetReady(self):
        if self.CSTparams is not None and self.manager is not None:
            self.ready = True
        else:
            self.ready = False

    def setCSTParams(self, params):
        self.CSTparams = params
        self.checkAndSetReady()

    def setJobManager(self, manager: cstmanager.manager):
        self.manager = manager
        self.mode_location = str(manager.currProjectDir) + "\\result\\"
        self.relative_location = str(manager.currProjectDir) + "\\save\\csv\\"
        if not os.path.exists(self.relative_location):
            os.makedirs(self.relative_location)
        logpath = os.path.join(manager.getResultDir(), "result.log")
        self.log = open(logpath, "w")
        self.checkAndSetReady()



    def logCalcSettings(self):
        print(self.getEditableAttrs())
        pass

    def get_y_trans_r_aprallel(self, xs, run_count):

        nor = self.state_y0
        print("nor:", nor)
        # r = []
        y = []

        for j, x in enumerate(xs):
            self.manager.addTask(self.input_name, x, str(run_count) + str(x[1]))

        self.manager.start()
        self.manager.synchronize()  # 同步 很重要
        rl = self.manager.getFullResults()
        ###SORT RESULTS
        rg = [i["PostProcessResult"] for i in rl]
        rg = sorted(rg, key=lambda x: int(x["name"][16:]))

        for irg in rg:
            print(irg["name"])
            y.append(irg["value"])

        print("y", y)

        return np.array(y).reshape(len(xs), self.dimension_output)

    




    def get_value(self, file):
        f = open(file)
        text = f.read()
        return float(text[140:])
    
    
    
    def start(self):
        if self.ready == False:
            print("CALCATION NOT READY, PLEASE CHECK SETTINGS.")
            print("IS THE JOBMANAGER SET?")
            return -1
        self.logCalcSettings()
        fmin = self.input_min[1]
        fmax = self.input_min[2]
        
        start_time = time.time()
        sample = pd.DataFrame([self.input_min], columns=self.input_name)
        samples = pd.DataFrame()

        seed(1037)
        mynsgaii=nsgaii_np.nsgaii()
        mynsgaii.nobj = 2
        mynsgaii.pmut_real = 0.1
        mynsgaii.eta_m = 1  ## coff for mutation
        mynsgaii.popsize = 20
        mynsgaii.generation = 20
        #min_realvar=[0,-10,-10,-10,-10,-10,-10,-10,-10,-10,-10]
        #max_realvar=[1,+10,+10,+10,+10,+10,+10,+10,+10,+10,+10]
        model = tm020cav()
        icallback = nsgaii_helper.fnds_callback_create_Image(savedir="result/nsgaTM020output")
        
        mynsgaii.nval = model.n
        min_realvar_raw, max_realvar_raw = model.getBoundaries()
        mynsgaii.min_realvar, mynsgaii.max_realvar =np.array(min_realvar_raw),np.array(max_realvar_raw)
        print(mynsgaii.min_realvar)
        
        sttime = time.time()
        icallback.setNewSavedir(model.name)
        poplist = mynsgaii.nsgaii_generation_parallel(model, fnds_callback=icallback)
        result = mynsgaii.fnds(poplist)
        endtime = time.time()
        print("elapsed time=", endtime - sttime)

        fp = open(icallback.savedir / "result.txt", "w")
        ###STATS
        front = result[0]
        fsize = len(front)
        print("Front Size:%d" % fsize, file=fp)
        for ind in front:
            print("Id:%d Value:" % ind.id, ind.value, file=fp)
        fp.close()
        
    

        


        end_time = time.time()
        print(start_time - end_time)
        self.log.close()
        
        return 0


if __name__ == "__main__":
    pass


