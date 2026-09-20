"""Modern CLI entry point for the TM020 optimization algorithm."""

from base import run_backend
from csttool.nsgaii_TM020 import myAlg_nsga
from install_compat import resource_path


def main(argv=None) -> int:
    return run_backend(
        algorithm=myAlg_nsga(),
        postprocess_path=resource_path("data/TM020PPS.json"),
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
