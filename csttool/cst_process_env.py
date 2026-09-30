"""Keep Python Qt test/plugin settings out of the external CST process."""
import os
from collections.abc import Mapping

PYTHON_QT_KEYS = frozenset({'QT_QPA_PLATFORM', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_PLUGIN_PATH'})


def cst_process_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy, never mutate the parent. Preserve licenses, PATH and other settings."""
    return {key: value for key, value in (os.environ if source is None else source).items()
            if key.upper() not in PYTHON_QT_KEYS}
