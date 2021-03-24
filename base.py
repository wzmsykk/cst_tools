import os
import sys
import shutil 
import result
import copy
import json
import numpy as np
import worker,cstmanager
import projectutil
import adam,myAlgorithm_pop,myAlgorithm
import globalconfmanager,logger,time
import projectconfmanager
import argparse

params=sys.argv
###设定命令行参数PARSER
parser = argparse.ArgumentParser(description='python cst project.')
parser.add_argument("-p", "--projectdir",
                  action="store", dest="projectdir", help="project目录")

parser.add_argument("-r", "--runonly", action="store_true", dest="runonly", help="仅运行已生成的项目")
parser.add_argument("-g", "--genonly", action="store_true", dest="genonly", help="仅从cst文件生成项目")
args=parser.parse_args()
batchprojectdir=args.projectdir
runonly=args.runonly
genonly=args.genonly


#batchprojectdir=r".\project\POP"
###读取全局配置
###生成LOG文件
uuid_str = time.strftime("%Y-%m-%d-%H_%M_%S",time.localtime()) 
os.makedirs(r".\log",exist_ok=True)
glogfilepath =r'log\base_%s.log' % uuid_str
glogger=logger.Logger(glogfilepath,level='debug')
gconfman=globalconfmanager.GlobalConfmanager(Logger=glogger)


if runonly==True and genonly ==True:
    glogger.logger.error("输入参数冲突")
###验证全局配置是否有效
gconfman.checkConfig()

if (batchprojectdir!=None):
    glogger.logger.info("使用命令行定义的project目录:%s" % batchprojectdir)
    gconfman.conf['PROJECT']['currprojdir']=batchprojectdir
else:
    glogger.logger.error("未指定project目录")
    os._exit(1)


###检查并取得当前project
gconfman.checkCurrProject()
gconfman.saveconf()

###使用找到的project
currprojdir=gconfman.conf['PROJECT']['currprojdir']
glogger.logger.info("开始使用project目录:%s" % currprojdir)

###读取项目配置
pconfman=projectconfmanager.ProjectConfmanager(GlobalConfigManager=gconfman,Logger=glogger)
if runonly==False:    
    pconfman.openProjectDir(currprojdir)
elif runonly==True:
    pconfman.openProjectDirReadOnly(currprojdir)

###读取完毕，显示当前设置
gconfman.printconf()
pconfman.printconf()


if genonly==False:

    params=pconfman.getParamsList()
    method="GD_PARALLEL_LOCAL"
    #if method=="GD":
    #    worker=worker.worker(type='loacl',config=cstconf)
    #    x0 = gen_x_list(rlst[0])
    #    gw=adam.adam(worker,x0) 
    #    gw.start()
    #    worker.stop()


    if method=="GD_PARALLEL_LOCAL":
        x0 = projectutil.convert_json_params_to_list(params)
        mym=cstmanager.manager(params=params,pconfm=pconfman,gconfm=gconfman,log_obj=glogger,maxTask=2)
        import myCSTFields_simple
        gw=myCSTFields_simple.MyCuts_Pillbox(manager=mym,params=params) 
        #gw=myAlgorithm_pop.myAlg01(manager=mym,params=params) 
        #gw=myAlgorithm.myAlg01_pillbox(manager=mym,x0=x0) 
        gw.start()
        mym.stop()
