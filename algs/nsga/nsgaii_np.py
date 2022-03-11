from math import inf, sqrt, floor
from random import random, seed, shuffle, choices,sample
from unittest import result

from sympy import I
from .zdts import zdt1, zdt2, zdt3, zdt4
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
        self.result = None
        self.pset: Set[
            nsgaii_var
        ] = set()  ### set of var domed by p ### By Ref so it might be memory safe
        self.done = False
        self.sorted = False
        self.n = 0
        self.crowed_dis = 0
        self.crowed_dis_calc_done = False
        
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
        dup.result=self.result.copy()        
        return dup
    def setResult(self, result):
        self.result = np.array(result)

    def dom(self, other):
        tarray = np.less(self.result,other.result)
        earray = np.less_equal(self.result,other.result)
        if np.all(earray) and np.any(tarray):
            return True  ### A N Domi B
        else:
            return False

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
    def fnds(self,vallist: List[nsgaii_var]):  ## Fast non dominated sort

        flist: List[List[nsgaii_var]] = [None for _ in range(len(vallist))]
        flist[0] = list()
        #### Get All Dom Relations
        for p in vallist:
            for q in vallist:
                if p.id == q.id:
                    continue
                if p.dom(q):
                    p.pset.add(q)  ### I DOM YOU
                elif q.dom(p):
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
    ):  # sort vars by the distance of results

        if len(flist) == 0:
            return
        elif len(flist) <= 2:
            for var in flist:
                var.crowed_dis = inf
                var.crowed_dis_calc_done = True
            return
        for i in range(self.nobj):
            ilist = sorted(flist, key=lambda x: x.result[i])
            ilist[0].crowed_dis = inf
            ilist[0].crowed_dis_calc_done = True
            ilist[-1].crowed_dis = inf
            ilist[-1].crowed_dis_calc_done = True
            coff = ilist[-1].result[i] - ilist[0].result[i]
            for u in range(len(ilist)):
                if not ilist[u].crowed_dis_calc_done:
                    if ilist[u + 1].result[i] == ilist[u - 1].result[i]:
                        ilist[u].crowed_dis += 0
                    else:
                        ilist[u].crowed_dis += (
                            ilist[u + 1].result[i] - ilist[u - 1].result[i]
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
                ind.setResult(list(imodel(ind.value)))
            
            childpoplist = self.offspring_gen(poplist)
            
            for ind in childpoplist:
                ind.setResult(list(imodel(ind.value)))
            ###DONE
            poplist = poplist + childpoplist
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

    def nsgaii_generation_parallel(self,model_parallel,fnds_callback=None):  ##
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
        resultlist=imodel(valuelist)            ###WORK To get Results
        for i in range(len(poplist)):        
            poplist[i].setResult(resultlist[i])

        for igen in range(self.generation):           

            childpoplist = self.offspring_gen(poplist)            
            childvaluelist=[ind.value for ind in childpoplist]
            childresultlist=imodel(childvaluelist)
            for i in range(len(childpoplist)):        
                childpoplist[i].setResult(childresultlist[i])

            ###DONE
            poplist = poplist + childpoplist

            if len(poplist)<self.popsize: ###check for unfinished calcs and dup random results
                self.logger.warning("Too Few Pop Results Calculated at gen:%d."%igen)
                cnt2dup=self.popsize-len(poplist)
                sampled=sample(poplist,cnt2dup)
                duplist=[src.dup() for src in sampled]
                poplist+=duplist


            fndsresult = self.fnds(poplist)
            #print("FNDS_SIZE",calc_fnds_size(fndsresult),"INPOP:",len(poplist))
            if fnds_callback is not None:
                fnds_callback(igen, fndsresult)
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

        pass


def fnds_test():
    mynsgaii=nsgaii()
    seed(666)
    imodel = zdt1(30)
    totalnums = 123
    vallist = []
    for i in range(totalnums):
        nvar = nsgaii_var(imodel.test_var())
        nvar.setResult(list(imodel(nvar.value)))
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
    seed(666)
    mynsgaii=nsgaii()
    mynsgaii.nobj = 2
    mynsgaii.pmut_real = 0.1
    mynsgaii.eta_m = 1  ## coff for mutation
    mynsgaii.popsize = 2
    mynsgaii.generation = 100
    # min_realvar=[0,-10,-10,-10,-10,-10,-10,-10,-10,-10,-10]
    # max_realvar=[1,+10,+10,+10,+10,+10,+10,+10,+10,+10,+10]
    models = [zdt1(), zdt2(), zdt3(), zdt4()]
    icallback = nsgaii_helper.fnds_callback_create_Image()
    for model in models:
        
        nval = model.n
        min_realvar_raw, max_realvar_raw = model.getBoundaries()
        min_realvar, max_realvar =np.array(min_realvar_raw),np.array(max_realvar_raw)
        print(min_realvar)
        sttime = time.time()
        icallback.setNewSavedir(model.name)
        poplist = mynsgaii.nsgaii_generation_demo(model, fnds_callback=icallback)
        result = mynsgaii.fnds(poplist)
        endtime = time.time()
        print("elapsed time=", endtime - sttime)

        fp = open(icallback.savedir / "result.txt", "w")
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


if __name__ == "__main__":
    nsgaii_test()
    #fnds_test()

