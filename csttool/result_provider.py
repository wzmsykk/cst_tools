"""Small provider-selection primitive independent of result physics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Hashable, Mapping, TypeVar


RequestT = TypeVar("RequestT", bound=Hashable)


class ResultProvider(str, Enum):
    NATIVE = "native"
    RUNTIME_VBA = "runtime-vba"


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    provider: ResultProvider
    native_key: str | None


def select_result_provider(
    request: RequestT,
    native_results: Mapping[RequestT, str],
) -> ProviderSelection:
    native_key = native_results.get(request)
    if native_key is not None:
        return ProviderSelection(ResultProvider.NATIVE, native_key)
    return ProviderSelection(ResultProvider.RUNTIME_VBA, None)
