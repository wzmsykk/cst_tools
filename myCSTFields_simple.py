import os
import sys
import shutil
import re
import result
import logger
import numpy as np
import cstmanager
import yfunction
import projectutil

class myCuts(object):
    def __init__(self, manager, params, log_obj):
        super().__init__()
        self.w = manager
        self.results=result.result
        self.log=log_obj
        self.runcount=0
        self.params=params
    def do(self):
        print(self.params)
        for i in range(5):
            xi=projectutil.convert_json_params_to_list(self.params)
            if (not self.params[i]["description"].find("常数")>=0):
                xi[i]+=1
            self.log.logger.info("changed paramname %s, paramvalue %s"% (self.params[i]['name'],self.params[i]['value']))
            
            self.w.addTask(xi,"dx"+str(i))  
        self.w.start()
        self.w.synchronize()
        rg=self.w.getFullResults()
        ###SORT RESULTS
        rg=sorted(rg,key=lambda x: x['name'])
        #############
        print(rg)
    def start(self):
        self.do()

##V2 rewrite for parallel
class MyCuts_Pillbox(object):
    def __init__(self, manager, params):
        super().__init__()
        self.input_dict = params
        self.struct_params_namelist = ['R', 'L', 'nmodes']
        print(params)
        self.struct_params_valuelist = [230,260,10]
        assert isinstance(manager, cstmanager.manager)
        self.manager = manager
        #assert isinstance(manager.logger, logging.logger)
        self.logger=manager.logger
        

        ###OTHERS
        self.results=result.result
        self.runcount=0

        ##########INITIALIZED############



    def do(self):
        ###Y=Y(R(X))####
        r=230
        nmodes=4
        for l in range(260,261):
            r0=self.manager.runWithParam(name_list=self.struct_params_namelist,value_list=[r,l,nmodes],job_name="R_%f_L_%f" % (r,l))

        self.logger.info("RUN:%d" %(self.runcount))
        return self.runcount


    def start(self):
        self.do()


