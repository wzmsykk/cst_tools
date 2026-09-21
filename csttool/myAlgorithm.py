"""Common algorithm contract used by CST application backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from .cstmanager import SimulationManager


class myAlg(ABC):
    """Base contract retained under its established public class name."""

    def __init__(self, manager=None, params=None) -> None:
        self.ready = False
        self.CSTparams = params
        self.manager = manager

    @abstractmethod
    def checkAndSetReady(self): ...

    @abstractmethod
    def setCSTParams(self, params: Sequence[Mapping[str, Any]]): ...

    @abstractmethod
    def setJobManager(self, manager: SimulationManager): ...

    @abstractmethod
    def setEditableAttrs(self, values: Mapping[str, Any]): ...

    @abstractmethod
    def getEditableAttrs(self) -> Mapping[str, Any]: ...

    @abstractmethod
    def start(self): ...

    def set_resume(self, resume: bool) -> None:
        if resume:
            raise NotImplementedError(
                f"{type(self).__name__} does not implement checkpoint resume"
            )
