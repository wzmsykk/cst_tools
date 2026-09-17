"""Backward-compatible command-line entry point.

Production GUI code uses :class:`csttool.application_backend.CstApplicationBackend`.
The historical class name remains here for scripts that still import ``base``.
"""

from csttool.application_backend import CstApplicationBackend


class cst_tools_main(CstApplicationBackend):
    """Deprecated compatibility alias for the pre-application-service API."""


def main() -> None:
    application = CstApplicationBackend()
    application.batchinit()
    application.setRunInfos()
    application.starttask()


if __name__ == "__main__":
    main()
