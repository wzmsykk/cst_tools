import configparser
import os,shutil
import logger,json
import pathlib
class GlobalConfmanager(object):
    
    def __init__(self,Logger=None):
        self.projlist=[]
        self.logger=Logger
        self.conf = configparser.ConfigParser()
        self.confdir=pathlib.Path(r'.\config')
        if (not self.confdir.exists()):
            self.confdir.mkdir()
        self.def_global_cfg_path=self.confdir / 'default.ini'
        self.curr_global_cfg_path=self.confdir / 'current.ini'
        ##Generate new default conf file
        if (not self.def_global_cfg_path.exists()):
            self.conf.add_section("BASE")
            self.conf.set('BASE','datadir','./data')
            self.conf.set('BASE','tempdir','./temp')
            self.conf.set('BASE','logdir','./log')  
            self.conf.set('BASE','resultdir','./result')        
            self.conf.add_section("CST")
            self.conf.set('CST','cstver','')
            self.conf.set('CST','cstexepath','')
            self.conf.add_section("PROJECT")
            self.conf.set('PROJECT','currprojdir','')

        if (not self.curr_global_cfg_path.exists()):

            self.logger.warning("未找到curr_global_cfg.")
            self.logger.warning("使用default.")
        else:
            self.logger.warning("找到curr_global_cfg:%s" % self.curr_global_cfg_path)
            self.conf.read(self.curr_global_cfg_path)            

    def printconf(self):
        self.logger.info("全局信息:")
        self.logger.info("data目录:%s"% self._rstr2astr(self.conf['BASE']['datadir']))
        self.logger.info("temp目录:%s"% self._rstr2astr(self.conf['BASE']['tempdir']))
        self.logger.info("log目录:%s"% self._rstr2astr(self.conf['BASE']['logdir']))
        self.logger.info("result目录:%s"% self._rstr2astr(self.conf['BASE']['resultdir']))
        self.logger.info("CST版本:%s"% self.conf['CST']['cstver'])
        self.logger.info("CSTEXE路径:%s"% self.conf['CST']['cstexepath'])
        self.logger.info("project目录:%s"% self._rstr2astr(self.conf['PROJECT']['currprojdir']))
    def _rstr2astr(self,instr): #_relative_path_str_to_abspath_str function
        ostr=str(pathlib.Path(instr).absolute())
        return ostr
    def saveconf(self):
        f=open(self.curr_global_cfg_path,'w')
        self.conf.write(f)
        self.logger.info("已保存全局配置文件于%s。" %self.curr_global_cfg_path)
        f.close()



    def checkConfig(self):
        #测试CST环境位置
        result=True 
        self.logger.info("检查全局配置开始.")
        cfg=self.conf
        self.logger.info("检查CST PATH.")
        cstenvexepath=pathlib.Path(cfg['CST']['cstexepath'])
        if (not cstenvexepath.exists()):
            self.logger.warning("定义的cstexepath:%s不存在。" %cfg['CST']['cstexepath'] )
            self.logger.warning("尝试寻找cstexepath。")
            try:
                cfg['CST']['cstexepath'],cfg['CST']['cstver']=self.findCSTenv()
            except FileNotFoundError:
                self.logger.error("未找到CST ENV PATH,请从config指定PATH")
                self.logger.info("检查CST PATH 失败.")
                result=False
            else:
                self.logger.info("检查CST PATH 失败, 已使用自动寻找到的有效cst path作为代替.")
            
        else:
            self.logger.info("检查CST PATH 成功.")
            
        #测试CST版本
        self.logger.info("检查CST 版本.")
        if (int(cfg['CST']['cstver'])<2015 or int(cfg['CST']['cstver'])>2020):
            self.logger.warning("定义的cstver不正确(req:cstver>2015&&<2021)。")
            self.logger.warning("尝试从cstexepath寻找cstver。")
            self.logger.error("功能未实现，请手动指定。")
            
            result=False
        self.logger.debug("CST ENV PATH为%s" % cfg['CST']['cstexepath'])
        self.logger.debug("CST 版本为%s" % cfg['CST']['cstver'])
        self.logger.info("检查CST 版本 结束.")
        #测试各个路径是否存在，若否则创建目录
        self.logger.info("检查各个路径是否存在.")
        for names,dirs in cfg['BASE'].items():
            pathobj=pathlib.Path(dirs)
            if(not pathobj.exists()):                
                pathobj.mkdir()
                self.logger.info("已建立%s于%s。" %(names,dirs))

        self.logger.info("检查全局配置结束.")
        if (result==False):
            self.logger.info("未通过全局配置检测")
        else:
            self.logger.info("通过全局配置检测")
        return result
    def findCSTenv(self):
        self.logger.info("寻找CSTenv开始")
        ed1=":\\Program Files (x86)\\CST Studio Suite "
        ed2="\\CST DESIGN ENVIRONMENT.exe"
        for j in range(2015,2025):        
            for i in range(ord('C'),ord('Z')):            
                if pathlib.Path(chr(i)+ed1+str(j)+ed2).exists():
                    success=True
                    CSTexepath=chr(i)+ed1+str(j)+ed2
                    CSTver=str(j)
                    self.logger.info("FOUND CST VERSION %s at %s"% (str(j),CSTexepath))
                    self.logger.info("寻找CSTenv结束")
                    return CSTexepath,CSTver
        raise FileNotFoundError
        return None,None

    ###检查project
    def checkCurrProject(self):
        self.logger.info("检查project开始")
        curprojdirpath=pathlib.Path(self.conf['PROJECT']['currprojdir'])
        if os.path.exists(curprojdirpath):
            self.logger.info("找到project目录:%s"% str(curprojdirpath))
        else:
            self.logger.info("未找到project目录:%s"% str(curprojdirpath))
            os.makedirs(curprojdirpath,exist_ok=True)
            self.logger.info("已创建project目录:%s"% str(curprojdirpath))
        self.logger.info("检查project结束")


