from pathlib import Path
import json
from projectutil import is_number


class vbpreprocess:
    def __init__(self) -> None:

        self.resultDir = None
        self.preProcessDataDir = Path("data/preprocess").absolute()
        self.altIncludeDir = Path("data").absolute()
        self.preProcessDocList = list()
        self.preProcessID = 0
        pass

    def createPreProcessVBCodeLines(self):
        lst = []
        importFileList = []
        for doc in self.preProcessDocList:
            importFile = doc["import"]
            importFileList.append(importFile)
        importFileSet = set(importFileList)
        for vbheaderfileName in importFileSet:
            importFilePath = self.preProcessDataDir / vbheaderfileName
            if not importFilePath.exists():
                importFilePath = self.altIncludeDir / vbheaderfileName
            fp = open(importFilePath, "r")
            for line in fp.readlines():
                lst.append(line)
            lst.append("\n")
        lst.append("\nSub CustomPreProcess\n")
        for doc in self.preProcessDocList:
            funcString = "    " + doc["funcString"]
            lst.append(funcString)
        lst.append("End Sub\n")
        return lst

    def appendPreProcessSteps(self, pslist):
        for doc in pslist:
            configdict = doc["config"]
            methodname = doc["method"]
            result = getattr(self, methodname)(configdict)

    def dummyReadout(self, *args, **kwargs):
        ## I Do Nothing
        return 0

    def commonReadout(self, resultFilename):
        rpath = self.resultDir / resultFilename
        d = self.readAllLines(rpath)
        return d

    def readAllLines(rpath):
        fp = open(rpath, "r")
        lines = fp.readlines(fp)
        return fp

    def readAllResults(self):
        resultList = []
        for doc in self.preProcessDocList:
            d = {}
            d["id"] = doc["id"]
            d["resultName"] = doc["resultName"]
            d["value"] = doc.get("readoutmethod", self.dummyReadout)(
                doc["resultFilename"]
            )
            d["params"] = doc["params"]
            resultList.append(d)
        return resultList

    def preparamize(self, configdict: dict):
        funcString = "StartPreProcess"
        paramdoc = {}
        doc = dict()
        doc.update({"id": self.postProcessID})
        doc.update({"import": "preparamize.vb"})
        doc.update({"resultName": configdict.get("resultName", "default")})
        doc.update(
            {"resultFilename": configdict.get("resultFilename", "default_filename")}
        )
        doc.update({"funcString": funcString})
        doc.update({"readoutmethod": self.commonReadout})
        doc.update({"params": paramdoc})
        self.preProcessDocList.append(doc)
        self.preProcessID += 1

    def getparamlist(self, configdict: dict):
        funcString = "GetParamList"
        paramdoc = {}
        doc = dict()
        doc.update({"id": self.postProcessID})
        doc.update({"import": "readParams.vb"})
        doc.update({"resultName": configdict.get("resultName", "default")})
        doc.update(
            {"resultFilename": configdict.get("resultFilename", "default_filename")}
        )
        doc.update({"funcString": funcString})
        doc.update({"readoutmethod": self.getparamlist_readout})
        doc.update({"params": paramdoc})
        self.preProcessDocList.append(doc)
        self.preProcessID += 1

    def getparamlist_readout(self, resultpath):
        ##从生成的ascii文件得到参数列表

        paramslist = []
        par = open(resultpath, "r")
        lines = par.readlines()
        totalparams = int(lines[2])
        for N in range(totalparams):
            linesN = lines[3 + N]
            words = linesN.split()
            paramname = words[1]
            paramvalue = words[2]
            paramdescript = ""
            if len(words) >= 4:
                paramdescript = words[3]
            ##推断类型
            paramtype = "double"
            if not is_number(paramvalue):
                paramtype = "expression"
            dictw = {}
            dictw["id"] = N
            dictw["name"] = paramname
            dictw["value"] = paramvalue
            dictw["type"] = paramtype
            if paramtype == "double":
                dictw["fixed"] = False
            else:
                dictw["fixed"] = True
            dictw["description"] = paramdescript

            paramslist.append(dictw)

        par.close()
        fp = open(resultpath, "w")
        # json.dump(paramslist,fp=fp)
        fp.close()
        return paramslist

    def saveCSTProject(self, configdict: dict):
        funcString = "StartPreProcess"
        paramdoc = {}
        doc = dict()
        doc.update({"id": self.postProcessID})
        doc.update({"import": "saveCST.vb"})
        doc.update({"resultName": configdict.get("resultName", "default")})
        doc.update(
            {"resultFilename": configdict.get("resultFilename", "default_filename")}
        )
        doc.update({"funcString": funcString})
        doc.update({"readoutmethod": self.commonReadout})
        doc.update({"params": paramdoc})
        self.preProcessDocList.append(doc)
        self.preProcessID += 1


###SET

