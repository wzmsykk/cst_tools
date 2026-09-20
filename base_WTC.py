"""Modern CLI entry point for the WTC optimization algorithm."""

from base import run_backend
from csttool.nsgaii_WTC import myAlg_nsga
from install_compat import resource_path


def main(argv=None) -> int:
    return run_backend(
        algorithm=myAlg_nsga(),
        postprocess_path=resource_path("data/WTCPPS.json"),
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
