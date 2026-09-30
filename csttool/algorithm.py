"""Common algorithm contract used by CST application backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from .cstmanager import SimulationManager


class Algorithm(ABC):
    """Typed algorithm contract consumed by the application backend."""

    def __init__(self, manager=None, params=None) -> None:
        self.ready = False
        self.CSTparams = params
        self.manager = manager

    @abstractmethod
    def check_and_set_ready(self): ...

    @abstractmethod
    def set_cst_parameters(self, params: Sequence[Mapping[str, Any]]): ...

    @abstractmethod
    def set_job_manager(self, manager: SimulationManager): ...

    @abstractmethod
    def set_editable_attributes(self, values: Mapping[str, Any]): ...

    @abstractmethod
    def get_editable_attributes(self) -> Mapping[str, Any]: ...

    @abstractmethod
    def start(self): ...

    def set_resume(self, resume: bool) -> None:
        if resume:
            raise NotImplementedError(
                f"{type(self).__name__} does not implement checkpoint resume"
            )
