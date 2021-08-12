import configparser
import os,shutil,re,json
import logger
import subprocess
import hashlib
import tempfile
import projectutil
import pathlib
###读取或生成ProjConf.ini文件

class ProjectStatusError(Exception):
    def __init__(self,message):
        self.meg=message
class ProjectConfmanager(object):
    def __init__(self,GlobalConfigManager=None,Logger=None):
        self.conf= configparser.ConfigParser()
        self.logger=Logger
        self.gconf=GlobalConfigManager.conf
        self.currProjectDir=None 
        self.CFGfilename="project.ini"
        self.paramsfilename='params.json'
    def isCFGfileexist(self):
        if self.currProjectDir!=None:
            if (self.currProjectDir / self.CFGfilename).exists():
                return True
        return False
    def _rap2apo(self,inpath): #relative or abs path to abspath object related to project dir as base dir
        if self.currProjectDir == None:
            raise AttributeError
        op=pathlib.Path(inpath)
        if not op.is_absolute():
            op = self.currProjectDir / op
        return op
    def openProjectDirReadOnly(self,projectDir):
        self.currProjectDir=pathlib.Path(projectDir).absolute()
        self.logger.info("尝试打开project目录%s。"% str(self.currProjectDir))
        cfgfilename=self.CFGfilename
        cfgpath=self.currProjectDir / cfgfilename
        if(not cfgpath.exists()):
            self.logger.error("未找到配置文件%s。"% cfgfilename)
            raise FileNotFoundError

        result=self.checkProjectStatus()
        if result==False:
            raise ProjectStatusError


    def openProjectDir(self,projectDir):
        self.currProjectDir=pathlib.Path(projectDir).absolute()
        self.logger.info("尝试打开project目录%s。"% str(self.currProjectDir))
        cfgfilename=self.CFGfilename
        cfgpath=self.currProjectDir/ cfgfilename
        if(not cfgpath.exists()):
            self.logger.info("未找到配置文件%s。"% cfgfilename)
            self.createProjectFromDir(self.currProjectDir)

        result=self.checkAndRepairProject()
        if result==False:
            raise ProjectStatusError

    def createProjectFromDir(self,newProjectDir=None,slient=False):
        self.logger.info("尝试从project目录%s创建配置文件。"% str(newProjectDir))
        if newProjectDir!=None:
            self.currProjectDir=pathlib.Path(newProjectDir).absolute()
        cfgfilename=self.CFGfilename
        self.createProjectConf(cfgfilename=cfgfilename)
        #self.checkProjectStatus()

    def savecfg(self,cfgfilename="project.ini",slient=False):
        cfgfilePath=self.currProjectDir / "project.ini"
        f=open(cfgfilePath,"w")
        self.conf.write(f)
        f.close()

    def createProjectConf(self,cfgfilename="project.ini",projectname=None):
        #所有路径都是相对于.\project\myproject这一文件夹 
        cfgfilepath=pathlib.Path(self.currProjectDir)/ cfgfilename
        self.logger.info("开始创建配置文件%s于%s。"% (cfgfilename,str(cfgfilepath)))
        self.conf.clear()
        cstfile=None
        currprojdir=pathlib.Path(self.currProjectDir)        
        avilprojname=currprojdir.name

        currprojname=None
        if(projectname!=None):
            self.logger.info("使用指定的project名%s" % projectname)
            currprojname=projectname

        else:
            self.logger.info("未指定project名,使用为默认目录名%s" % avilprojname)
            currprojname=avilprojname

        cstfilelist=list(currprojdir.glob("*.cst"))
        if (len(cstfilelist)==0):
            self.logger.error("未找到CST项目文件于%s目录"%str(currprojdir))
            raise FileNotFoundError
        else:
            file=cstfilelist[0]
            self.logger.info("找到CST项目文件%s"% file)
            cstfile=file
        self.conf.add_section("PROJECT")
        self.conf.set('PROJECT','ProjectName',currprojname)
        self.conf.set('PROJECT','ProjectType',currprojname)
        self.conf.set('PROJECT','ProjectDescription',"")
        self.conf.add_section("DIRS")   
        #保存为相对路径

        #############TO DO #####################


        self.conf.set('DIRS','resultdir','result')
        self.conf.set('DIRS','tempdir','temp')
        self.conf.add_section("CST")      
        self.conf.set('CST','CSTFilename',str(cstfile.name))  

        file_md5=self.genMD5FromCST(cstfile)
        self.conf.set('CST','CSTFileMD5',file_md5.hexdigest())

        self.conf.set('CST','UseMpi',"False")  
        self.conf.set('CST','MpiNodeList',"")  
        self.conf.set('CST','UseRemoteCalculaton',"False")  
        self.conf.set('CST','DCMainControlAddress',"")  
        self.conf.add_section("PARAMETERS")
        self.conf.set('PARAMETERS','paramfile',self.paramsfilename)  
        self.readParametersFromCST()

        #保存配置文件
        self.savecfg()
        self.logger.info("创建配置文件结束。")

    def printconf(self):
        self.logger.info("项目信息:")
        self.logger.info("ProjectName:%s"% self.conf['PROJECT']['ProjectName'])
        self.logger.info("ProjectType:%s"% self.conf['PROJECT']['ProjectType'])
        self.logger.info("ProjectDescription:%s"% self.conf['PROJECT']['ProjectDescription'])
        self.logger.info("项目result目录:%s"% self.conf['DIRS']['resultdir'])
        self.logger.info("项目temp目录:%s"% self.conf['DIRS']['tempdir'])
        self.logger.info("CST文件名:%s"% self.conf['CST']['CSTFilename'])
        self.logger.info("CSTFileMD5:%s"% self.conf['CST']['CSTFileMD5'])
        self.logger.info("使用MPI:%s"% self.conf['CST']['UseMpi'])
        self.logger.info("MPI节点文件:%s"% self.conf['CST']['MpiNodeList'])
        self.logger.info("UseRemoteCalculaton:%s"% self.conf['CST']['UseRemoteCalculaton'])
        self.logger.info("DCMainControlAddress:%s"% self.conf['CST']['DCMainControlAddress'])
        self.logger.info("参数列表文件:%s"% self.conf['PARAMETERS']['paramfile'])
        self.printparams()

    def printparams(self):
        paramfile=self.currProjectDir / self.conf['PARAMETERS']['paramfile']
        f=open(paramfile,"r")
        pamlist=json.load(f)
        print(pamlist)
        f.close()

    def getParamsList(self, jsonpath=None):
        """从生成的json读取Model结构参数列表 read model parameters from json filepath
            
        Parameters
        ----------
        jsonpath : string

        Returns
        -------
        pamlist : a list of json dict contains the param names and values

        """
        if (jsonpath==None):
            paramfile=self.currProjectDir / self.conf['PARAMETERS']['paramfile']
        else:
            paramfile=jsonpath
        f=open(paramfile,"r")
        pamlist=json.load(f)
        f.close()
        return pamlist


    def genMD5FromCST(self,cstfilepath):
        #生成MD5
        fp=open(cstfilepath,"rb")
        dat=fp.read()
        file_md5 = hashlib.md5(dat)
        fp.close()
        return file_md5
        

    def readParametersFromCST(self,savejsonpath=None):    
        if savejsonpath==None:
            jsonpath=self.currProjectDir / self.paramsfilename 
        else:
            jsonpath=pathlib.Path(savejsonpath)
            if not jsonpath.is_absolute():
                jsonpath = self.currProjectDir / jsonpath
        self.logger.info("正在从CST文件中读取参数列表。")    
        projectname=self.conf['PROJECT']['ProjectName']
        td=pathlib.Path(self.conf['DIRS']['tempdir'])
        
        if td.is_absolute():
            td=self.conf['DIRS']['tempdir']
        else:
            td=self.currProjectDir / td
        if not td.exists():
            td.mkdir()
        tempfile.tempdir=str(td)
        self.logger.info("tempdir为%s。" %tempfile.gettempdir())  
        tmp_bas=tempfile.NamedTemporaryFile(mode="w",suffix='.bas',delete =False)
        tmp_txt=tempfile.NamedTemporaryFile(mode="w",suffix='.txt',delete =False)
        tmp_cst=tempfile.NamedTemporaryFile(mode="wb",suffix='.cst',delete =False)
        tmp_bas_name = tmp_bas.name
        tmp_cst_name = tmp_cst.name
        tmp_txt_name = tmp_txt.name
        self.logger.info("临时文件生成成功。")
        vbasrcpath=pathlib.Path(self.gconf['BASE']['datadir']).absolute() / "readParamsT.vb"
        vbadstpath=pathlib.Path(tempfile.gettempdir()) / tmp_bas_name
        midfilepath=pathlib.Path(tempfile.gettempdir()) / tmp_txt_name
        
        
        cstfilepath=pathlib.Path(self.currProjectDir).absolute() / self.conf['CST']['CSTFilename']
        tmpcstpath=pathlib.Path(tempfile.gettempdir()).absolute() / tmp_cst_name
        #tmpcstfile
        fcst=open(cstfilepath,"rb")
        content=fcst.read()
        tmp_cst.file.write(content)
        
        tmp_cst.file.close()
        
        
        file_1=open(vbasrcpath,"r")
        file_2=tmp_bas.file
        list1=[]
        for line in file_1.readlines():
            ssd=line
            ssd=re.sub('%PARAMDSTPATH%',str(midfilepath).replace('\\','\\\\'),ssd)
            ssd=re.sub('%CSTPROJFILE%',str(tmpcstpath).replace('\\','\\\\'),ssd)
            list1.append(ssd)
        file_1.close()
        for i in range(len(list1)):
            file_2.write(list1[i])
        file_2.close()

        #command=

        command = "\""+self.gconf['CST']['cstexepath'] + "\"" +" -m " + "\"" + str(vbadstpath) + "\""
        with subprocess.Popen(command, stdout=subprocess.PIPE,shell=True) as self.cstProcess:
            for line in self.cstProcess.stdout:
                self.logger.info(line)
        
        projectutil.custom_ascii_2_json(midfilepath,jsonpath)
        pass

    def checkAndRepairProject(self,cfgfilename="project.ini",slient=False,force=True):
        result=True
        cfgpath=self.currProjectDir / cfgfilename
        cstfileflag=False
        cfgfileflag=False
        self.logger.info("检测并更新项目配置文件")
        self.logger.info("测试项目配置文件是否存在")
        self.logger.debug("推测项目配置文件位于%s",str(cfgpath))
        if(cfgpath.exists()):
            self.logger.info("测试项目配置文件存在 通过")
            cfgfileflag=True
        else:
            self.logger.error("未找到配置文件%s\n"% str(cfgpath))
            self.logger.info("测试项目配置文件存在 失败")
            result=False
        self.conf.clear()
        self.conf.read(cfgpath)
        self.logger.info("测试CST模型文件是否存在")
        cstfilepath=self.currProjectDir / self.conf['CST']['CSTFilename']
        self.logger.debug("推测模型文件位于%s",str(cstfilepath))
        if(cstfilepath.exists()):
            self.logger.info("测试CST模型文件存在 通过")
            cstfileflag=True
        else:
            self.logger.error("未找到cst文件%s\n"% str(cstfilepath))
            self.logger.info("测试CST模型文件存在 失败")
            result=False
        currCSTMD5=self.genMD5FromCST(cstfilepath).hexdigest()
        savedCSTMD5=self.conf['CST']['CSTFileMD5']
        self.logger.info("测试保存的参数列表与MD5是否与CST模型文件匹配")
        paramjsonpath=self._rap2apo(self.conf['PARAMETERS']['paramfile'])
        
        if(currCSTMD5!=savedCSTMD5):
            self.logger.warning("记录的CST文件MD5_%s与实际的MD5_%s不一致，已被修改"%(savedCSTMD5,currCSTMD5))           
            
            self.logger.warning("重新生成参数列表并保存MD5n/y")
            self.logger.info("正在重新生成参数列表")
            self.readParametersFromCST()
            self.conf['CST']['CSTFileMD5']=currCSTMD5
            self.savecfg()
            self.logger.warning("已更新保存的MD5")
            self.logger.info("测试MD5 通过")
        elif(not paramjsonpath.exists()):
            self.logger.warning("参数列表文件_%s不存在"%str(paramjsonpath))       
            
            self.logger.warning("重新生成并保存参数列表")
            self.readParametersFromCST(paramjsonpath)
        self.logger.info("%s检测并更新项目配置文件结束\n"% cfgfilename)
        return result

    def checkProjectStatus(self,cfgfilename="project.ini",slient=False,force=False):
        result=True
        cfgpath=self.currProjectDir / cfgfilename
        cstfileflag=False
        cfgfileflag=False
        self.logger.info("检测项目配置文件正确性")
        self.logger.info("测试项目配置文件是否存在")
        self.logger.debug("推测项目配置文件位于%s",str(cfgpath))
        if(cfgpath.exists()):
            cfgfileflag=True
            self.logger.info("测试项目配置文件 通过")
        else:
            self.logger.error("未找到项目配置文件%s\n"% str(cfgpath))
            self.logger.info("测试项目配置文件 失败")
            result=False

        self.conf.clear()
        self.conf.read(cfgpath)
        cstfilepath=self.currProjectDir / self.conf['CST']['CSTFilename']
        self.logger.info("测试CST模型文件是否存在")
        self.logger.debug("推测模型文件位于%s",str(cstfilepath))
        if(cstfilepath.exists()):
            cstfileflag=True
            self.logger.info("测试CST模型文件 通过")
        else:
            self.logger.error("未找到cst模型文件%s\n"% str(cstfilepath))
            self.logger.info("测试CST模型文件 失败")
            result=False
        currCSTMD5=self.genMD5FromCST(cstfilepath).hexdigest()
        savedCSTMD5=self.conf['CST']['CSTFileMD5']
        self.logger.info("测试保存的MD5是否与CST模型文件匹配")
        paramjsonpath=self._rap2apo(self.conf['PARAMETERS']['paramfile'])
        if(currCSTMD5!=savedCSTMD5):
            self.logger.warning("记录的CST文件MD5%s与实际的%s不一致，已被修改"%(savedCSTMD5,currCSTMD5))       
            self.logger.info("测试MD5 失败")     
            result=False
        elif(not paramjsonpath.exists()):
            self.logger.warning("参数列表文件_%s不存在"%str(paramjsonpath))       
            result=False
        else:
            self.logger.info("测试MD5 通过")
        
        self.logger.info("%s检测项目配置文件结束\n"% cfgfilename)

        return result




