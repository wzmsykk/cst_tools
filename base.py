"""Command-line entry point for the production CST application backend."""

from __future__ import annotations

import argparse

from csttool.application_backend import CstApplicationBackend


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a CST Tools project")
    parser.add_argument("-p", "--projectdir", required=True)
    parser.add_argument("-f", "--cstfilepath")
    parser.add_argument("-c", "--resume", action="store_true")
    parser.add_argument("-j", "--workers", type=int, default=1)
    return parser


def run_backend(*, algorithm=None, postprocess_path=None, argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.resume and not args.cstfilepath:
        raise SystemExit("--cstfilepath is required for a new run")

    application = CstApplicationBackend(algorithm=algorithm)
    if postprocess_path is not None:
        application.update_postprocess_settings(
            application.read_postprocess_settings(postprocess_path)
        )
    application.select_project_directory(args.projectdir)
    if args.cstfilepath:
        application.select_cst_file(args.cstfilepath)
    application.initialize_run(args.resume, args.workers)
    application.prepare_run()
    application.execute_run()
    return 0


def main(argv=None) -> int:
    return run_backend(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
