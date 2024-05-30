from math import cos,pi,sqrt,sin
from random import random
from abc import ABCMeta, abstractmethod,abstractclassmethod
import threading
class commonfunc():
    __metaclass__=ABCMeta
    tolerance=1e-8
    def __init__(self,nofdvs) -> None:
        self.n=nofdvs
        self.name="dummyfunc"
        self.min_var,self.max_var=self.create_var_boundary()
        self.__check_boundary_validity()
    def __check_boundary_validity(self):
        for min,max in zip(self.min_var,self.max_var):
            if min>max:
                print("boundary invalid")
                raise ValueError
    def getBoundaries(self):
        return self.min_var,self.max_var
    
    def create_var_boundary(self):
        max_var=[None for _ in range(self.n)]
        min_var=[None for _ in range(self.n)]        
        for i in range(0,self.n):
            min_var[i]=0
            max_var[i]=1
        return min_var,max_var
        
    @abstractmethod
    def __call__(self,invars):
        print(invars)
        objs=invars
        return objs
    
    def result_with_constraint(self,invars):
        print(invars)
        objs=invars
        c_objs=invars
        return objs,c_objs
    def check_boundary(self,invars):
        for index,var in enumerate(invars):
            if var>self.max_var[index] or var<self.min_var[index]:
                return False        
        return True
    @abstractmethod
    def test_var(self):
        invars=[]
        for _ in range(0,self.n):
            invars.append(0)
        return invars
    @classmethod
    def best_solution_check(cls,var):        
        return True

class tm020cav(commonfunc):
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
class tm020cav_parallel(commonfunc):
    def __init__(self,nofdvs=2) -> None:
        super().__init__(nofdvs)
        self.name='TM020 cav'
        self.log_results=True
        # input 2-dims 
        # Req 180-200mm
        # Leq 60-120mm
        
        # output 4-dims
        # freq 1500Mhz
        # R over Q
        # Q
        # Shunt-dep
        self.compute_done=False
        self.in_value_list=None
        self.computed_value_list=None
        self.compute_function=None
        self.listening_thread=None
    def sendValueList(self,valuelist):
        self.in_value_list=valuelist
    def startListening(self):
        self.compute_done=False
        self.listening_thread=threading.Thread(target=tm020cav_parallel.callCompute,args=(self.in_value_list))
        self.listening_thread.join()
        self.compute_done=True
    def callCompute(self):
        self.computed_value_list=self.compute_function(self.in_value_list)
        return self.computed_value_list
    def getComputeResult(self):
        if self.compute_done==False:            
            return None
        else:
            return self.computed_value_list
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