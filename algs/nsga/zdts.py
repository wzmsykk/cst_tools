from math import cos,pi,sqrt,sin
from random import random
from abc import ABCMeta, abstractmethod,abstractclassmethod

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
        return invars
    
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
    @abstractclassmethod
    def best_solution_check(cls,var):        
        return True

class zdt1(commonfunc):
    def __init__(self,nofdvs=30) -> None:
        super().__init__(nofdvs)
        self.name='zdt1'
    def create_var_boundary(self):
        max_var=[None for _ in range(self.n)]
        min_var=[None for _ in range(self.n)]
        for i in range(0,self.n):
            min_var[i]=0
            max_var[i]=1
        return min_var,max_var
    def __call__(self,invars):
        ####f1=fx, f2=g(x)h(x)        
            
        try:
            fx=invars[0]
            gx=1
            for i in range(1,self.n):
                xi=invars[i]
                gx+=9/(self.n-1)*xi
            hx=(1-sqrt(fx/gx))
        except ValueError:
            print("ValueError",invars)
        else:
            return fx,hx*gx
    def check_boundary(self,invars):
        flag=True
        x1=invars[0]
        if not 0<=x1<=1: flag=False
        for i in range(1,self.n):
            xi=invars[i]
            if not 0<=xi<=1:flag=False
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
        if var[0]>1 or var[0]<0:
            return False
        for i in range(1,10):
            if abs(var[i])>cls.tolerance:
                return False
        return True

class zdt2(commonfunc):
    def __init__(self,nofdvs=30) -> None:
        super().__init__(nofdvs)
        self.name='zdt2'
    def __call__(self,invars):
        ####f1=fx, f2=g(x)h(x)
        fx=invars[0]
        gx=1
        for i in range(1,self.n):
            xi=invars[i]
            gx+=9/(self.n-1)*xi
        hx=(1-(fx/gx)**2)
        return fx,hx*gx
    def create_var_boundary(self):
        max_var=[None for _ in range(self.n)]
        min_var=[None for _ in range(self.n)]
        for i in range(0,self.n):
            min_var[i]=0
            max_var[i]=1
        return min_var,max_var
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
        if var[0]>1 or var[0]<0:
            return False
        for i in range(1,10):
            if abs(var[i])>cls.tolerance:
                return False
        return True

class zdt3(commonfunc):
    def __init__(self,nofdvs=30) -> None:
        super().__init__(nofdvs)
        self.name='zdt3'
    def __call__(self,invars):
        ####f1=fx, f2=g(x)h(x)
        fx=invars[0]
        gx=1
        for i in range(1,self.n):
            xi=invars[i]
            gx+=9/(self.n-1)*xi
        hx=(1-sqrt(fx/gx)-(fx/gx)*sin(10*pi*fx))
        return fx,hx*gx
    def create_var_boundary(self):
        max_var=[None for _ in range(self.n)]
        min_var=[None for _ in range(self.n)]
        for i in range(0,self.n):
            min_var[i]=0
            max_var[i]=1
        return min_var,max_var
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
        if 0.0830<var[0]<0.1822:
            return False
        elif 0.2577<var[0]<0.4093:
            return False
        elif 0.4538<var[0]<0.6183:
            return False
        elif 0.6585<var[0]<0.8233:
            return False
        elif 0.8518<var[0]<=1:
            return False
        for i in range(1,10):
            if abs(var[i])>cls.tolerance:
                return False
        return True
class zdt4(commonfunc):
    def __init__(self,nofdvs=10) -> None:
        super().__init__(nofdvs)
        self.name='zdt4'
    def __call__(self,invars):
        ####f1=fx, f2=g(x)h(x)
        fx=invars[0]
        gx=1+10*(self.n-1)
        for i in range(1,self.n):
            xi=invars[i]
            gx+=xi**2-10*cos(4*pi*xi)
        hx=(1-sqrt(fx/gx))
        return fx,hx*gx
    def create_var_boundary(self):
        max_var=[None for _ in range(self.n)]
        min_var=[None for _ in range(self.n)]
        min_var[0]=0
        max_var[0]=1
        for i in range(1,self.n):
            min_var[i]=-10
            max_var[i]=10
        return min_var,max_var
    
    def test_var(self):
        invars=[]
        x1=random()
        invars.append(x1)
        for i in range(1,self.n):
            xi=20*random()-10
            invars.append(xi)
        return invars
    @classmethod
    def best_solution_check(cls,var):
        if var[0]>1 or var[0]<0:
            return False
        for i in range(1,10):
            if abs(var[i])>cls.tolerance:
                return False
        return True

