from pathlib import Path

class vba_parser():
    def __init__(self) -> None:
        pass
        self.filePath=None
        self.filelines=[]
        self.vbfuncDef={}
    def reset(self):
        self.filelines.clear()
        self.filePath=None
    def setVBAFile(self,filePath):
        self.filelines.clear()
        self.filePath=Path(filePath)
        fp=open(self.filePath,"r")
        for line in fp.readlines():
            self.filelines.append(line)

    def getFuncList(self):

        for line in self.filelines():
            words=line.split()
            if words[0]=='Function' or 'Sub':
                FuncName=words[1].split('(')[0]
                ###TODO PASS

