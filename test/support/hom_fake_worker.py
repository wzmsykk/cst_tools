"""Reproducible probabilistic CST Worker for HOM scan tests."""

from __future__ import annotations

from collections import Counter, deque
import csv
from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
import random
from typing import Iterable, Mapping


class HomFakeOutcome(str, Enum):
    NORMAL = "normal"
    EMPTY = "empty"
    TASK_FAILURE = "task-failure"
    REPEAT_PREVIOUS = "repeat-previous"
    OUT_OF_WINDOW = "out-of-window"
    NON_FINITE = "non-finite"
    MULTI_MODE = "multi-mode"


@dataclass(frozen=True)
class EmpiricalHomSpectrum:
    """A frequency spectrum loaded from CST-derived HOM CSV output."""

    frequencies: tuple[float, ...]
    categories: tuple[str | None, ...]
    values: tuple[dict[str, float], ...]
    source: str

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        frequency_column: str = "frequency",
        category_column: str = "category",
        category: str | None = None,
    ) -> "EmpiricalHomSpectrum":
        path = Path(path)
        records = []
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or frequency_column not in reader.fieldnames:
                raise ValueError(
                    f"HOM spectrum CSV is missing column {frequency_column!r}"
                )
            has_category = category_column in reader.fieldnames
            if category is not None and not has_category:
                raise ValueError(
                    f"HOM spectrum CSV is missing column {category_column!r}"
                )
            for line_number, row in enumerate(reader, start=2):
                row_category = row.get(category_column) if has_category else None
                if category is not None and row_category != category:
                    continue
                try:
                    frequency = float(row[frequency_column])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"invalid HOM frequency at {path}:{line_number}"
                    ) from exc
                if not math.isfinite(frequency):
                    raise ValueError(
                        f"non-finite HOM frequency at {path}:{line_number}"
                    )
                numeric_values = {}
                for name, raw_value in row.items():
                    if not name or raw_value in (None, ""):
                        continue
                    try:
                        value = float(raw_value)
                    except ValueError:
                        continue
                    if not math.isfinite(value):
                        raise ValueError(
                            f"non-finite value in column {name!r} at "
                            f"{path}:{line_number}"
                        )
                    numeric_values[name] = value
                numeric_values[frequency_column] = frequency
                records.append((frequency, row_category, numeric_values))
        if not records:
            suffix = f" for category {category!r}" if category is not None else ""
            raise ValueError(f"HOM spectrum CSV contains no modes{suffix}")
        records.sort(key=lambda item: item[0])
        return cls(
            frequencies=tuple(item[0] for item in records),
            categories=tuple(item[1] for item in records),
            values=tuple(item[2] for item in records),
            source=str(path),
        )

    @property
    def frequency_range(self) -> tuple[float, float]:
        return self.frequencies[0], self.frequencies[-1]

    @property
    def mean_gap(self) -> float:
        if len(self.frequencies) < 2:
            return math.inf
        lo, hi = self.frequency_range
        return (hi - lo) / (len(self.frequencies) - 1)

    @property
    def mean_density(self) -> float:
        gap = self.mean_gap
        return 0.0 if math.isinf(gap) else 1.0 / gap

    def resample(self, *, seed: int) -> "EmpiricalHomSpectrum":
        """Bootstrap a spectrum with the same count, range and empirical shapes."""

        if len(self.frequencies) < 2:
            return self
        rng = random.Random(seed)
        source_gaps = [
            right - left
            for left, right in zip(self.frequencies, self.frequencies[1:])
        ]
        sampled_gaps = rng.choices(source_gaps, k=len(source_gaps))
        source_span = self.frequencies[-1] - self.frequencies[0]
        sampled_span = sum(sampled_gaps)
        scale = source_span / sampled_span
        frequencies = [self.frequencies[0]]
        for gap in sampled_gaps[:-1]:
            frequencies.append(frequencies[-1] + gap * scale)
        frequencies.append(self.frequencies[-1])

        sampled_indices = [rng.randrange(len(self.values)) for _ in frequencies]
        values = []
        categories = []
        for frequency, index in zip(frequencies, sampled_indices):
            row = dict(self.values[index])
            row["frequency"] = frequency
            values.append(row)
            categories.append(self.categories[index])
        return EmpiricalHomSpectrum(
            frequencies=tuple(frequencies),
            categories=tuple(categories),
            values=tuple(values),
            source=f"{self.source}#bootstrap-seed={seed}",
        )


class ProbabilisticHomWorker:
    """Model a fixed spectrum plus probabilistic CST/protocol edge cases."""

    def __init__(
        self,
        worker_id: str = "hom-fake",
        *,
        spectrum: Iterable[float] = (),
        probabilities: Mapping[HomFakeOutcome | str, float] | None = None,
        seed: int = 0,
        scripted_outcomes: Iterable[HomFakeOutcome | str] = (),
        postprocess: Iterable[Mapping] | None = None,
        mode_values: Mapping[float, Mapping[str, float]] | None = None,
    ):
        self.ID = worker_id
        self.spectrum = tuple(sorted(float(value) for value in spectrum))
        self._rng = random.Random(seed)
        self._scripted = deque(HomFakeOutcome(item) for item in scripted_outcomes)
        self._probabilities = self._validate_probabilities(probabilities or {})
        self.postprocess = tuple(dict(item) for item in postprocess or ())
        self._mode_values = {
            float(frequency): dict(values)
            for frequency, values in (mode_values or {}).items()
        }
        self.outcome_counts = Counter()
        self.calls = []
        self.previous_frequency = None
        self.stopped = False

    @classmethod
    def from_csv(cls, path: str | Path, **kwargs):
        """Build a Worker from a CST-derived frequency/category CSV."""

        loader_keys = {"frequency_column", "category_column", "category"}
        loader_kwargs = {
            key: kwargs.pop(key) for key in tuple(kwargs) if key in loader_keys
        }
        model = EmpiricalHomSpectrum.from_csv(path, **loader_kwargs)
        worker = cls(
            spectrum=model.frequencies,
            mode_values=dict(zip(model.frequencies, model.values)),
            **kwargs,
        )
        worker.spectrum_model = model
        worker._validate_requested_postprocess()
        return worker

    @classmethod
    def from_csv_randomized(
        cls,
        path: str | Path,
        *,
        model_seed: int,
        **kwargs,
    ):
        """Build a deterministic empirical-bootstrap Worker from CSV."""

        loader_keys = {"frequency_column", "category_column", "category"}
        loader_kwargs = {
            key: kwargs.pop(key) for key in tuple(kwargs) if key in loader_keys
        }
        model = EmpiricalHomSpectrum.from_csv(path, **loader_kwargs).resample(
            seed=model_seed
        )
        worker = cls(
            spectrum=model.frequencies,
            mode_values=dict(zip(model.frequencies, model.values)),
            **kwargs,
        )
        worker.spectrum_model = model
        worker._validate_requested_postprocess()
        return worker

    def _validate_requested_postprocess(self):
        if not self.postprocess or not self._mode_values:
            return
        available = set.intersection(
            *(set(values) for values in self._mode_values.values())
        )
        missing = [
            item.get("resultName")
            for item in self.postprocess
            if self._source_column(item) not in available
        ]
        if missing:
            raise ValueError(
                "HOM spectrum CSV cannot satisfy postprocess results: "
                + ", ".join(repr(item) for item in missing)
            )

    @staticmethod
    def _source_column(setting):
        result_name = setting.get("resultName")
        method = setting.get("method")
        params = setting.get("params") or {}
        if method == "Frequency":
            return "frequency"
        if method == "Q_Factor":
            return "Q-factor"
        if method == "Total_Loss":
            return "Total_Loss"
        if method == "Shunt_Inpedence":
            return "Shunt_Inpedence"
        if method == "R_over_Q":
            offsets = [
                abs(float(params.get(name, 0.0)))
                for name in ("xoffset", "yoffset", "zoffset")
            ]
            offset = max(offsets)
            if math.isclose(offset, 0.0, abs_tol=1e-12):
                return "R_divide_Q"
            if math.isclose(offset, 5.0, abs_tol=1e-12):
                return "R_divide_Q_5mm"
            if math.isclose(offset, 10.0, abs_tol=1e-12):
                return "R_divide_Q_10mm"
        return result_name

    def _normal_postprocess(self, frequency):
        values = self._mode_values.get(frequency)
        if values is None:
            values = {"frequency": frequency, "Q-factor": 1000.0}
        if self.postprocess:
            results = []
            for setting in self.postprocess:
                source = self._source_column(setting)
                results.append(
                    {
                        "resultName": setting["resultName"],
                        "value": values[source],
                        "params": dict(setting.get("params") or {}),
                    }
                )
            return results
        preferred = (
            "frequency",
            "R_divide_Q",
            "R_divide_Q_5mm",
            "R_divide_Q_10mm",
            "Q-factor",
            "Shunt_Inpedence",
            "Total_Loss",
        )
        return [
            {
                "resultName": name,
                "value": values[name],
                "params": {"iModeNumber": 1},
            }
            for name in preferred
            if name in values
        ]

    @staticmethod
    def _validate_probabilities(values):
        normalized = {HomFakeOutcome(key): float(value) for key, value in values.items()}
        if any(value < 0 for value in normalized.values()):
            raise ValueError("HOM fake outcome probabilities must be non-negative")
        total = sum(normalized.values())
        if total > 1:
            raise ValueError("HOM fake outcome probabilities must sum to at most 1")
        normalized[HomFakeOutcome.NORMAL] = (
            normalized.get(HomFakeOutcome.NORMAL, 0.0) + 1.0 - total
        )
        return normalized

    def _next_outcome(self):
        if self._scripted:
            return self._scripted.popleft()
        outcomes = tuple(self._probabilities)
        weights = tuple(self._probabilities[item] for item in outcomes)
        return self._rng.choices(outcomes, weights=weights, k=1)[0]

    def runWithParam(self, resultname, *, params):
        params = dict(params)
        lo = float(params["fmin"])
        hi = float(params["fmax"])
        if int(params.get("nmodes", 1)) != 1:
            raise AssertionError("HOM fake Worker expects the single-mode protocol")
        outcome = self._next_outcome()
        self.outcome_counts[outcome] += 1
        self.calls.append((resultname, params, outcome))

        if outcome is HomFakeOutcome.TASK_FAILURE:
            return self._result(
                resultname,
                params,
                status="Failure",
                failure="SIMULATED_SOLVER_FAILURE",
            )
        if outcome is HomFakeOutcome.EMPTY:
            return self._result(resultname, params, postprocess=[])

        in_window = [value for value in self.spectrum if lo <= value <= hi]
        physical = in_window[0] if in_window else None
        if outcome is HomFakeOutcome.NORMAL:
            if physical is None:
                return self._result(resultname, params, postprocess=[])
            frequency = physical
        elif outcome is HomFakeOutcome.REPEAT_PREVIOUS:
            frequency = self.previous_frequency if self.previous_frequency is not None else lo
        elif outcome is HomFakeOutcome.OUT_OF_WINDOW:
            frequency = hi + max(1.0, hi - lo)
        elif outcome is HomFakeOutcome.NON_FINITE:
            frequency = float("nan")
        elif outcome is HomFakeOutcome.MULTI_MODE:
            first = physical if physical is not None else lo
            return self._result(
                resultname,
                params,
                postprocess=[
                    {
                        "resultName": "frequency",
                        "value": {"ModeIndex 1": first, "ModeIndex 2": first + 0.001},
                    },
                    {
                        "resultName": "Q-factor",
                        "value": {"ModeIndex 1": 1000.0, "ModeIndex 2": 1001.0},
                    },
                ],
            )
        else:
            raise AssertionError(outcome)

        self.previous_frequency = frequency
        return self._result(
            resultname,
            params,
            postprocess=self._normal_postprocess(frequency),
        )

    def _result(
        self,
        resultname,
        params,
        *,
        status="Success",
        failure=None,
        postprocess=None,
    ):
        return {
            "WorkerID": self.ID,
            "TaskStatus": status,
            "FailureReport": failure,
            "RunName": resultname,
            "RunParameters": params,
            "PostProcessResult": postprocess,
        }

    def stop(self):
        self.stopped = True
        return True
