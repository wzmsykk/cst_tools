"""produce LHS sample"""
import os
import logging
import hashlib
import json
from .myAlgorithm import myAlg

import math
import numpy as np
from . import cstmanager
from .hom_scan import (
    AdaptiveHomScanner,
    IncompleteScanError,
    ModeResult,
    ScanCheckpointStore,
    ScanPolicy,
)
from . import yfunction
import time
import pandas as pd
from pathlib import Path


class myAlg01(myAlg):
    def __init__(self, manager: cstmanager.SimulationManager = None, params=None):
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

    def setJobManager(self, manager: cstmanager.SimulationManager):
        self.manager = manager
        self.logger = getattr(manager, "logger", logging.getLogger(__name__))
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

    def validate_postprocess_settings(self, settings):
        if not settings:
            raise ValueError("HOM single-mode scan requires postprocess settings")
        frequency_steps = [
            item for item in settings if item.get("resultName", "").casefold() == "frequency"
        ]
        if len(frequency_steps) != 1:
            raise ValueError("HOM single-mode scan requires one frequency result")
        for item in settings:
            method = item.get("method")
            params = item.get("params") or {}
            if not isinstance(method, str) or method.endswith("_All"):
                raise ValueError("HOM single-mode scan does not use _All methods")
            if int(params.get("iModeNumber", 0)) != 1:
                raise ValueError("HOM postprocess methods must target iModeNumber=1")

    def logCalcSettings(self):
        print(self.getEditableAttrs())
        pass

    def get_y_trans_r_aprallel(self, xs, run_count):

        nor = self.state_y0
        print("nor:", nor)
        # r = []
        y = []

        tasks = [
            self._simulation_task(x, str(run_count) + str(x[1]))
            for x in xs
        ]
        rl = self.manager.run_batch(tasks)
        ###SORT RESULTS
        rg = [i["PostProcessResult"] for i in rl]
        rg = sorted(rg, key=lambda x: int(x["name"][16:]))

        for irg in rg:
            print(irg["name"])
            y.append(irg["value"])

        print("y", y)

        return np.array(y).reshape(len(xs), self.dimension_output)

    def _simulation_task(self, values, job_name, retry_count=0):
        params = dict(zip(self.input_name, values))
        return cstmanager.SimulationTask(
            params=params,
            job_name=job_name,
            retry_count=retry_count,
        )

    def _execute_simulation(self, values, job_name, retry_count=0):
        return self.manager.execute(
            self._simulation_task(values, job_name, retry_count)
        )

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

    def _legacy_start(self):
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
            runresult = self._execute_simulation(
                self.input_min,
                "frequency"
                + str(1000000)[1:]
                + "_"
                + str(fmin).replace(".", "-")
                + "_"
                + str(fmax),
                retry_count=1,
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
                runresult = self._execute_simulation(
                    self.input_min,
                    "frequency"
                    + str(1000000)[1:]
                    + "_"
                    + str(fmin).replace(".", "-")
                    + "_"
                    + str(fmax),
                    retry_count=1,
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
                    runresult = self._execute_simulation(
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
                        runresult = self._execute_simulation(
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

    def _scan_policy(self):
        initial_width = float(self.input_min[2]) - float(self.input_min[1])
        return ScanPolicy(
            start=float(self.input_min[1]),
            initial_stop=float(self.input_min[2]),
            stop=float(self.end_frequency),
            window_width=min(float(self.delta_frequency), initial_width),
            requested_modes=1,
        )

    def _mesh_settings(self, frequency):
        accuracy = self.accu_list.loc[
            (self.accu_list["f_down"] <= frequency)
            & (self.accu_list["f_up"] > frequency),
            "accuracy",
        ]
        cells = self.cell_list.loc[
            (self.cell_list["f_down"] <= frequency)
            & (self.cell_list["f_up"] > frequency),
            "cell",
        ]
        if len(accuracy) != 1 or len(cells) != 1:
            raise ValueError(f"no unique mesh policy for frequency {frequency}")
        return float(accuracy.iloc[0]), float(cells.iloc[0])

    def _extract_scan_modes(self, result_list):
        if not result_list:
            return []
        values = {}
        for item in result_list:
            result_name = item.get("resultName")
            if not isinstance(result_name, str) or not result_name:
                raise ValueError("postprocess result has no resultName")
            value = item.get("value")
            if isinstance(value, dict):
                if len(value) != 1:
                    raise ValueError("single-mode result must contain exactly one value")
                value = next(iter(value.values()))
            params = item.get("params") or {}
            if params and int(params.get("iModeNumber", 1)) != 1:
                raise ValueError("single-mode result does not target mode 1")
            if result_name in values:
                raise ValueError(f"duplicate result {result_name!r}")
            values[result_name] = float(value)

        frequency_name = next(
            (name for name in values if name.casefold() == "frequency"), None
        )
        if frequency_name is None:
            raise ValueError("postprocess results do not contain frequency")
        return [
            ModeResult(
                mode_index=1,
                frequency=float(values[frequency_name]),
                values=values,
            )
        ]

    def _project_fingerprint(self):
        project = getattr(self.manager, "cstProjPath", None)
        if project is None:
            fingerprint = {
                "projectDirectory": str(Path(self.manager.currProjectDir).resolve())
            }
        else:
            path = Path(project).resolve()
            stat = path.stat()
            fingerprint = {
                "path": str(path),
                "size": stat.st_size,
                "mtimeNs": stat.st_mtime_ns,
            }
        project_config = getattr(self.manager, "pconfm", None)
        if project_config is not None:
            postprocess = project_config.getCurrPPSList()
            encoded = json.dumps(
                postprocess,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            fingerprint["postprocessSha256"] = hashlib.sha256(encoded).hexdigest()
        return fingerprint

    def _write_scan_results(self, report):
        rows = [
            {"mode": scan_index, "solverMode": mode.mode_index, **mode.values}
            for scan_index, mode in enumerate(
                sorted(report.modes, key=lambda item: item.frequency),
                start=1,
            )
        ]
        destination = Path(self.relative_location) / "hom_scan_results.csv"
        temporary = destination.with_suffix(".csv.tmp")
        pd.DataFrame(rows).to_csv(temporary, index=False)
        temporary.replace(destination)

    def start(self):
        if not self.ready:
            raise RuntimeError("HOM scan is not ready")

        policy = self._scan_policy()
        scanner = AdaptiveHomScanner(policy)
        checkpoint_store = ScanCheckpointStore(
            Path(self.relative_location) / "hom_scan_checkpoint.json"
        )
        fingerprint = self._project_fingerprint()
        report = None
        pending = None
        if self.continue_flag[0]:
            if not checkpoint_store.path.exists():
                raise FileNotFoundError(checkpoint_store.path)
            report, pending = checkpoint_store.load(policy, fingerprint)
            pending = list(report.failed) + pending
            report.failed.clear()
            report.failure_reasons.clear()

        def save_checkpoint(current_report, current_pending):
            checkpoint_store.save(
                policy,
                fingerprint,
                current_report,
                current_pending,
            )
            self._write_scan_results(current_report)

        def solve(request):
            accuracy, cells = self._mesh_settings(request.interval.lo)
            values = [
                request.requested_modes,
                request.solve_lo,
                request.solve_hi,
                accuracy,
                cells,
            ]
            job_name = (
                f"hom_{request.interval.lo:g}_{request.interval.hi:g}"
            )
            result = self._execute_simulation(values, job_name, retry_count=1)
            if result.get("TaskStatus") != "Success":
                reason = result.get("FailureReport", "unknown CST failure")
                raise RuntimeError(reason)
            postprocess = result.get("PostProcessResult")
            if not isinstance(postprocess, list):
                raise ValueError("CST task returned no postprocess result list")
            return self._extract_scan_modes(postprocess)

        started = time.monotonic()
        try:
            final_report = scanner.run(
                solve,
                pending=pending,
                report=report,
                checkpoint=save_checkpoint,
            )
            save_checkpoint(final_report, [])
            self.logger.info(
                "HOM scan completed: modes=%d intervals=%d solver_calls=%d elapsed=%.3fs",
                len(final_report.modes),
                len(final_report.completed),
                final_report.solver_calls,
                time.monotonic() - started,
            )
            return final_report
        except IncompleteScanError as exc:
            self.logger.error(
                "HOM scan incomplete: failed_intervals=%d solver_calls=%d",
                len(exc.report.failed),
                exc.report.solver_calls,
            )
            raise
        finally:
            if self.log is not None and not self.log.closed:
                self.log.close()


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

