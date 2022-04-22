"""produce LHS sample"""
###修改内容
###runWithX 修改为 runWithParam 需要提供param_name_list 和 value_list 作为参数
###addTask 同上
###初值需要自己写，留空[]则为默认
###
import os
from myAlgorithm import myAlg

import math
import numpy as np
import cstmanager
import yfunction
import time
import pandas as pd


class myAlg01(myAlg):
    def __init__(self, manager: cstmanager.manager = None, params=None):
        super().__init__(manager, params)
        self.parameter_range = 0
        self.CSTparams = params

        self.state_x0 = []
        self.state_y0 = 0

        # 读写
        # self.mode_location = 'result\\'
        self.log = None
        self.mode_location = None
        self.relative_location = None  # 在setManager后实现
        self.ready = False
        # y函数,
        self.yFunc = yfunction.yfunc(yfunction.myYFunc01)

        ##OTHERS
        self.manager = None
        if manager is not None:
            self.setJobManager(manager)
        # self.results=result.result

        self.input_name = ["nmodes", "fmin", "fmax", "accuracy", "cell"]
        self.input_min = [1, 700, 800, 1e-5, 20]  ##初始值

        self.csv_input_name = self.input_name + ["mode"]

        self.output_name = [
            "frequency",
            "R_divide_Q",
            "R_divide_Q_5mm",
            "R_divide_Q_10mm",
            "Q-factor",
            "Shunt_Inpedence",
            "Total_Loss",
        ]
        self.output_name = None
        self.text_name = ["Frequency", "R_Q", "R_Q_5mm", "Q-Factor", "R_Q_10mm"]
        self.accu_list = pd.DataFrame(
            [[0, 1500, 1e-5], [1500, 4100, 1e-4]],
            columns=["f_down", "f_up", "accuracy"],
        )
        self.cell_list = pd.DataFrame(
            [[0, 1300, 20], [1300, 2000, 15], [2000, 4100, 10]],
            columns=["f_down", "f_up", "cell"],
        )

        # self.dimension_input = len(self.input_name)
        # self.dimension_output = len(self.output_name)

        self.delta_frequency = 50

        self.end_frequency = 2500
        self.continue_flag = [0, 3738.9532]  # [是否继续，上次做完的最后一次频率]

    def checkAndSetReady(self):
        if self.CSTparams is not None and self.manager is not None:
            self.ready = True
        else:
            self.ready = False

    def setCSTParams(self, params):
        self.CSTparams = params
        self.checkAndSetReady()

    def setJobManager(self, manager: cstmanager.manager):
        self.manager = manager
        self.mode_location = str(manager.currProjectDir) + "\\result\\"
        self.relative_location = str(manager.currProjectDir) + "\\save\\csv\\"
        if not os.path.exists(self.relative_location):
            os.makedirs(self.relative_location)
        logpath = os.path.join(manager.getResultDir(), "result.log")
        self.log = open(logpath, "w")
        self.checkAndSetReady()

    def setEditableAttrs(self, dict):
        d = {
            "fmin": self.input_min[1],
            "fmax": self.input_min[2],
            "cflag": self.continue_flag[0],
            "cfreq": self.continue_flag[1],
        }
        d.update(dict)
        self.input_min[1] = d["fmin"]
        self.input_min[2] = d["fmax"]
        self.continue_flag[0] = int(d["cflag"])
        self.continue_flag[1] = d["cfreq"]
        self.end_frequency = d.get("endfreq", 2500)

    def getEditableAttrs(self):
        d = {
            "fmin": self.input_min[1],
            "fmax": self.input_min[2],
            "cflag": self.continue_flag[0],
            "cfreq": self.continue_flag[1],
            "endfreq": self.end_frequency,
        }
        return d

    def logCalcSettings(self):
        print(self.getEditableAttrs())
        pass

    def get_y_trans_r_aprallel(self, xs, run_count):

        nor = self.state_y0
        print("nor:", nor)
        # r = []
        y = []

        for j, x in enumerate(xs):
            self.manager.addTask(self.input_name, x, str(run_count) + str(x[1]))

        self.manager.start()
        self.manager.synchronize()  # 同步 很重要
        rl = self.manager.getFullResults()
        ###SORT RESULTS
        rg = [i["PostProcessResult"] for i in rl]
        rg = sorted(rg, key=lambda x: int(x["name"][16:]))

        for irg in rg:
            print(irg["name"])
            y.append(irg["value"])

        print("y", y)

        return np.array(y).reshape(len(xs), self.dimension_output)

    def write_many(self, title, data):
        name = self.relative_location + title + ".csv"
        #         print("name:",name)
        data.to_csv(name, index=True, sep=",")

    def compire_str(self, a, b):
        # print("compire:"+a+"###"+b+"###")
        if len(a) != len(b):
            # print("False because len")
            return False
        else:
            for i in range(len(a)):
                # print(a[i],b[i])
                if a[i] != b[i]:
                    # print("False because str")
                    return False
            return True

    def get_3_modes_custom(self, resultList):
        return self.__get_3_modes_custom(resultList, self.output_name)

    def __get_3_modes_custom(self, resultList, customResultNameList=None):

        resultNameList = []
        for dict in resultList:
            resultNameList.append(dict["resultName"])
        if customResultNameList is None:
            columnNameSet = set(resultNameList)
            columnNameList = list(columnNameSet)
            columnNameList.sort()
        else:
            columnNameList = customResultNameList

        samples = pd.DataFrame(columns=self.csv_input_name + columnNameList)
        mode1 = np.zeros(len(self.csv_input_name) + len(columnNameList))
        mode2 = np.zeros(len(self.csv_input_name) + len(columnNameList))
        for i in range(len(self.csv_input_name)):
            if i < len(self.csv_input_name) - 1:
                mode1[i] = mode2[i] = self.input_min[i]
            else:
                mode1[i] = 1
                mode2[i] = 2
        columns = self.csv_input_name + resultNameList

        for i in range(len(columnNameList)):
            target = columnNameList[i]
            u = [
                item["value"]
                for item in resultList
                if (item["params"]["iModeNumber"] == 1 and item["resultName"] == target)
            ]
            if len(u) > 0:
                mode1[len(self.csv_input_name) + i] = u[0]
            v = [
                item["value"]
                for item in resultList
                if (item["params"]["iModeNumber"] == 2 and item["resultName"] == target)
            ]
            if len(v) > 0:
                mode2[len(self.csv_input_name) + i] = v[0]

        samples = samples.append(
            pd.DataFrame([list(mode1)], columns=self.csv_input_name + columnNameList)
        )
        samples = samples.append(
            pd.DataFrame([list(mode2)], columns=self.csv_input_name + columnNameList)
        )
        print("samples\n", samples)
        return samples.reset_index(drop=True)

    def get_3_modes(self, title):
        samples = pd.DataFrame(columns=self.csv_input_name + self.output_name)
        location = self.mode_location + title + "\\"
        sub_files = os.listdir(location)
        samples = pd.DataFrame()
        mode1 = np.zeros(len(self.csv_input_name) + len(self.output_name))
        mode2 = np.zeros(len(self.csv_input_name) + len(self.output_name))

        for i in range(len(self.csv_input_name)):
            if i < len(self.csv_input_name) - 1:
                mode1[i] = mode2[i] = self.input_min[i]
            else:
                mode1[i] = 1
                mode2[i] = 2

        for sub_file in sub_files:
            print("sub_file:\n", sub_file)
            sub_m = os.path.join(location, sub_file)

            if "Mode1" in sub_m:
                for i in range(len(self.text_name)):
                    if self.compire_str("Mode1" + self.text_name[i] + ".txt", sub_file):
                        mode1[len(self.csv_input_name) + i] = self.get_value(sub_m)
                        print(sub_m, ":  ", self.get_value(sub_m))

            if "Mode2" in sub_m:
                for i in range(len(self.text_name)):
                    if self.compire_str("Mode2" + self.text_name[i] + ".txt", sub_file):
                        mode2[len(self.csv_input_name) + i] = self.get_value(sub_m)
                        print(sub_m, ":  ", self.get_value(sub_m))

        samples = samples.append(
            pd.DataFrame([list(mode1)], columns=self.csv_input_name + self.output_name)
        )
        samples = samples.append(
            pd.DataFrame([list(mode2)], columns=self.csv_input_name + self.output_name)
        )
        print("samples\n", samples)

        return samples.reset_index(drop=True)

    def get_value(self, file):
        f = open(file)
        text = f.read()
        return float(text[140:])

    def start(self):
        if self.ready == False:
            print("CALCATION NOT READY, PLEASE CHECK SETTINGS.")
            print("IS THE JOBMANAGER SET?")
            return -1
        self.logCalcSettings()
        fmin = self.input_min[1]
        fmax = self.input_min[2]
        start_time = time.time()
        sample = pd.DataFrame([self.input_min], columns=self.input_name)
        samples = pd.DataFrame()

        if self.continue_flag[0] == 0:
            runresult = self.manager.runWithParam(
                self.input_name,
                self.input_min,
                "frequency"
                + str(1000000)[1:]
                + "_"
                + str(fmin).replace(".", "-")
                + "_"
                + str(fmax),
                retry_cnt=1,
            )
            if runresult["TaskStatus"] == "Success":
                self.state_y0 = np.array(runresult["PostProcessResult"])
                # sample = self.get_3_modes("frequency"+str(1000000)[1:]+"_"+str(fmin).replace(".", "-")+"_"+str(fmax)).iloc[0]
                sample = self.get_3_modes_custom(self.state_y0).iloc[0]
                samples = samples.append(sample)
                self.write_many("all_value_" + str(fmin).replace(".", "-"), samples)
                # fmin = np.float(sample["frequency"])
                fmin = (
                    math.ceil(np.float(sample["frequency"]) * 10) / 10
                )  ## round up float to 1 decimals
                fmax = math.floor(sample["frequency"]) + self.delta_frequency
            elif runresult["TaskStatus"] == "Failure":
                print("First Loop Failure")
                return
                pass

        else:
            self.continue_flag[0] = 0
            fmin = self.continue_flag[1]
            samples = pd.read_csv(
                self.relative_location
                + "all_value_"
                + str(fmin).replace(".", "-")
                + ".csv"
            )
            samples = samples.drop(["Unnamed: 0"], 1)

            sample = samples.iloc[-1]
            print("sample is:\n", sample)
            # fmin = np.float(sample["frequency"])
            fmin = (
                math.ceil(np.float(sample["frequency"]) * 10) / 10
            )  ## round up float to 1 decimals
            fmax = math.floor(sample["frequency"]) + self.delta_frequency

        while fmin < self.end_frequency:

            satisfy_flag = False
            while satisfy_flag == False:

                self.input_min[1] = fmin
                self.input_min[2] = fmax
                print(self.accu_list)
                print(
                    (self.accu_list["f_down"] <= fmin)
                    & (self.accu_list["f_up"] > fmin)
                )
                self.input_min[3] = float(
                    self.accu_list.loc[
                        (self.accu_list["f_down"] <= fmin)
                        & (self.accu_list["f_up"] > fmin),
                        "accuracy",
                    ]
                )
                self.input_min[4] = float(
                    self.cell_list.loc[
                        (self.cell_list["f_down"] <= fmin)
                        & (self.cell_list["f_up"] > fmin),
                        "cell",
                    ]
                )
                print("input is:", self.input_min)
                runresult = self.manager.runWithParam(
                    self.input_name,
                    self.input_min,
                    "frequency"
                    + str(1000000)[1:]
                    + "_"
                    + str(fmin).replace(".", "-")
                    + "_"
                    + str(fmax),
                    retry_cnt=1,
                )
                if runresult["TaskStatus"] == "Success":
                    self.state_y0 = np.array(runresult["PostProcessResult"])
                    sample = self.get_3_modes_custom(self.state_y0).iloc[0]
                    print(
                        "--------\nfmin_define:",
                        fmin,
                        "\nfmax_define:",
                        fmax,
                        "\nf_get:",
                        sample["frequency"],
                    )
                elif runresult["TaskStatus"] == "Failure":
                    print("Main Loop Failure Met max retry count")
                    print("Skip this run.")
                    print(
                        self.log,
                        "Skipped freq calc %f Mhz-%f Mhz because of failure\n"
                        % (fmin, fmax),
                        flush=True,
                    )  ### OUTPUT TO LOG
                    fmin = fmax
                    fmax = fmax + self.delta_frequency  # 200MHZ
                    print("Adjust New Fmin to %f" % fmin)
                    print("Adjust New Fmax to %f" % fmax)

                    continue

                # sample = self.get_3_modes("frequency"+str(1000000)[1:]+"_"+str(fmin).replace(".", "-")+"_"+str(fmax)).iloc[0]

                if sample["frequency"] == fmin:
                    #                    try:
                    #                        self.input_min[0] = 2
                    #                        print("input is:",self.input_min)
                    #                        self.state_y0 = np.array(self.w.runWithParam(self.input_name, self.input_min, "frequency"+str(1000000)[1:]+"_"+str(fmin).replace(".", "-")+"_"+str(fmax)+"_2mode"))
                    #                        sample = self.get_3_modes("frequency"+str(1000000)[1:]+"_"+str(fmin).replace(".", "-")+"_"+str(fmax)+"_2mode")
                    #                        if sample.loc[0,"frequency"] == fmin:
                    #                            sample = sample.iloc[1]
                    #                        else:
                    #                            sample = sample.iloc[0]
                    #                        self.input_min[0] = 1
                    #                    except:
                    self.input_min[1] = (
                        float(math.ceil(sample["frequency"] * 10)) / 10
                    )  ## round up float to 1 decimals
                    runresult = self.manager.runWithParam(
                        self.input_name,
                        self.input_min,
                        "frequency"
                        + str(1000000)[1:]
                        + "_"
                        + str(self.input_min[1]).replace(".", "-")
                        + "_"
                        + str(fmax)
                        + "_variate_",
                    )
                    while runresult["TaskStatus"] != "Success":
                        print("Variate Loop Failure")
                        fmax = math.floor(sample["frequency"]) + self.delta_frequency
                        print("Adjust New Fmax to %f" % fmax)
                        runresult = self.manager.runWithParam(
                            self.input_name,
                            self.input_min,
                            "frequency"
                            + str(1000000)[1:]
                            + "_"
                            + str(self.input_min[1]).replace(".", "-")
                            + "_"
                            + str(fmax)
                            + "_variate_",
                        )

                    self.state_y0 = np.array(runresult["PostProcessResult"])
                    sample = self.get_3_modes_custom(self.state_y0).iloc[0]

                    # sample = self.get_3_modes("frequency"+str(1000000)[1:]+"_"+str(self.input_min[1]).replace(".", "-")+"_"+str(fmax)+"_variate").iloc[0]

                if float(sample["frequency"]) < fmax:
                    satisfy_flag = True
                    print("judge:True")
                else:
                    fmax = math.floor(sample["frequency"]) + 20
                    print("judge:False")
            samples = samples.append(sample)
            samples = samples.reset_index(drop=True)
            self.write_many("all_value_" + str(fmin).replace(".", "-"), samples)
            # fmin = np.float(sample["frequency"])
            fmin = (
                math.ceil(np.float(sample["frequency"]) * 10) / 10
            )  ## round up float to 1 decimals
            fmax = math.floor(sample["frequency"]) + self.delta_frequency

        end_time = time.time()
        print(start_time - end_time)
        self.log.close()
        return 0


if __name__ == "__main__":
    from postprocess_cst import vbpostprocess
    from pathlib import Path

    vbp = vbpostprocess()
    import json

    fp = open("template/defaultPPS.json", "r")
    r = json.load(fp)

    vbp.appendPostProcessSteps(r)
    fp = open("temp/a.txt", "w")
    ilist = vbp.createPostProcessVBCodeLines()
    for line in ilist:
        fp.write(line)
    fp.close()
    dir = Path(r"project\HOM analysis\result\frequency000000_700_800")
    vbp.setResultDir(dir)

    cc = vbp.readAllResults()
    print(cc)
    alg = myAlg01()
    sample = alg.get_3_modes_custom(cc).iloc[0]
    print(sample)
    fmin = float(sample["frequency"])
    fmax = math.floor(sample["frequency"]) + alg.delta_frequency
    alg.input_min[1] = fmin
    alg.input_min[2] = fmax
    print(alg.accu_list)
    print((alg.accu_list["f_down"] <= fmin) & (alg.accu_list["f_up"] >= fmin))
    alg.input_min[3] = float(
        alg.accu_list.loc[
            (alg.accu_list["f_down"] <= fmin) & (alg.accu_list["f_up"] >= fmin),
            "accuracy",
        ]
    )
    alg.input_min[4] = float(
        alg.cell_list.loc[
            (alg.cell_list["f_down"] <= fmin) & (alg.cell_list["f_up"] >= fmin), "cell"
        ]
    )

