"""Backward-compatible CLI and API facade for historical callers."""

from __future__ import annotations

import argparse

from csttool.application_backend import (
    BackendInitializationError,
    BackendPreparationError,
    CstApplicationBackend,
)


class cst_tools_main(CstApplicationBackend):
    """Deprecated camelCase facade; new code must use CstApplicationBackend."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ctn = False
        self.safe = False

    def setProjectDir(self, path):
        return self.select_project_directory(path)

    def getProjectDir(self):
        return self.get_project_directory()

    def setCSTFilePath(self, path):
        return self.select_cst_file(path)

    def getCSTFilePath(self):
        return self.get_cst_file()

    def setFlags(self, startFromExisted, safe):
        self.ctn = bool(startFromExisted)
        self.safe = bool(safe)

    def setWorkerCount(self, worker_count):
        worker_count = int(worker_count)
        if worker_count < 1:
            raise ValueError("worker_count must be at least 1")
        self.worker_count = worker_count

    def setCurrPostProcessList(self, values):
        return self.update_postprocess_settings(values)

    def getCurrPostProcessList(self):
        return self.get_postprocess_settings()

    def readPostProcessListFromFile(self, path):
        return self.read_postprocess_settings(path)

    def getAlgAttrs(self):
        return self.get_algorithm_settings()

    def setAlgAttrs(self, values):
        return self.update_algorithm_settings(values)

    def wininit(self):
        try:
            self.initialize_run(self.ctn, self.safe, self.worker_count)
        except BackendInitializationError:
            return False
        return True

    def setRunInfos(self):
        try:
            self.prepare_run()
        except BackendPreparationError:
            return 0
        return None

    def createJobManager(self):
        return self._create_manager()

    def starttask(self):
        return self.execute_run()

    def batchinit(self, argv=None):
        parser = _build_parser()
        args = parser.parse_args(argv)
        self.setProjectDir(args.projectdir)
        self.setCSTFilePath(args.cstfilepath)
        self.setFlags(args.ctn, args.safe)
        if not self.wininit():
            return 0
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="python cst project.")
    parser.add_argument("-p", "--projectdir", help="project目录")
    parser.add_argument("-f", "--cstfilepath", help="输入CST文件路径")
    parser.add_argument("-c", "--continue", action="store_true", dest="ctn")
    parser.add_argument("-s", "--safe", action="store_true", dest="safe")
    return parser


def main(argv=None) -> int:
    application = cst_tools_main()
    if application.batchinit(argv) == 0:
        return 1
    if application.setRunInfos() == 0:
        return 1
    application.starttask()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
