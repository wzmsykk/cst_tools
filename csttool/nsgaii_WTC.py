"""produce LHS sample"""

###修改内容
###runWithX 修改为 runWithParam 需要提供param_name_list 和 value_list 作为参数
###addTask 同上
###初值需要自己写，留空[]则为默认
###
import os
from .myAlgorithm import myAlg
from random import random, seed, shuffle, choices, sample
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
    idlock = threading.Lock()

    def __init__(self, value) -> None:

        self.value = np.array(value)  ###For optim
        self.simvalue = None  ###all implicit and explicit varaiables for simulation generated from self.value
        self.rank = 0
        self.rawobj = (
            None  # Save all mid and final values for record (self.output+self.mid)
        )
        self.obj = None  # Save Objective transformed for minimum search (self.obj)
        self.pset: Set[nsgaii_var] = (
            set()
        )  ### set of var domed by p ### By Ref so it might be memory safe
        self.done = False
        self.sorted = False
        self.n = 0
        self.crowed_dis = 0
        self.crowed_dis_calc_done = False
        self.constrainted_obj = None
        self.constraint_violaton_value = 0
        self.id = nsgaii_var._getNewAvailableId()

    @classmethod
    def _getNewAvailableId(cls):
        cls.idlock.acquire()
        cls.id += 1
        cls.idlock.release()
        return cls.id

    def duplicate(self) -> "nsgaii_var":
        #### Get An Unsorted Var Duplicate
        dup = nsgaii_var(self.value)
        dup.obj = self.obj.copy()
        return dup

    def setRawObjs(self, rawobjective):
        self.rawobj = np.array(rawobjective)

    def setObjs(self, objective):
        self.obj = np.array(objective)

    def setConstrainted_objs(self, c_objective):
        self.constrainted_obj = np.array(c_objective)

    def setSimValue(self, simvalue):
        self.simvalue = np.array(simvalue)

    def dom(self, other):
        ### FIND MINIMUM
        tarray = np.less(self.obj, other.obj)
        earray = np.less_equal(self.obj, other.obj)
        if np.all(earray) and np.any(tarray):
            return True  ### A N Domi B
        else:
            return False

    def constrainted_dom(self, other):
        if self.constraint_violaton_value < other.constraint_violaton_value:
            return True
        elif self.constraint_violaton_value > other.constraint_violaton_value:
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
        if self.id != __o.id:
            return False
        return True

    def __hash__(self):
        return hash(self.id)


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

        # input 2-dims
        # g 300-600mm
        # L 600-1800mm
        # I0 5-20mm
        # R0 5-20mm
        # I1 5-20mm

        # output 3-dims
        # frequency = 44.4MHz
        # Epk@2MV <7.5MV
        # Shunt-dep >28MOhm

        ##### NSGA OPTIONS #####
        self.nobj = 3
        self.nval = 3
        self.pmut_real = 0.1
        self.eta_m = 1  ## coff for mutation
        self.popsize = 4
        self.generation = 2

        self.min_realvar = []
        self.max_realvar = []

        self.constrainted = True
        if self.constrainted:
            self.constraint_func = self.constraint_function_WTC
        else:
            self.constraint_func = None

        self.input_name_opt = ["g", "L", "d0"]
        self.input_name = ["g", "L", "d0"]
        self.input_min = [300, 1200, 45]  ##初始值 for sim
        self.input_max = [600, 1800, 60]  ##初始值

        self.require_sim_input_transfrom = (
            True  #### IF TRUE disables input_mins and use values below instead
        )
        self.sim_input_conv_method = self.simtransfromfunc
        self.opt_input_name = ["part_L_to_g", "L", "d0"]
        self.opt_input_min = [0.05, 600, 45]  ##初始值 for opt
        self.opt_input_max = [0.49, 1800, 60]  ##初始值
        ####
        ####
        # g<L/2
        ####

        self.output_name = [  ### values provided by sim
            "Frequency (Mode 1)",
            "R over Q beta=1 (Mode 1)",
            "Q-Factor (Perturbation) (Mode 1)",
            "Shunt Impedance (Pertubation) beta=1 (Mode 1)",
            "Voltage beta=1 (Mode 1)",
            "face1_Max_e",
            "face1_Max_h",
        ]
        self.info_name = [
            "beta",
            "Epk@2MV",
            "Hpk@2MV",
        ]  ###not used for optim but used for info and Mid Calc

        self.object_name = [  ### target name
            "frequency_offset",
            "Epk@2MV",
            "Shunt_Inpedence",
        ]
        self.constrainted_object_name = ["Frequency (Mode 1)"]

        ##### Freq Options
        self.targetfreq = 44.4
        self.freqthreshold = 0.05
        self.freqlockmut = False
        self.freqstr = "Frequency (Mode 1)"
        self.freqdomstr = None

        #### SET RANGE
        if self.require_sim_input_transfrom:
            min_realvar_raw, max_realvar_raw = self.opt_input_min, self.opt_input_max
        else:
            min_realvar_raw, max_realvar_raw = self.input_min, self.input_max
        self.min_realvar, self.max_realvar = np.array(min_realvar_raw), np.array(
            max_realvar_raw
        )

    def simtransfromfunc(self, altinput):

        ####
        # g<L/2
        # self.alt_input_name=["part_L_to_g","L","d0"]
        # g=part_L_to_g*L
        ####
        oarr = np.array(altinput)
        oarr[0] = oarr[1] * oarr[0]
        return oarr

    def constraint_function_WTC(self, iconstrainted_obj, iobj):
        ###iconstrainted_obj: Frequency
        ### abs(Frequency-1500)<threshold

        constraint_violaton_value = abs(self.targetfreq - iconstrainted_obj[0])
        if constraint_violaton_value < self.freqthreshold:
            constraint_violaton_value = 0
        return constraint_violaton_value

    def getFullNameList(self):
        namelist = []
        namelist = namelist + self.input_name
        if self.require_sim_input_transfrom:
            namelist += self.opt_input_name
        namelist += self.output_name + self.info_name + self.object_name
        if self.constrainted:
            namelist += self.constrainted_object_name
        return namelist

    def param_check(self):
        # assert self.nobj==len(self.min_realvar)
        # assert self.nobj==len(self.max_realvar)
        if self.constrainted == True:
            assert self.constraint_func is not None

    def constrainted_dominance(self, flist: List[nsgaii_var]):
        if len(flist) == 0:
            return
        if self.constraint_func is None:
            return
        for ivar in flist:
            iobj = ivar.obj
            iconstrainted_obj = ivar.constrainted_obj
            ivar.constraint_violaton_value = self.constraint_func(
                iconstrainted_obj, iobj
            )

    def fnds(self, vallist: List[nsgaii_var]):  ## Fast non dominated sort

        flist: List[List[nsgaii_var]] = [None for _ in range(len(vallist))]
        flist[0] = list()
        #### Get All Dom Relations
        for p in vallist:
            for q in vallist:
                if p.id == q.id:
                    continue

                if not self.constrainted:  ####Type 1 支配排序
                    if p.dom(q):
                        p.pset.add(q)  ### I DOM YOU
                    elif q.dom(p):
                        p.n += 1  ## Be Domed count
                else:
                    if p.constrainted_dom(q):
                        p.pset.add(q)  ### I DOM YOU
                    elif q.constrainted_dom(p):
                        p.n += 1  ## Be Domed count

            if p.n == 0:  ## not domed By Anyone
                p.rank = 0  ### first front
                flist[0].append(p)

        #### Sort
        i = 0

        while len(flist[i]) > 0:
            # print([str(p.n) for p in vallist])
            q_set = set()
            for p in flist[i]:

                for q in p.pset:
                    q.n -= 1  ### 除p外q仍被支配的个数
                    if q.n == 0:  ### not domed By Anyone Except P
                        q.rank = i + 1
                        q_set.add(q)

            i += 1
            if i >= len(flist):
                break
            flist[i] = list(q_set)

        return flist

    def crowding_dis_assign(
        self,
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

    def crossover_real_SBX_np(self, par1, par2):

        uarray = np.random.random(self.nval)
        barray = np.less_equal(uarray, 0.5)
        nbarray = np.logical_not(barray)
        gamma = np.sqrt(2 * uarray) * barray + np.sqrt(0.5 / (1 - uarray)) * nbarray
        val1 = 0.5 * ((1 + gamma) * par1.value + (1 - gamma) * par2.value)
        val2 = 0.5 * ((1 - gamma) * par1.value + (1 + gamma) * par2.value)

        val1 = np.clip(val1, self.min_realvar, self.max_realvar)
        val2 = np.clip(val2, self.min_realvar, self.max_realvar)
        child1 = self.new_nsgaii_var(val1)
        child2 = self.new_nsgaii_var(val2)
        return child1, child2

    def mutation_real_np(self, ind: nsgaii_var):

        rnd = np.random.random(self.nval)
        barray = np.less(rnd, self.pmut_real)
        rnd2 = np.random.random(self.nval)
        barray2 = np.less_equal(rnd2, 0.5)
        nbarray2 = np.logical_not(barray2)
        v = np.array(ind.value)
        vl = np.array(self.min_realvar)
        vu = np.array(self.max_realvar)
        delta1 = (v - vl) / (vu - vl)
        delta2 = (vu - v) / (vu - vl)
        mut_pow = 1.0 / (self.eta_m + 1.0)

        ##rnd2<=0.5
        xy1 = (1.0 - delta1) * barray2
        val1 = 2.0 * rnd2 + (1.0 - 2.0 * rnd2) * xy1 ** (self.eta_m + 1.0)
        deltaq1 = val1**mut_pow - 1.0

        xy2 = (1.0 - delta2) * nbarray2
        val2 = 2.0 * (1.0 - rnd2) + 2.0 * (rnd2 - 0.5) * xy2 ** (self.eta_m + 1.0)
        deltaq2 = 1.0 - val2**mut_pow

        v = v + (deltaq1 * barray2 + deltaq2 * nbarray2) * (vu - vl)
        np.clip(v, vl, vu, v)
        v = v * barray + np.array(ind.value) * np.logical_not(barray)  ### BUGFIX
        v = np.clip(v, self.min_realvar, self.max_realvar)  ###boundary check
        ind.value = v

    def mutation_real_np_freqlock(self, ind: nsgaii_var):
        ####
        # Dom Req main factor of Freq
        ####
        try:
            domfactorindex = self.input_name.index("Req")
            domfactorexist = True
        except ValueError:
            domfactorexist = False
        try:
            targetvalueindex = self.object_name.index("frequency")
            targetexist = True
        except ValueError:
            targetexist = False

        rnd = np.random.random(self.nval)

        barray = np.less(rnd, self.pmut_real)
        mask = np.ones_like(barray)
        mask[domfactorindex] = 0
        barray = barray * mask
        ### NO auto mutation for Dom Req main factor

        rnd2 = np.random.random(self.nval)
        barray2 = np.less_equal(rnd2, 0.5)
        nbarray2 = np.logical_not(barray2)
        v = np.array(ind.value)
        vl = np.array(self.min_realvar)
        vu = np.array(self.max_realvar)
        delta1 = (v - vl) / (vu - vl)
        delta2 = (vu - v) / (vu - vl)
        mut_pow = 1.0 / (self.eta_m + 1.0)

        ##rnd2<=0.5
        xy1 = (1.0 - delta1) * barray2
        val1 = 2.0 * rnd2 + (1.0 - 2.0 * rnd2) * xy1 ** (self.eta_m + 1.0)
        deltaq1 = val1**mut_pow - 1.0

        xy2 = (1.0 - delta2) * nbarray2
        val2 = 2.0 * (1.0 - rnd2) + 2.0 * (rnd2 - 0.5) * xy2 ** (self.eta_m + 1.0)
        deltaq2 = 1.0 - val2**mut_pow

        v = v + (deltaq1 * barray2 + deltaq2 * nbarray2) * (vu - vl)
        np.clip(v, vl, vu, v)
        v = v * barray + np.array(ind.value) * np.logical_not(barray)  ### BUGFIX

        ###Manual mutation for domfactor
        ## TODO
        if domfactorexist and targetexist:
            domfv = np.array(ind.value)[domfactorindex]
            tgtv = np.array(ind.rawobj)[targetvalueindex]
            freqdiff = tgtv - self.targetfreq
            if abs(freqdiff) > self.freqthreshold:
                newdomfv = (domfv - self.targetfreq) / 2.5525 + domfv
            v[domfactorindex] = newdomfv

        v = np.clip(v, self.min_realvar, self.max_realvar)  ###boundary check
        ind.value = v

    def tournament(self, ind1: nsgaii_var, ind2: nsgaii_var):
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

    def offspring_gen(self, inpop: List[nsgaii_var]):
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
            if self.freqlockmut:
                self.mutation_real_np_freqlock(child)
            else:
                self.mutation_real_np(child)
        # print("offspring pop",len(offspop))
        return offspop

    def err_norm(self):
        pass

    def random_sampling_LHS_np(self, nsamples):
        ###FAST RANDOM USE NUMPY
        ranlist = np.random.random((nsamples, self.nval))
        jarray = np.mgrid[0:nsamples, 0 : self.nval][0]
        for colomn in jarray.T:
            np.random.shuffle(colomn)
        ranlist = (ranlist + jarray) / nsamples
        return ranlist

    def calc_fnds_size(self, fnds_arr):
        sum = 0
        for list in fnds_arr:
            if list is not None:
                sum += len(list)
        return sum

    def nsgaii_generation_demo(self, model, fnds_callback=None):  ##
        self.param_check()
        ### fnds_callback for mid output

        valarr = self.random_sampling_LHS_np(self.popsize)
        val_width = self.max_realvar - self.min_realvar
        valarr = valarr * val_width + self.min_realvar

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

            if self.constrainted:
                self.constrainted_dominance(poplist)

            fndsresult = self.fnds(poplist)
            # print("FNDS_SIZE",calc_fnds_size(fndsresult),"INPOP:",len(poplist))
            if fnds_callback is not None:
                fnds_callback(igen, fndsresult)
            ###find accept
            acceptedpop.clear()
            pack = self.popsize
            for iset in fndsresult:

                # print("PACK=%d" %pack)
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
                    curfront.sort(
                        key=lambda x: x.crowed_dis, reverse=True
                    )  ###按最大拥挤距离排序
                    n2p = pack
                    # print("LAST FRONT:%d"%n2p)
                    acceptedpop += curfront[0:n2p]
                    pack = 0
                # print("    ACC PROP SIZE:%d"%len(acceptedpop),"TO GO:%d" %pack)
            poplist.clear()
            poplist += acceptedpop
            print("GEN:%d DONE, SIZE:%d" % (igen, len(acceptedpop)))
            ### GEN DONE
        return poplist

    def new_nsgaii_var(self, optvalue):
        newnsga = nsgaii_var(optvalue)
        if self.require_sim_input_transfrom:
            simvalue = self.sim_input_conv_method(optvalue)
            newnsga.setSimValue(simvalue)
        else:
            newnsga.setSimValue(newnsga.value)
        return newnsga

    def nsgaii_generation_parallel(self, fnds_callback=None):  ##
        self.param_check()
        ### fnds_callback for mid output
        if not isinstance(fnds_callback, list):
            fnds_callback = [fnds_callback]

        valarr = self.random_sampling_LHS_np(self.popsize * 2)
        val_width = self.max_realvar - self.min_realvar
        valarr = valarr * val_width + self.min_realvar

        poplist: List[nsgaii_var] = []
        acceptedpop: List[nsgaii_var] = []

        for var in valarr:
            ind = self.new_nsgaii_var(var)
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
        # MINIUM EPK
        # MAXIMUM Shunt Impedence
        #
        ####

        # First Run To Get the Initial Pop
        for ind in poplist:
            JobName = "Init_Pop_" + str(ind.id)
            params = self.createSimParamDictFromNPvar(ind.simvalue)
            self.manager.addTask(params=params, job_name=JobName)
        ###
        self.manager.startProcessing()
        ### WAIT
        ### TIME For Processing And Results
        # if self.constrainted:
        #       ind.constraint_violaton_value=self.constraint_func(ind.constrainted_obj,ind.iobj)
        #     self.constrainted_dominance(poplist)
        ### Get Results
        results = self.manager.getFullResults()
        #### Apply Result To Element
        mapdict = {}
        for index, iresult in enumerate(results):
            targetid = int(iresult["RunName"].split("_")[2])
            mapdict.update({targetid: index})
        processedpoplist = []
        for ind in poplist:
            resultindex = mapdict.get(ind.id)
            if results[resultindex]["TaskStatus"] != "Success":
                ind.done = False
                continue
            objarray, c_objarray, rawarray = self.convertResult(results[resultindex])
            ind.setObjs(objarray)
            ind.setRawObjs(rawarray)
            if self.constrainted:
                ind.setConstrainted_objs(c_objarray)
                ind.constraint_violaton_value = self.constraint_func(
                    ind.constrainted_obj, ind.obj
                )
            ind.done = True
            processedpoplist.append(ind)

        poplist = processedpoplist

        for igen in range(self.generation):
            if igen > 0:
                ### CREATE CHILD POP
                childpoplist = self.offspring_gen(poplist)
                # Run To Get the Children POP
                for ind in childpoplist:
                    JobName = "GEN_%d_" % igen + str(ind.id)
                    params = self.createSimParamDictFromNPvar(ind.simvalue)
                    self.manager.addTask(params=params, job_name=JobName)
                ###
                self.manager.startProcessing()
                ### WAIT
                ### TIME For Processing And Results

                ### Get Results
                results = self.manager.getFullResults()
                #### Apply Results To Element
                mapdict = {}
                for index, iresult in enumerate(results):
                    targetid = int(iresult["RunName"].split("_")[2])
                    mapdict.update({targetid: index})
                processedpoplist = []
                for ind in childpoplist:
                    resultindex = mapdict.get(ind.id)
                    if results[resultindex]["TaskStatus"] != "Success":
                        ind.done = False
                        continue
                    objarray, c_objarray, rawarray = self.convertResult(
                        results[resultindex]
                    )
                    ind.setObjs(objarray)
                    ind.setRawObjs(rawarray)
                    if self.constrainted:
                        ind.setConstrainted_objs(c_objarray)
                        ind.constraint_violaton_value = self.constraint_func(
                            ind.constrainted_obj, ind.obj
                        )
                    ind.done = True
                    processedpoplist.append(ind)
                childpoplist = processedpoplist
                ###DONE
                poplist = poplist + childpoplist

            ### FNDS SORT
            fndsresult = self.fnds(poplist)
            if len(fnds_callback) > 0:
                for ifnds in fnds_callback:
                    ifnds(igen, fndsresult)
            ###find accepted
            acceptedpop.clear()
            pack = self.popsize
            for iset in fndsresult:
                # print("PACK=%d" %pack)
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
                    curfront.sort(
                        key=lambda x: x.crowed_dis, reverse=True
                    )  ###按最大拥挤距离排序
                    n2p = pack
                    # print("LAST FRONT:%d"%n2p)
                    acceptedpop += curfront[0:n2p]
                    pack = 0
                # print("    ACC PROP SIZE:%d"%len(acceptedpop),"TO GO:%d" %pack)
            poplist.clear()
            poplist += acceptedpop

            print("GEN:%d DONE, SIZE:%d" % (igen, len(acceptedpop)))
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

    def getPPSResult(self, runresult):
        ppsr = runresult["PostProcessResult"]
        ar = {}
        for ips in ppsr:
            key = ips["resultName"]
            value = ips["value"]
            ar.update({key: value})
        processedResult = {
            "WorkerID": runresult.get("WorkerID"),
            "TaskIndex": runresult.get("TaskIndex"),
            "TaskStatus": runresult.get("TaskStatus"),
            "RunName": runresult.get("RunName"),
            "RunParameters": runresult.get("RunParameters"),
            "PostProcessResult": ar,
        }
        return processedResult

    def createSimParamDictFromNPvar(self, simvar):
        odict = {}
        for i in range(len(self.input_name)):
            key = self.input_name[i]
            value = simvar[i]
            odict.update({key: value})
        return odict

    def convertResult(self, result):
        pResult = self.getPPSResult(result)
        fp = open(
            self.manager.resultDir / (str(result["RunName"]) + "_Result.json"), "w"
        )
        json.dump(result, fp, indent=4)
        fp.close()
        # DONE
        raw_obj_list = []
        c_iobj_list = []
        for oname in self.output_name:
            raw_obj_list.append(pResult["PostProcessResult"][oname])
        for cname in self.constrainted_object_name:
            c_iobj_list.append(pResult["PostProcessResult"][cname])

        # frequency = 44.4MHz
        # Epk@2MV <7.5MV
        # Shunt-dep >28MOhm
        ###MID CALC
        freq = pResult["PostProcessResult"]["Frequency (Mode 1)"]
        Voltage = pResult["PostProcessResult"]["Voltage beta=1 (Mode 1)"]
        face1_Max_e = pResult["PostProcessResult"]["face1_Max_e"]
        face1_Max_h = pResult["PostProcessResult"]["face1_Max_h"]
        Ra = pResult["PostProcessResult"][
            "Shunt Impedance (Pertubation) beta=1 (Mode 1)"
        ]
        if (Voltage is not None) and (face1_Max_e is not None):
            beta = 2e6 / Voltage
            Epk = beta * face1_Max_e * 1e-6
            Hpk = beta * face1_Max_h * 1e-6
            midinfo = [beta, Epk, Hpk]
            rawarray = np.array(raw_obj_list + midinfo)
            objarray = [freq, Epk, Ra]
            objarray[0] = abs(objarray[0] - self.targetfreq)
            objarray[1] = objarray[1]  # MINIMUM Epk
            objarray[2] = -objarray[2]  # MAXIMUM Shunt-dep
            objarray = np.array(objarray)
            cindarray = np.array(c_iobj_list)
        else:  ##BAD CALCULATION
            print("WARNING:CST MISCALCULATON AT JOB %s" % result["RunName"])
            beta = 0
            Epk = 99999
            Hpk = 99999
            Ra = -99999
            midinfo = [beta, Epk, Hpk]
            rawarray = np.array(raw_obj_list + midinfo)
            objarray = [99999, Epk, Ra]
            cindarray = np.array([99999 + self.targetfreq])

        return objarray, cindarray, rawarray

    def start2(self):

        resultPath = self.manager.resultDir / "TestResult.json"

        # params={"Leq":90,"Req":190}
        params = {}
        result = self.manager.runWithParam(params=params, job_name="test")
        print(result)
        print(self.convertResult(result))
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
        # results=self.manager.getFullResults()

        # fp=open(resultPath,"w")
        # json.dump(results,fp,indent=4)
        # fp.close()

        # print(results)
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
        namelist = self.getFullNameList()

        seed(1037)
        resultDir = self.manager.resultDir
        icallback = fnds_callback_create_Image(savedir=resultDir)
        icallback2 = fnds_callback_dump_individuals(
            savedir=resultDir,
            namelist=namelist,
            require_transform=self.require_sim_input_transfrom,
            constrainted=self.constrainted,
        )
        # self.nval = model.n
        sttime = time.time()

        poplist = self.nsgaii_generation_parallel(fnds_callback=[icallback, icallback2])
        result = self.fnds(poplist)
        endtime = time.time()
        print("elapsed time=", endtime - sttime)

        end_time = time.time()
        print(end_time - start_time)

        return 0


class fnds_callback_dump_individuals:
    def __init__(
        self, savedir="", namelist=[], require_transform=False, constrainted=False
    ) -> None:
        self.setNewSavedir(savedir)
        self.constrainted = constrainted
        self.namelist = namelist
        self.relation = True
        self.require_transform = require_transform

    def setNewSavedir(self, savedir):
        self.savedir = Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)

    def __call__(self, igen, fndslist):

        iprocess = multiprocessing.Process(
            target=dump_individual_worker_func,
            args=(
                self.savedir,
                igen,
                fndslist,
                self.namelist,
                self.require_transform,
                self.constrainted,
            ),
        )
        iprocess.start()
        fp = open(self.savedir / ("GEN_%d_Relations.json" % igen), "w")
        d = {}
        if self.relation:
            for ifnd, fnd in enumerate(fndslist):
                print(ifnd, fnd)
                if fnd is not None:
                    for indv in fnd:
                        u = {
                            indv.id: {
                                "id": indv.id,
                                "rank": indv.rank,
                                "pset": [i.id for i in indv.pset],
                                "value": indv.value.tolist(),
                            }
                        }
                        d.update(u)

        json.dump(d, fp, indent=4)
        fp.close()


def dump_individual_worker_func(
    savedir: Path,
    igen,
    fndslist: List[List[nsgaii_var]],
    namelist,
    require_transform=False,
    constrainted=False,
):
    data_list_all = []
    prefix_name = ["Generation", "Index", "Front Index"]
    columnlist = prefix_name + namelist
    if constrainted:
        columnlist += ["constraint_value"]

    for ifnd, fnd in enumerate(fndslist):
        if fnd is not None:
            for indv in fnd:
                data_row_list = []
                data_row_list += [igen, indv.id, ifnd]
                data_row_list += indv.value.tolist()
                if require_transform:
                    data_row_list += indv.simvalue.tolist()
                data_row_list += indv.rawobj.tolist()
                data_row_list += indv.obj.tolist()
                if constrainted:
                    data_row_list += indv.constrainted_obj.tolist()
                    data_row_list += [indv.constraint_violaton_value]
                data_list_all.append(data_row_list)
    if len(data_row_list) > len(columnlist):

        columnlist += (len(data_row_list) - len(columnlist)) * [""]
    elif len(data_row_list) < len(columnlist):
        columnlist = columnlist[: len(data_row_list)]
    csv = pd.DataFrame(data_list_all, columns=columnlist)
    fp = open(savedir / ("GEN_%d_Individuals.csv" % igen), "w")
    csv.to_csv(fp)
    fp.close()

    return


class fnds_callback_create_Image:
    def __init__(self, savedir="") -> None:
        self.setNewSavedir(savedir)

    def setNewSavedir(self, savedir):
        self.savedir = Path(savedir)
        if not self.savedir.exists():
            self.savedir.mkdir(parents=True)

    def __call__(self, igen, fndslist):
        iprocess = multiprocessing.Process(
            target=image_worker_func, args=(self.savedir, igen, fndslist)
        )
        iprocess.start()
        return


def image_worker_func(savedir, igen, fndslist: List[List[nsgaii_var]]):
    x0 = []
    y0 = []
    x1 = []
    y1 = []
    x2 = []
    y2 = []
    if fndslist[0] is not None:
        for ind in fndslist[0]:
            x0.append(ind.rawobj[0])
            y0.append(ind.obj[1])
        plt.scatter(x0, y0, c="none", marker="o", edgecolors="r")
    if fndslist[1] is not None:
        for ind in fndslist[1]:
            x1.append(ind.rawobj[0])
            y1.append(ind.obj[1])
        plt.scatter(x1, y1, c="none", marker="o", edgecolors="orange")
    if fndslist[2] is not None:
        for ind in fndslist[2]:
            x2.append(ind.rawobj[0])
            y2.append(ind.obj[1])
        plt.scatter(x2, y2, c="none", marker="o", edgecolors="y")

    plt.xlabel("freq")
    plt.ylabel("Epk")
    # plt.axis('scaled')
    plt.savefig(savedir / ("GEN_%05d_Front.png" % igen), bbox_inches="tight")
    return


if __name__ == "__main__":
    pass