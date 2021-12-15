import os, json, re, copy, sys, shutil
import result
import numpy as np
import time
import subprocess
import logging
import hashlib
import pathlib
import worker


class local_superfish_worker(worker.worker):
    def __init__(self, id, type, config, logger):
        super().__init__(id, type=type, config=config, logger=logger)
        ## configs
        self.projectType = config["ProjectType"]
        self.tempDir = pathlib.Path(config["tempPath"])
        self.resultDir = pathlib.Path(config["resultDir"])
        self.input = pathlib.Path(config["cstPath"])

        # LOGGING#
        self.logger.info("LOCAL POISSON SUPERFISH WORKER ID:%s" % str(id))
        self.logger.info("TempDir:%s" % str(self.tempDir))
        self.logger.info("TaskFileDir:%s" % str(self.taskFileDir))

        # FINDSF
        self.currentSFENVPATH = config["SFENVPATH"]

