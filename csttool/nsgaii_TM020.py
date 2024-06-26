"""produce LHS sample"""
###修改内容
###runWithX 修改为 runWithParam 需要提供param_name_list 和 value_list 作为参数
###addTask 同上
###初值需要自己写，留空[]则为默认
###
import os
from .myAlgorithm import myAlg
from random import random, seed, shuffle, choices,sample
from math import inf, sqrt, floor
from time import sleep
import matplotlib.pyplot as plt
import numpy as np
from . import cstmanager
from utils import mode_util_sample
import time
import pandas as pd
import json
from pathlib import Path
import threading
import multiprocessing
from typing import List, Set
from utils.mode_util_sample import findTM020index
from copy import deepcopy
class nsgaii_var:
    id = 0
    idlock=threading.Lock()
    def __init__(self, value) -> None:
        self.value = np.array(value)
        self.rank = 0
        self.obj = None
        self.pset: Set[
            nsgaii_var
        ] = set()  ### set of var domed by p ### By Ref so it might be memory safe
        self.done = False
        self.sorted = False
        self.n = 0
        self.crowed_dis = 0
        self.crowed_dis_calc_done = False
        
        self.constraint_obj=None
        self.constraint_violaton_value=0
        self.id = nsgaii_var._getNewAvailableId()
        
    @classmethod
    def _getNewAvailableId(cls):
        cls.idlock.acquire()
        cls.id += 1
        cls.idlock.release()
        return cls.id

    def duplicate(self)-> "nsgaii_var":
        #### Get An Unsorted Var Duplicate
        dup=nsgaii_var(self.value)
        dup.obj=self.obj.copy()        
        return dup
    def setObjs(self, objective):
        self.obj = np.array(objective)
    def setConstraint_objs(self, c_objective):
        self.constraint_obj = np.array(c_objective)
    def dom(self, other):
        tarray = np.less(self.obj,other.obj)
        earray = np.less_equal(self.obj,other.obj)
        if np.all(earray) and np.any(tarray):
            return True  ### A N Domi B
        else:
            return False
    def constrained_dom(self,other):
        if self.constraint_violaton_value==0 and other.constraint_violaton_value>0:
            return True
        elif self.constraint_violaton_value>0 and other.constraint_violaton_value==0:
            return False
        if self.constraint_violaton_value<other.constraint_violaton_value:
            return True
        elif self.constraint_violaton_value>other.constraint_violaton_value:
            return False
        else:
            return self.dom(other) 
    def crowed_cmp_lt(self, other):
        if self.rank < other.rank:
            return True
        elif self.rank == other.rank:
            if self.crowed_dis > other.crowed_dis:
                return True
        return False

    def crowed_cmp_gt(self, other):
        if self.rank > other.rank:
            return True
        elif self.rank == other.rank:
            if self.crowed_dis < other.crowed_dis:
                return True
        return False

    def crowed_cmp_eq(self, other):
        if self.rank == other.rank and self.crowed_dis == other.crowed_dis:
            return True
        else:
            return False

    def __str__(self):
        # idict={"id":self.id,"Rank":self.rank,"N":self.n}
        idict = {"id": self.id}
        str = json.dumps(idict, indent=4)
        return str

    def __repr__(self) -> str:
        str = "nsgaii_var obj:" + self.__str__()
        return str

    def __eq__(self, __o: object) -> bool:
        if self.id!=__o.id:
            return False
        return True

    def __hash__(self):
        return hash(self.id)
    
def constraint_function_TM020(iconstrained_obj,iobj):
    ###iconstrained_obj: Frequency
    ### abs(Frequency-1500)<threshold
    threshold=0.05
    constraint_violaton_value=abs(1500-iconstrained_obj[0]) 
    if constraint_violaton_value<threshold:
        constraint_violaton_value=0
    return constraint_violaton_value

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

        ##WORKER
        self.manager = None
        if manager is not None:
            self.setJobManager(manager)
            
        # self.results=result.result
        
        # input 5-dims 
        # Req 180-200mm
        # Leq 60-120mm
        # I0 5-20mm
        # R0 5-20mm
        # I1 5-20mm
        
        # output 4-dims
        # freq 1500Mhz
        # R over Q
        # Q
        # Shunt-dep
        
        ##### NSGA OPTIONS #####
        self.nobj = 3
        self.nval = 5
        self.pmut_real = 0.1
        self.eta_m = 1  ## coff for mutation
        self.popsize = 4
        self.generation = 2
        

        self.min_realvar = []
        self.max_realvar = []
        
        self.constrained=True
        if self.constrained:
            self.constraint_func=constraint_function_TM020
        else:
            self.constraint_func=None
        
        
        self.input_name_opt = ["Leq", "Req","I0","R0","I1"]
        self.input_name = ["Leq", "Req","I0","R0","I1"]
        self.input_min = [60, 180,5,5,5]  ##初始值
        self.input_max = [120, 200,20,20,20]  ##初始值

        self.constrained_object_name = ["frequency_offset_abs"]
        self.object_name = [
            "R_divide_Q",
            "Q-factor",
            "Shunt_Inpedence",
        ]
        self.output_name = [
            "frequency",
            "R_divide_Q",
            "Q-factor",
            "Shunt_Inpedence",
        ]
        


        
        
    def param_check(self):
        #assert self.nobj==len(self.min_realvar)
        #assert self.nobj==len(self.max_realvar)
        if self.constrained==True:
            assert self.constraint_func is not None

    def constrained_dominance(self,flist: List[nsgaii_var]):
        if len(flist) == 0:
            return
        if self.constraint_func is None:
            return
        for ivar in flist:
            iobj=ivar.obj
            iconstrained_obj=ivar.constrained_obj
            ivar.constraint_violaton_value=self.constraint_func(iconstrained_obj,iobj)
            
    def fnds(self,vallist: List[nsgaii_var]):  ## Fast non dominated sort

        flist: List[List[nsgaii_var]] = [None for _ in range(len(vallist))]
        flist[0] = list()
        #### Get All Dom Relations
        for p in vallist:
            for q in vallist:
                if p.id == q.id:
                    continue

                if not self.constrained:  ####Type 1 支配排序
                    if p.dom(q):
                        p.pset.add(q)  ### I DOM YOU
                    elif q.dom(p):
                        p.n += 1  ## Be Domed count
                else:
                    if p.constrained_dom(q):
                        p.pset.add(q)  ### I DOM YOU
                    elif q.constrained_dom(p):
                        p.n += 1  ## Be Domed count

            if p.n == 0:  ## not domed By Anyone
                p.rank = 1  ### first front
                flist[0].append(p)

        #### Sort
        i = 0

        while len(flist[i]) > 0:
            #print([str(p.n) for p in vallist])

            q_set = list()
            for p in flist[i]:

                for q in p.pset:
                    q.n -= 1  ### 除p外q仍被支配的个数
                    if q.n == 0:  ### not domed By Anyone Except P
                        q.rank = i + 1
                        q_set.append(q)

            i += 1

            flist[i] = list(q_set)

        return flist


    def crowding_dis_assign(self,
        flist: List[nsgaii_var],
    ):  # sort vars by the distance of objectives

        if len(flist) == 0:
            return
        elif len(flist) <= 2:
            for var in flist:
                var.crowed_dis = inf
                var.crowed_dis_calc_done = True
            return
        for i in range(self.nobj):
            ilist = sorted(flist, key=lambda x: x.obj[i])
            ilist[0].crowed_dis = inf
            ilist[0].crowed_dis_calc_done = True
            ilist[-1].crowed_dis = inf
            ilist[-1].crowed_dis_calc_done = True
            coff = ilist[-1].obj[i] - ilist[0].obj[i]
            for u in range(len(ilist)):
                if not ilist[u].crowed_dis_calc_done:
                    if ilist[u + 1].obj[i] == ilist[u - 1].obj[i]:
                        ilist[u].crowed_dis += 0
                    else:
                        ilist[u].crowed_dis += (
                            ilist[u + 1].obj[i] - ilist[u - 1].obj[i]
                        ) / coff


    def crossover_real_SBX_np(self,par1, par2):

        uarray = np.random.random(self.nval)
        barray = np.less_equal(uarray, 0.5)
        nbarray = np.logical_not(barray)
        gamma = np.sqrt(2 * uarray) * barray + np.sqrt(0.5 / (1 - uarray)) * nbarray
        val1 = 0.5 * ((1 + gamma) * par1.value + (1 - gamma) * par2.value)
        val2 = 0.5 * ((1 - gamma) * par1.value + (1 + gamma) * par2.value)

        val1=np.clip(val1,self.min_realvar,self.max_realvar)
        val2=np.clip(val2,self.min_realvar,self.max_realvar)
        child1 = nsgaii_var(val1)
        child2 = nsgaii_var(val2)
        return child1, child2


    def mutation_real_np(self,ind: nsgaii_var):

        rnd = np.random.random(self.nval)
        barray = np.less(rnd, self.pmut_real)
        rnd2 = np.random.random(self.nval)
        barray2 = np.less_equal(rnd2, 0.5)
        nbarray2 = np.logical_not(barray2)
        v = ind.value
        vl = np.array(self.min_realvar)
        vu = np.array(self.max_realvar)
        delta1 = (v - vl) / (vu - vl)
        delta2 = (vu - v) / (vu - vl)
        mut_pow = 1.0 / (self.eta_m + 1.0)

        ##rnd2<=0.5
        xy1 = (1.0 - delta1)*barray2
        val1 = 2.0 * rnd2 + (1.0 - 2.0 * rnd2) * xy1 **(self.eta_m + 1.0)
        deltaq1 = val1** mut_pow - 1.0

        xy2 = (1.0 - delta2)*nbarray2
        val2 = 2.0 * (1.0 - rnd2) + 2.0 * (rnd2 - 0.5) * xy2** (self.eta_m + 1.0)
        deltaq2 = 1.0 - val2** mut_pow

        v = v + (deltaq1 * barray2 + deltaq2 * nbarray2) * (vu - vl)
        np.clip(v, vl, vu, v)
        v = v * barray
        v=np.clip(v,self.min_realvar,self.max_realvar) ###boundary check
        ind.value = v


    def tournament(self,ind1: nsgaii_var, ind2: nsgaii_var):
        if ind1.crowed_cmp_lt(ind2):
            return ind1
        elif ind1.crowed_cmp_gt(ind2):
            return ind2
        else:
            rnd = random()
            if rnd <= 0.5:
                return ind1
            else:
                return ind2


    def offspring_gen(self,inpop: List[nsgaii_var]):
        offspop = []
        quart_size = floor(len(inpop) / 4)
        shuffle(inpop)
        for i in range(quart_size):
            par1 = self.tournament(inpop[i], inpop[i + 1])
            par2 = self.tournament(inpop[i + 2], inpop[i + 3])
            child1, child2 = self.crossover_real_SBX_np(par1, par2)
            offspop.append(child1)
            offspop.append(child2)
        shuffle(inpop)
        for i in range(quart_size):
            par1 = self.tournament(inpop[i], inpop[i + 1])
            par2 = self.tournament(inpop[i + 2], inpop[i + 3])
            child1, child2 = self.crossover_real_SBX_np(par1, par2)
            offspop.append(child1)
            offspop.append(child2)
        
        #### IF size mod 4 !=0
        extra = len(inpop) - len(offspop)
        if extra > 0:
            ichoice = choices(inpop, k=extra * 4)
            for i in range(extra):
                par1 = self.tournament(ichoice[i], ichoice[i + 1])
                par2 = self.tournament(ichoice[i + 2], ichoice[i + 3])
                child1, child2 = self.crossover_real_SBX_np(par1, par2)
                rnd = random()
                if rnd <= 0.5:
                    offspop.append(child1)
                else:
                    offspop.append(child2)
        ### MUTATION

        for child in offspop:
            self.mutation_real_np(child)
        #print("offspring pop",len(offspop))
        return offspop

    def err_norm(self):
        pass
    def random_sampling_LHS_np(self,nsamples):
        ###FAST RANDOM USE NUMPY
        ranlist=np.random.random((nsamples,self.nval))
        jarray=np.mgrid[0:nsamples,0:self.nval][0]
        for colomn in jarray.T:
            np.random.shuffle(colomn)    
        ranlist=(ranlist+jarray)/nsamples
        return ranlist


    def calc_fnds_size(self,fnds_arr):
        sum=0
        for list in fnds_arr:
            if list is not None:
                sum+=len(list)
        return sum

    def nsgaii_generation_demo(self,model, fnds_callback=None):  ##
        self.param_check()
        ### fnds_callback for mid output

        valarr = self.random_sampling_LHS_np(self.popsize)
        val_width=self.max_realvar-self.min_realvar
        valarr=valarr*val_width+self.min_realvar


        poplist = []
        acceptedpop = []

        for var in valarr:
            ind = nsgaii_var(var)
            poplist.append(ind)
        imodel = model
        for igen in range(self.generation):
            ###WORK To get Obj

            for ind in poplist:
                ind.setObjs(list(imodel(ind.value)))
            
            childpoplist = self.offspring_gen(poplist)
            
            for ind in childpoplist:
                ind.setObjs(list(imodel(ind.value)))
            ###DONE
            poplist = poplist + childpoplist

            if self.constrained:
                self.constrained_dominance(poplist)

            fndsresult = self.fnds(poplist)
            #print("FNDS_SIZE",calc_fnds_size(fndsresult),"INPOP:",len(poplist))
            if fnds_callback is not None:
                fnds_callback(igen, fndsresult)
            ###find accept
            acceptedpop.clear()
            pack = self.popsize
            for iset in fndsresult:

                #print("PACK=%d" %pack)
                if pack <= 0:
                    break
                if not iset:
                    continue
                if pack >= len(iset):
                    for ind in iset:
                        acceptedpop.append(ind)
                    pack -= len(iset)
                    
                else:
                    curfront = list(iset)
                    self.crowding_dis_assign(curfront)
                    curfront.sort(key=lambda x: x.crowed_dis, reverse=True)  ###按最大拥挤距离排序
                    n2p = pack
                    #print("LAST FRONT:%d"%n2p)
                    acceptedpop += curfront[0:n2p]
                    pack=0
                #print("    ACC PROP SIZE:%d"%len(acceptedpop),"TO GO:%d" %pack)
            poplist.clear()
            poplist += acceptedpop
            print("GEN:%d DONE, SIZE:%d" % (igen,len(acceptedpop)))
            ### GEN DONE
        return poplist
    
    def nsgaii_generation_parallel(self,fnds_callback=None):  ##
        self.param_check()
        ### fnds_callback for mid output
        if not isinstance(fnds_callback,list):
            fnds_callback=[fnds_callback]
            
        valarr = self.random_sampling_LHS_np(self.popsize)
        val_width=self.max_realvar-self.min_realvar
        valarr=valarr*val_width+self.min_realvar


        poplist:List[nsgaii_var] = []
        acceptedpop:List[nsgaii_var] = []

        for var in valarr:
            ind = nsgaii_var(var)
            poplist.append(ind)
        
        #### OPTIMIZAION 
        # PARAMETER SPACE
        # Req 180-200mm
        # Leq 60-120mm
        # I0 5-20mm
        # R0 5-20mm
        # I1 5-20mm
        # OBJETIVE
        # FREQ |F_fm-F_obj|<0.05
        # MINIMUM ROQ
        # MAXIMUM Shunt Impedence
        # MAXIMUM Q
        ####

        #First Run To Get the Initial Pop
        for ind in poplist:
            JobName="Init_Pop_"+str(ind.id)
            params=self.createParamDictFromNPvar(ind.value)
            self.manager.addTask(params=params,job_name=JobName)
        ###
        self.manager.startProcessing()
        ### WAIT 
        ### TIME For Processing And Results

        ### Get Results
        results=self.manager.getFullResults()

        ####Sort Results        
        results.sort(key=lambda ele:ele["RunName"].split("_")[2])
        print(results)

        objlist,c_objlist=self.convertSortedResultsListToNumpyList(results)
        #### Apply Results To Element
        for i in range(len(poplist)):        
            poplist[i].setObjs(objlist[i])
        if self.constrained:
            for i in range(len(poplist)):    
                poplist[i].setConstraint_objs(c_objlist[i])
        for igen in range(self.generation):           

            childpoplist = self.offspring_gen(poplist)      
            #Run To Get the Children POP
            for ind in childpoplist:
                # flag=False
                # ###CHECK IF ALREADY CALCULATED
                # for indc in poplist:
                #     if ind.value == indc.value:
                #         ind.obj = deepcopy(indc.obj)
                #         ind.done= True
                #         flag=True
                # if flag:
                #     continue
                JobName="GEN_%d_"%igen+str(ind.id)
                params=self.createParamDictFromNPvar(ind.value)
                self.manager.addTask(params=params,job_name=JobName)
            ###
            self.manager.startProcessing()
            ### WAIT 
            ### TIME For Processing And Results

            ### Get Results
            results=self.manager.getFullResults()
            ####Sort Results        
            results.sort(key=lambda ele:ele["RunName"].split("_")[2])
            objlist,c_objlist=self.convertSortedResultsListToNumpyList(results)

            #### Apply Results To Element           
            for i in range(len(childpoplist)):        
                childpoplist[i].setObjs(objlist[i])
            if self.constrained:
                for i in range(len(childpoplist)):    
                    childpoplist[i].setConstraint_objs(c_objlist[i])

            ###DONE
            poplist = poplist + childpoplist

            # if len(poplist)<self.popsize: ###check for unfinished calcs and dup random results
            #     self.logger.warning("Too Few Pop Results Calculated at gen:%d."%igen)
            #     cnt2dup=self.popsize-len(poplist)
            #     sampled=sample(poplist,cnt2dup)
            #     duplist=[src.dup() for src in sampled]
            #     poplist+=duplist


            fndsresult = self.fnds(poplist)
            #print("FNDS_SIZE",calc_fnds_size(fndsresult),"INPOP:",len(poplist))
            if len(fnds_callback)>0:
                for ifnds in fnds_callback:
                    ifnds(igen, fndsresult)
            ###find accepted
            acceptedpop.clear()
            pack = self.popsize  ###NEEDED TO 
            
            for iset in fndsresult:

                #print("PACK=%d" %pack)
                if pack <= 0:
                    break
                if not iset:
                    continue
                if pack >= len(iset):
                    for ind in iset:
                        acceptedpop.append(ind)
                    pack -= len(iset)
                    
                else:
                    curfront = list(iset)
                    self.crowding_dis_assign(curfront)
                    curfront.sort(key=lambda x: x.crowed_dis, reverse=True)  ###按最大拥挤距离排序
                    n2p = pack
                    #print("LAST FRONT:%d"%n2p)
                    acceptedpop += curfront[0:n2p]
                    pack=0
                #print("    ACC PROP SIZE:%d"%len(acceptedpop),"TO GO:%d" %pack)
            poplist.clear()
            poplist += acceptedpop
            print("GEN:%d DONE, SIZE:%d" % (igen,len(acceptedpop)))
            ### GEN DONE
        return poplist
    
   

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
        self.checkAndSetReady()



    def logCalcSettings(self):
        print(self.getEditableAttrs())
        pass


    

    def getTM020Result(self,runresult):
        ppsr=runresult["PostProcessResult"]
        for ips in ppsr:
            if ips["resultName"] =="Mode_Rec":
                mode_result=ips["value"] 
                
            
        tm020index=-1
        for i in range(0,len(mode_result)):
            c=mode_result[i]
            if c[1]=='HX_TM' or c[1] =='TM':
                if c[2]==0 and c[3]==2 and c[4]==0:
                    tm020index=c[0]
                    break
        querystring="ModeIndex "+str(tm020index)
        nppsr=deepcopy(ppsr)
        ar={}
        for ips in nppsr:
            if ips["resultName"] =="Mode_Rec":
                continue
            else:
                key=ips["resultName"]
                value=ips["value"][querystring]
                ar.update({key:value})
                
                
            
        processedResult={
        "WorkerID": runresult.get("WorkerID"),
        "TaskIndex": runresult.get("TaskIndex"),
        "TaskStatus": runresult.get("TaskStatus"),
        "RunName": runresult.get("RunName"),
        "RunParameters": runresult.get("RunParameters"),
        "TM020Index" : tm020index,
        "PostProcessResult":ar
        }
        return processedResult
    def createParamDictFromNPvar(self,var):
        odict={}
        for i in range(len(self.input_name)):
            key=self.input_name[i]
            value=var[i]
            odict.update({key:value})
        return odict
    def convertSortedResultsListToNumpyList(self,resultslist_sorted):
        objlist=[]
        c_objlist=[]
        for iresult in resultslist_sorted:     
            pResult=self.getTM020Result(iresult) 
            #SAVE Full and TM020 Results
            
            fp=open(self.manager.resultDir /(str(iresult["RunName"])+"_Result.json"),"w")
            json.dump(iresult,fp,indent=4)
            fp.close()
            fp=open(self.manager.resultDir /(str(iresult["RunName"])+"_TM020Result.json"),"w")
            json.dump(pResult,fp,indent=4)
            fp.close()
            # DONE
            iobj_list=[]
            c_iobj_list=[]
            for oname in self.object_name:
                iobj_list.append(pResult["PostProcessResult"][oname]) 
            c_iobj_list.append(pResult["PostProcessResult"]["frequency"])
            
                
            ### Custom Func
            # OBJETIVE
            # MINIMUM ROQ
            # MAXIMUM Q
            # MAXIMUM Shunt Impedence
            # CONSTRAINT OBJECTIVE
            # abs|F_fm-F_obj|<0.05
            ####
            indarray=np.array(iobj_list)      
            cindarray=np.array(c_iobj_list)      
            objlist.append(indarray)
            c_objlist.append(cindarray)
        return objlist,c_objlist
    def start2(self):
        
        # resultPath=self.manager.resultDir / "TestResult.json"
        
        # params={"Leq":90,"Req":190}
        # result=self.manager.runWithParam(params=params,job_name="test")
        # print(result)
        # params={"Leq":60,"Req":180}
        # result=self.manager.runWithParam(params=params,job_name="test2")
        # print(result)

        # params1={"Leq":90,"Req":190}
        # self.manager.addTask(params=params1,job_name="TEST01")
        # params2={"Leq":60,"Req":180}
        # self.manager.addTask(params=params2,job_name="TEST02")   
        
        # params1={"Leq":100,"Req":190}
        # self.manager.addTask(params=params1,job_name="TEST03")
        # params2={"Leq":60,"Req":160}
        # self.manager.addTask(params=params2,job_name="TEST04")
        
        # self.manager.startProcessing()            
        resultPath=r"F:\programs\cst_tools\test\TestResult.json"
        fp=open(resultPath,"r")
        results=json.load(fp)
        pr=self.getTM020Result(results[0])
        print(pr)
        #results=self.manager.getFullResults()
    
        
        # fp=open(resultPath,"w")
        # json.dump(results,fp,indent=4)
        # fp.close()
        
        #print(results)
        pass
    def start(self):
        if self.ready == False:
            print("CALCATION NOT READY, PLEASE CHECK SETTINGS.")
            print("IS THE JOBMANAGER SET?")
            return -1
        self.logCalcSettings()
        
        start_time = time.time()
        sample = pd.DataFrame([self.input_min], columns=self.input_name)
        samples = pd.DataFrame()

        seed(1037)
        resultDir=self.manager.resultDir
        icallback = fnds_callback_create_Image(savedir=resultDir)
        icallback2 =fnds_callback_dump_individuals(savedir=resultDir,input_names=self.input_name,objnames=self.object_name,cobjnames=self.constrained_object_name,constrainted=self.constrained)
        #self.nval = model.n
        min_realvar_raw, max_realvar_raw = self.input_min,self.input_max
        self.min_realvar, self.max_realvar =np.array(min_realvar_raw),np.array(max_realvar_raw)
        print(self.min_realvar)
        
        sttime = time.time()

        poplist = self.nsgaii_generation_parallel(fnds_callback=[icallback,icallback2])
        result = self.fnds(poplist)
        endtime = time.time()
        print("elapsed time=", endtime - sttime)

        
    

        


        end_time = time.time()
        print(start_time - end_time)
        
        return 0

class fnds_callback_dump_individuals():
    def __init__(self,savedir="",input_names:List=[],objnames:List=[],cobjnames:List=[],constrainted=False) -> None:
        self.setNewSavedir(savedir)
        self.constrainted=constrainted
        self.input_names=input_names
        self.objnames=objnames
        self.cobjnames=cobjnames
    def setNewSavedir(self,savedir):
        self.savedir=Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)
    def __call__(self,igen,fndslist):
        iprocess=multiprocessing.Process(target=dump_individual_worker_func,args=(self.savedir,igen,fndslist,self.input_names,self.objnames,self.cobjnames,self.constrainted))
        iprocess.start()
        
def dump_individual_worker_func(savedir:Path,igen,fndslist:List[List[nsgaii_var]],input_names:List,objnames:List,cobjnames:List,constrainted=False):
    data_list_all=[]
    data_row_list=[]
    prefix_name=["Generation","Index","Front Index"]
    columnlist=prefix_name+input_names+objnames
    if constrainted:
        columnlist+=cobjnames
        
    print(columnlist)
    
    for ifnd,fnd in enumerate(fndslist):
        if fnd is not None:
            for indv in fnd:
                data_row_list.clear()
                data_row_list+=[igen,indv.id,ifnd]
                data_row_list+=indv.value.tolist()
                data_row_list+=indv.obj.tolist()
                if constrainted:
                    data_row_list+=indv.constraint_obj.tolist()
                data_list_all.append(data_row_list)

    csv=pd.DataFrame(data_list_all,columns=columnlist)
    fp=open(savedir /("GEN_%d_Individuals.csv"%igen),"w" )
    csv.to_csv(fp)
    fp.close()
    return 
    
class fnds_callback_create_Image():
    def __init__(self,savedir="") -> None:
        self.setNewSavedir(savedir)
        
    def setNewSavedir(self,savedir):
        self.savedir=Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)
    def __call__(self,igen,fndslist):
        iprocess=multiprocessing.Process(target=image_worker_func,args=(self.savedir,igen,fndslist))
        iprocess.start()
        return 
def image_worker_func(savedir,igen,fndslist:List[List[nsgaii_var]]):
    x0=[]
    y0=[]
    x1=[]
    y1=[]
    x2=[]
    y2=[]
    if fndslist[0] is not None:
        for ind in fndslist[0]:
            x0.append(ind.obj[0])
            y0.append(ind.obj[1])
        plt.scatter(x0,y0,c='none',marker='o', edgecolors='r')
    if fndslist[1] is not None:
        for ind in fndslist[1]:
            x1.append(ind.obj[0])
            y1.append(ind.obj[1])
        plt.scatter(x1,y1,c='none',marker='o', edgecolors='orange')
    if fndslist[2] is not None:
        for ind in fndslist[2]:
            x2.append(ind.obj[0])
            y2.append(ind.obj[1])      
        plt.scatter(x2,y2,c='none',marker='o', edgecolors='y')

    plt.xlabel('abs(freq-1500)')
    plt.ylabel('roq')
    #plt.axis('scaled')
    plt.savefig(savedir / ('GEN_%05d_Front.png' %igen), bbox_inches='tight')
    return

if __name__ == "__main__":
    pass


