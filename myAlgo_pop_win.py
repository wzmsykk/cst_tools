from logger import Logger
from myAlgorithm_pop import myAlg01

class myAlg01_win_wrapper():
    
    def __init__(self,Logger=None):
        self.input_name = ['Nmodes','fmin','fmax','accuracy','cell']
        self.input_min = [1,700,800,1e-5,20]
        self.continue_flag = [0, 3738.9532]
        self.manager=None
        self.otherparamsdict=None
        self.alg=None
        self.logger=Logger
    def changeCalcParams(self,paramdict):
        print(paramdict)
        for k,v in paramdict.items():
            setattr(self,k,v)

        # EXPECT continue_flag
        # EXPECT self.input_min = [1,700,800,1e-5,20]
    def assignCSTWorkManager(self,manager):
        self.manager=manager
    def assignCSTVariable(self,paramsdict):
        self.otherparamsdict=paramsdict
    def getAttrsDict(self):
        attr_name_list=['continue_flag','input_min','input_name']
        dic={}
        for name in attr_name_list:            
            dic[name]=getattr(self,name)
        return dic
    
    def start(self):
        if self.manager and self.otherparamsdict:
            self.alg=myAlg01(manager=self.manager,params=self.otherparamsdict)
            self.alg.start()
        else:
            self.logger.error("未指定manager与paramslict")