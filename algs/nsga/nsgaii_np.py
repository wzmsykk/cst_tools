from math import inf, sqrt, floor
from random import random, seed, shuffle, choices,sample
from time import sleep
from pathlib import Path
from zdts import zdt1, zdt2, zdt3, zdt4
from typing import List, Set
import json
import numpy as np
import logging
import threading

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



def sample_constraint_func(obj,constraint_obj):
    ###constraint: constraint_obj[0]==500 
    cv=0
    for index in range(len(obj)):
        iobj=obj[index]
        if iobj>0:
            cv+=iobj
    cv+=abs(constraint_obj[0]-500)

class nsgaii():
    def __init__(self,logger=None):
        if logger==None:
            self.logger=logging.getLogger("nsgaii")
        self.nobj = 2
        self.nval = 10
        self.pmut_real = 0.1
        self.eta_m = 1  ## coff for mutation
        self.popsize = 200
        self.generation = 100

        self.min_realvar = []
        self.max_realvar = []
        
        self.constrained=False
        self.constraint_func=None
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

            q_set = set()
            for p in flist[i]:

                for q in p.pset:
                    q.n -= 1  ### 除p外q仍被支配的个数
                    if q.n == 0:  ### not domed By Anyone Except P
                        q.rank = i + 1
                        q_set.add(q)

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
        for var in flist:
            var.crowed_dis_calc_done = False
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
        for var in flist:
            var.crowed_dis_calc_done = True

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
        v = v * barray + np.array(ind.value) * np.logical_not(barray)  ### BUGFIX
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
        if not isinstance(fnds_callback, list):
            fnds_callback = [fnds_callback]
        valarr = self.random_sampling_LHS_np(self.popsize)
        val_width=self.max_realvar-self.min_realvar
        valarr=valarr*val_width+self.min_realvar


        poplist = []
        acceptedpop = []

        for var in valarr:
            ind = nsgaii_var(var)
            poplist.append(ind)
        imodel = model
        
        ###WORK To get Obj
        for ind in poplist:
            ind.setObjs(list(imodel(ind.value)))
        
        for igen in range(self.generation):
            if igen>0:            
                childpoplist = self.offspring_gen(poplist)
                for ind in childpoplist:
                    ind.setObjs(list(imodel(ind.value)))
                ###DONE
                poplist = poplist + childpoplist
                if self.constrained:
                    self.constrained_dominance(poplist)

            fndsresult = self.fnds(poplist)
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
                    curfront = list(iset)
                    self.crowding_dis_assign(curfront)
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
            if len(fnds_callback) > 0:
                for ifnds in fnds_callback:
                    ifnds(self, igen, fndsresult)
                    
            poplist.clear()
            poplist += acceptedpop
            print("GEN:%d DONE, SIZE:%d" % (igen,len(acceptedpop)))
            ### GEN DONE
        return poplist

    def nsgaii_generation_parallel(self,model_parallel,fnds_callback=None):  ##
        
        if not isinstance(fnds_callback, list):
            fnds_callback = [fnds_callback]
        self.param_check()
        ### fnds_callback for mid output

        valarr = self.random_sampling_LHS_np(self.popsize)
        val_width=self.max_realvar-self.min_realvar
        valarr=valarr*val_width+self.min_realvar


        poplist:List[nsgaii_var] = []
        acceptedpop:List[nsgaii_var] = []

        for var in valarr:
            ind = nsgaii_var(var)
            poplist.append(ind)
        imodel = model_parallel ####supports job submitting

        valuelist=[ind.value for ind in poplist] ####First Run To Get the Initial Pop
        
        
        # if self.constrained: ###WORK To get Initial Objs
        #     objlist,c_objlist=imodel(valuelist)
        #     for i in range(len(poplist)):        
        #         poplist[i].setObjs(objlist[i])
        #         poplist[i].setConstraint_objs(c_objlist[i])
        # else:
            ####Wait For Model To Get Results
        
        imodel.sendValueList(valuelist)
        imodel.startCompute()
        while (not imodel.compute_done):
            sleep(1)
        objlist=imodel.getComputeResult()
        for i in range(len(poplist)):        
            poplist[i].setObjs(objlist[i])


        for igen in range(self.generation):           

            childpoplist = self.offspring_gen(poplist)            
            childvaluelist=[ind.value for ind in childpoplist]


            if self.constrained: ###WORK To get ChildPop Objs
                objlist,c_objlist=imodel(childvaluelist)
                for i in range(len(childpoplist)):        
                    childpoplist[i].setObjs(objlist[i])
                    childpoplist[i].setConstraint_objs(c_objlist[i])
            else:
                objlist=imodel(valuelist)            
                for i in range(len(childpoplist)):        
                    childpoplist[i].setObjs(objlist[i])


            ###DONE
            poplist = poplist + childpoplist

            if len(poplist)<self.popsize: ###check for unfinished calcs and dup random results
                self.logger.warning("Too Few Pop Results Calculated at gen:%d."%igen)
                cnt2dup=self.popsize-len(poplist)
                sampled=sample(poplist,cnt2dup)
                duplist=[src.dup() for src in sampled]
                poplist+=duplist


            fndsresult = self.fnds(poplist)
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
                    curfront = list(iset)
                    self.crowding_dis_assign(curfront) ###EXTRA INFOMATIONS
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
                
            if len(fnds_callback) > 0:
                for ifnds in fnds_callback:
                    ifnds(self, igen, fndsresult)
                    
            poplist.clear()
            poplist += acceptedpop
            print("GEN:%d DONE, SIZE:%d" % (igen,len(acceptedpop)))
            ### GEN DONE
        return poplist

        pass


def fnds_test():
    mynsgaii=nsgaii()
    seed(666)
    imodel = zdt1(30)
    totalnums = 123
    vallist = []
    for i in range(totalnums):
        nvar = nsgaii_var(imodel.test_var())
        nvar.setObjs(list(imodel(nvar.value)))
        vallist.append(nvar)

    # print("TOTAL PTS:", len(set(vallist)))
    flist = mynsgaii.fnds(vallist)
    print(mynsgaii.calc_fnds_size(flist))
    # print(flist)
    # for i in range(1,len(flist)):
    #     iset=flist[i]
    #     # if not iset:
    #     #     break
    #     print(iset)


def nsgaii_test():
    import time
    import nsgaii_helper

    # global nval
    # global min_realvar
    # global max_realvar
    # global popsize
    # global generation
    # global eta_m
    seed(1037)
    mynsgaii=nsgaii()
    mynsgaii.nobj = 2
    mynsgaii.pmut_real = 0.1
    mynsgaii.eta_m = 15  ## coff for mutation
    mynsgaii.popsize = 200
    mynsgaii.generation = 300
    #min_realvar=[0,-10,-10,-10,-10,-10,-10,-10,-10,-10,-10]
    #max_realvar=[1,+10,+10,+10,+10,+10,+10,+10,+10,+10,+10]
    models = [zdt1(), zdt2(), zdt3(), zdt4()]
    icallback1 = nsgaii_helper.fnds_callback_create_Image()
    icallback2 = nsgaii_helper.fnds_callback_dump_fnds()
    icallbacks=[icallback1,icallback2]
    for model in models:
        mynsgaii.nval = model.n
        min_realvar_raw, max_realvar_raw = model.getBoundaries()
        mynsgaii.min_realvar, mynsgaii.max_realvar =np.array(min_realvar_raw),np.array(max_realvar_raw)
        print(mynsgaii.min_realvar)
        print(mynsgaii.max_realvar)
        sttime = time.time()
        savedir=Path(model.name)
        for icallback in icallbacks:
            icallback.setNewSavedir(savedir)
        poplist = mynsgaii.nsgaii_generation_demo(model, fnds_callback=icallbacks)
        result = mynsgaii.fnds(poplist)
        endtime = time.time()
        print("elapsed time=", endtime - sttime)

        fp = open(savedir / "result.txt", "w")
        ###STATS
        front = result[0]
        fsize = len(front)
        accept = 0
        print("Front Size:%d" % fsize, file=fp)
        for ind in front:
            if model.best_solution_check(ind.value):
                accept += 1
            print("Id:%d Value:" % ind.id, ind.value, file=fp)
        print("Result accept rate:%f" % (accept / fsize), file=fp)
        fp.close()
        nsgaii_helper.crowd_distance_stats_from_dump(savedir)


if __name__ == "__main__":
    nsgaii_test()
    #fnds_test()

