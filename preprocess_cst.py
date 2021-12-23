from pathlib import Path
from install_compat import resource_path
from projectutil import is_number


class vbpreprocess:
    def __init__(self) -> None:

        self.resultDir = None
        self.preProcessDataDir = resource_path("data/preprocess")
        self.altIncludeDir = resource_path("data")
        self.preProcessDocList = list()
        self.preProcessID = 0
        pass

    def setResultDir(self, rDir):
        self.resultDir = Path(rDir)

    def reset(self):
        self.resultDir = None
        self.preProcessDocList.clear()
        self.preProcessID = 0

    def getUsedFileNameList(self):
        namelist = list()
        for doc in self.preProcessDocList:
            namelist.append(doc["resultFilename"])
        return namelist

    def createPreProcessVBCodeLines(self, createMain=True):
        lst = []
        importFileList = []
        for doc in self.preProcessDocList:
            importFile = doc.get("import", None)
            if importFile is not None:
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
            funcString = "    " + doc["funcString"] + "\n"
            lst.append(funcString)
        lst.append("End Sub\n")
        if createMain:
            lst.append("\nSub Main\n")
            funcString = "    " + "CustomPreProcess" + "\n"
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

    def OpenFile(self, configdict: dict):
        cstpath = configdict.get("cstpath")
        funcString = "OpenFile" + '"' + cstpath + '"'
        paramdoc = {}
        doc = dict()
        doc.update({"id": self.preProcessID})
        doc.update({"resultName": configdict.get("resultName", "default")})
        doc.update(
            {"resultFilename": configdict.get("resultFilename", "default_filename")}
        )
        doc.update({"funcString": funcString})
        doc.update({"readoutmethod": self.commonReadout})
        doc.update({"params": paramdoc})
        self.preProcessDocList.append(doc)
        self.preProcessID += 1

    def preparamize(self, configdict: dict):
        funcString = "StartPreProcess"
        paramdoc = {}
        doc = dict()
        doc.update({"id": self.preProcessID})
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
        ### dict resultName
        resultpath = Path(configdict.get("resultpath", "./a.txt"))
        resultFilename = resultpath.stem

        funcString = "GetParamList " + '"' + str(resultpath) + '"'
        paramdoc = {}
        doc = dict()
        doc.update({"id": self.preProcessID})
        doc.update({"import": "GetParamList.vb"})
        doc.update({"resultName": configdict.get("resultName", "default")})
        doc.update({"resultFilename": resultFilename})
        doc.update({"resultpath": resultpath})
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
        # dict cst vb path
        outpath = configdict.get("outpath", r"./temp/a.cst")
        outpath = str(Path(outpath).absolute())
        funcString = "SaveCST" + " " + '"' + outpath + '"'
        paramdoc = {}
        doc = dict()
        doc.update({"id": self.preProcessID})
        doc.update({"import": "saveCST.vb"})
        doc.update({"resultName": configdict.get("resultName", "default")})
        doc.update(
            {"resultFilename": configdict.get("resultFilename", "default_filename.txt")}
        )
        doc.update({"funcString": funcString})
        doc.update({"outpath": outpath})
        doc.update({"readoutmethod": self.commonReadout})
        doc.update({"params": paramdoc})
        self.preProcessDocList.append(doc)
        self.preProcessID += 1


###SET

