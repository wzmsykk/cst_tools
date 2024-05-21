import json
from pathlib import Path

fp=open(r"./test/data/Pillbox/params.json")
workerconfig={}
workerconfig["workDir"]=r".\temp"
workerconfig["cstPath"]=r".\test\data\Pillbox\Pillbox.cst"
workerconfig["taskFileDir"]=r".\temp"
workerconfig["resultDir"]=r".\temp"
workerconfig["tempPath"]=r".\temp"
workerconfig["cstPatternDir"]=r".\data"
workerconfig["CSTENVPATH"]=r"D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe"
workerconfig["paramList"]=json.load(fp)
fp=open(r"./test/data/testworker.json","w")
json.dump(workerconfig,fp,indent=4)