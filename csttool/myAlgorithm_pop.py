"""produce LHS sample"""
import os
import logging
import hashlib
import json
from dataclasses import replace
from .myAlgorithm import myAlg

import math
import numpy as np
from . import cstmanager
from .hom_scan import (
    AdaptiveHomScanner,
    IncompleteScanError,
    ScanInterrupted,
    ModeResult,
    ScanCheckpointStore,
    ScanPolicy,
)
from .hom_run_manifest import HomRunManifest
from .mesh_convergence import MeshConvergenceSettings
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

        self.input_name = ["nmodes", "fmin", "fmax"]
        self.input_min = [1, 700, 800]  ##初始值

        self.csv_input_name = self.input_name + ["mode"]

        self.output_name = [
            "frequency",
            "R_divide_Q",
            "R_divide_Q_5mm",
            "R_divide_Q_10mm",
            "Q-factor",
            "Shunt_Impedance",
            "Total_Loss",
        ]
        self.output_name = None
        self.text_name = ["Frequency", "R_Q", "R_Q_5mm", "Q-Factor", "R_Q_10mm"]
        self.mesh_cells_per_wavelength = 20
        self.mesh_convergence_enabled = False
        self.mesh_convergence_start = 10
        self.mesh_convergence_stop = 30
        self.mesh_convergence_step = 5
        self.mesh_convergence_tolerance = 0.01

        # self.dimension_input = len(self.input_name)
        # self.dimension_output = len(self.output_name)

        self.delta_frequency = 50

        self.end_frequency = 2500
        self.resume_requested = False

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
        }
        d.update(dict)
        self.input_min[1] = d["fmin"]
        self.input_min[2] = d["fmax"]
        self.end_frequency = d.get("endfreq", 2500)
        self.mesh_cells_per_wavelength = int(
            d.get("mesh_cells_per_wavelength", 20)
        )
        if self.mesh_cells_per_wavelength < 1:
            raise ValueError("mesh_cells_per_wavelength must be positive")
        self.mesh_convergence_enabled = bool(
            d.get("mesh_convergence_enabled", False)
        )
        self.mesh_convergence_start = int(d.get("mesh_convergence_start", 10))
        self.mesh_convergence_stop = int(d.get("mesh_convergence_stop", 30))
        self.mesh_convergence_step = int(d.get("mesh_convergence_step", 5))
        self.mesh_convergence_tolerance = float(
            d.get("mesh_convergence_tolerance", 0.01)
        )
        MeshConvergenceSettings(
            self.mesh_convergence_enabled,
            self.mesh_convergence_start,
            self.mesh_convergence_stop,
            self.mesh_convergence_step,
            self.mesh_convergence_tolerance,
        )

    def set_resume(self, resume: bool) -> None:
        self.resume_requested = bool(resume)

    def getEditableAttrs(self):
        d = {
            "fmin": self.input_min[1],
            "fmax": self.input_min[2],
            "endfreq": self.end_frequency,
            "mesh_cells_per_wavelength": self.mesh_cells_per_wavelength,
            "mesh_convergence_enabled": self.mesh_convergence_enabled,
            "mesh_convergence_start": self.mesh_convergence_start,
            "mesh_convergence_stop": self.mesh_convergence_stop,
            "mesh_convergence_step": self.mesh_convergence_step,
            "mesh_convergence_tolerance": self.mesh_convergence_tolerance,
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

    def _simulation_task(
        self, values, job_name, retry_count=0, *, continue_from_snapshot=False
    ):
        params = dict(zip(self.input_name, values))
        return cstmanager.SimulationTask(
            params=params,
            job_name=job_name,
            retry_count=retry_count,
            continue_from_snapshot=continue_from_snapshot,
        )

    def _execute_simulation(
        self, values, job_name, retry_count=0, *, continue_from_snapshot=False
    ):
        return self.manager.execute(
            self._simulation_task(
                values,
                job_name,
                retry_count,
                continue_from_snapshot=continue_from_snapshot,
            )
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

    def _scan_policy(self):
        initial_width = float(self.input_min[2]) - float(self.input_min[1])
        return ScanPolicy(
            start=float(self.input_min[1]),
            initial_stop=float(self.input_min[2]),
            stop=float(self.end_frequency),
            window_width=min(float(self.delta_frequency), initial_width),
            requested_modes=1,
        )

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
            {
                "mode": scan_index, "solverMode": mode.mode_index, **mode.values,
                "taskName": mode.task_name,
                "taskId": mode.task_id,
                "projectSnapshot": mode.project_snapshot or "",
                "resultDirectory": str(Path(mode.project_snapshot).parent) if mode.project_snapshot else "",
            }
            for scan_index, mode in enumerate(
                sorted(report.modes, key=lambda item: item.frequency),
                start=1,
            )
        ]
        destination = Path(self.relative_location) / "hom_scan_results.csv"
        temporary = destination.with_suffix(".csv.tmp")
        pd.DataFrame(rows).to_csv(temporary, index=False, encoding="utf-8-sig")
        temporary.replace(destination)
        guide = destination.with_name("hom_scan_results_README.txt")
        temporary_guide = guide.with_suffix(".txt.tmp")
        temporary_guide.write_text(
            "HOM 扫描结果与 CST 存档对应说明\n\n"
            "hom_scan_results.csv 每行对应一个已确认模态，按频率升序排列。\n"
            "mode：扫描模态序号；solverMode：该次求解中的模态编号。\n"
            "frequency：频率，单位 MHz。\n"
            "taskName / taskId：产生该结果的任务名称和唯一编号。\n"
            "projectSnapshot：对应的 CST 存档文件；resultDirectory：后处理结果目录。\n"
            "这两列的路径均相对于项目根目录，不是 CSV 所在目录。\n"
            "打开 CST 存档时请保留同名配套目录；每个任务目录的 task_result.json 保存原始任务与后处理结果。\n"
            "运行中或中断时 CSV 仅包含已经确认的结果，不能据此判断完整扫描已经结束。\n",
            encoding="utf-8-sig",
        )
        temporary_guide.replace(guide)

    def start(self):
        if not self.ready:
            raise RuntimeError("HOM scan is not ready")

        policy = self._scan_policy()
        HomRunManifest.ensure(
            Path(self.relative_location) / "scan_manifest.json",
            self.manager,
            policy,
            mesh_cells_per_wavelength=self.mesh_cells_per_wavelength,
        )
        scanner = AdaptiveHomScanner(policy, logger=self.logger)
        checkpoint_store = ScanCheckpointStore(
            Path(self.relative_location) / "hom_scan_checkpoint.json"
        )
        fingerprint = self._project_fingerprint()
        report = None
        pending = None
        if self.resume_requested:
            if not checkpoint_store.path.exists():
                raise FileNotFoundError(checkpoint_store.path)
            report, pending, resume_snapshot = checkpoint_store.load_with_snapshot(
                policy, fingerprint
            )
            if resume_snapshot is not None:
                restore_snapshot = getattr(
                    self.manager, "restore_project_snapshot", None
                )
                if restore_snapshot is None:
                    raise RuntimeError(
                        "manager cannot restore the confirmed CST snapshot"
                    )
                restore_snapshot(resume_snapshot)
            pending = list(report.failed) + pending
            report.failed.clear()
            report.failure_reasons.clear()

        def save_checkpoint(current_report, current_pending):
            get_snapshot = getattr(self.manager, "get_confirmed_snapshot", None)
            snapshot = get_snapshot() if get_snapshot is not None else None
            checkpoint_store.save(
                policy,
                fingerprint,
                current_report,
                current_pending,
                snapshot_path=snapshot,
            )
            self._write_scan_results(current_report)

        def solve(request):
            values = [
                request.requested_modes,
                request.solve_lo,
                request.solve_hi,
            ]
            job_name = (
                f"hom_{request.interval.lo:g}_{request.interval.hi:g}"
            )
            result = self._execute_simulation(
                values,
                job_name,
                retry_count=1,
                continue_from_snapshot=True,
            )
            if result.get("TaskStatus") != "Success":
                reason = result.get("FailureReport", "unknown CST failure")
                raise RuntimeError(reason)
            postprocess = result.get("PostProcessResult")
            if not isinstance(postprocess, list):
                raise ValueError("CST task returned no postprocess result list")
            snapshot = result.get("ProjectSnapshot")
            if snapshot:
                snapshot = os.path.relpath(snapshot, self.manager.currProjectDir)
            return [replace(
                mode,
                project_snapshot=snapshot,
                task_name=result.get("RunName", job_name),
                task_id=result.get("TaskID", ""),
            ) for mode in self._extract_scan_modes(postprocess)]

        started = time.monotonic()
        try:
            final_report = scanner.run(
                solve,
                pending=pending,
                report=report,
                checkpoint=save_checkpoint,
                should_stop=lambda: bool(
                    getattr(self.manager, "stop_requested", False)
                ),
            )
            save_checkpoint(final_report, [])
            if final_report.failed:
                self.logger.warning(
                    "HOM_SCAN_COMPLETED_WITH_GAPS 扫描已结束，未确认区间=%d；已记录到检查点，可继续运行补算",
                    len(final_report.failed),
                )
            self.logger.info(
                "HOM scan completed: modes=%d intervals=%d solver_calls=%d elapsed=%.3fs",
                len(final_report.modes),
                len(final_report.completed),
                final_report.solver_calls,
                time.monotonic() - started,
            )
            return final_report
        except ScanInterrupted as exc:
            save_checkpoint(exc.report, exc.pending)
            self.logger.info(
                "HOM scan interrupted safely: modes=%d pending=%d solver_calls=%d",
                len(exc.report.modes),
                len(exc.pending),
                exc.report.solver_calls,
            )
            raise
        except IncompleteScanError as exc:
            for interval in exc.report.failed:
                self.logger.error(
                    "HOM_FAILED_INTERVAL lo=%.12g hi=%.12g reason=%s",
                    interval.lo, interval.hi,
                    exc.report.failure_reasons.get(
                        AdaptiveHomScanner._interval_key(interval), "unknown failure"
                    ),
                )
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
    from .postprocess_cst import VBPostProcessor
    from pathlib import Path

    vbp = VBPostProcessor()
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

