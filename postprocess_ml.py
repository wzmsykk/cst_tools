from pathlib import Path
import torch

class mlpostprocess():

    def __init__(self,modelpath) -> None:
        self.trained_model_path=Path(modelpath)
        with open(self.trained_model_path,'rb') as f:
            self.model=torch.load(f)
        pass

    def 