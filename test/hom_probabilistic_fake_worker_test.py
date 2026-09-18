from pathlib import Path
import json

import pytest

from csttool.hom_scan import AdaptiveHomScanner, IncompleteScanError, ScanPolicy
from csttool.myAlgorithm_pop import myAlg01
from test.support.hom_fake_worker import (
    EmpiricalHomSpectrum,
    HomFakeOutcome,
    ProbabilisticHomWorker,
)


HOM_CSV_SAMPLE = Path(__file__).parent / "data" / "hom_threshold_classified_sample.csv"
DEFAULT_PPS = Path(__file__).parents[1] / "data" / "defaultPPS.json"


def solve_with(worker, algorithm):
    def solve(request):
        result = worker.runWithParam(
            f"fake_{request.solve_lo:g}_{request.solve_hi:g}",
            params={
                "nmodes": request.requested_modes,
                "fmin": request.solve_lo,
                "fmax": request.solve_hi,
            },
        )
        if result["TaskStatus"] != "Success":
            raise RuntimeError(result["FailureReport"])
        return algorithm._extract_scan_modes(result["PostProcessResult"])

    return solve


def test_fake_worker_scans_empty_windows_and_close_physical_modes():
    worker = ProbabilisticHomWorker(
        spectrum=(2.0, 2.00005, 17.0),
        scripted_outcomes=(
            HomFakeOutcome.NORMAL,
            HomFakeOutcome.NORMAL,
            HomFakeOutcome.EMPTY,
            HomFakeOutcome.EMPTY,
            HomFakeOutcome.NORMAL,
            HomFakeOutcome.EMPTY,
        ),
    )
    policy = ScanPolicy(0, 5, 20, window_width=5)

    report = AdaptiveHomScanner(policy).run(solve_with(worker, myAlg01()))

    assert [item.frequency for item in report.modes] == [2.0, 2.00005, 17.0]
    assert len(report.empty) == 3
    assert all(call[1]["nmodes"] == 1 for call in worker.calls)


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (HomFakeOutcome.TASK_FAILURE, "SIMULATED_SOLVER_FAILURE"),
        (HomFakeOutcome.OUT_OF_WINDOW, "outside the solve interval"),
        (HomFakeOutcome.NON_FINITE, "non-finite"),
        (HomFakeOutcome.MULTI_MODE, "exactly one value"),
    ],
)
def test_fake_worker_abnormal_outcomes_cannot_be_reported_complete(outcome, reason):
    worker = ProbabilisticHomWorker(
        spectrum=(2.0,),
        scripted_outcomes=(outcome,),
    )
    policy = ScanPolicy(0, 5, 5, max_interval_attempts=1)

    with pytest.raises(IncompleteScanError) as captured:
        AdaptiveHomScanner(policy).run(solve_with(worker, myAlg01()))

    assert reason in next(iter(captured.value.report.failure_reasons.values()))


def test_fake_worker_repeated_frequency_exercises_degeneracy_guard():
    worker = ProbabilisticHomWorker(
        spectrum=(2.0,),
        scripted_outcomes=(
            HomFakeOutcome.NORMAL,
            HomFakeOutcome.REPEAT_PREVIOUS,
        ),
    )
    policy = ScanPolicy(0, 5, 10, window_width=5, max_interval_attempts=1)

    with pytest.raises(IncompleteScanError) as captured:
        AdaptiveHomScanner(policy).run(solve_with(worker, myAlg01()))

    assert "degenerate" in next(iter(captured.value.report.failure_reasons.values()))


def test_probability_mix_is_seeded_and_exercises_all_configured_cases():
    probabilities = {
        HomFakeOutcome.EMPTY: 0.15,
        HomFakeOutcome.TASK_FAILURE: 0.15,
        HomFakeOutcome.REPEAT_PREVIOUS: 0.15,
        HomFakeOutcome.OUT_OF_WINDOW: 0.15,
        HomFakeOutcome.NON_FINITE: 0.15,
        HomFakeOutcome.MULTI_MODE: 0.15,
    }
    first = ProbabilisticHomWorker(
        spectrum=(2.0,), probabilities=probabilities, seed=20260919
    )
    second = ProbabilisticHomWorker(
        spectrum=(2.0,), probabilities=probabilities, seed=20260919
    )
    params = {"nmodes": 1, "fmin": 0, "fmax": 5}

    for index in range(100):
        first.runWithParam(str(index), params=params)
        second.runWithParam(str(index), params=params)

    assert [item[2] for item in first.calls] == [item[2] for item in second.calls]
    assert set(first.outcome_counts) == set(HomFakeOutcome)


def test_invalid_probability_configuration_is_rejected():
    with pytest.raises(ValueError, match="sum"):
        ProbabilisticHomWorker(
            probabilities={
                HomFakeOutcome.EMPTY: 0.6,
                HomFakeOutcome.TASK_FAILURE: 0.5,
            }
        )


def test_empirical_spectrum_loads_frequency_category_and_density():
    spectrum = EmpiricalHomSpectrum.from_csv(HOM_CSV_SAMPLE)

    assert len(spectrum.frequencies) == 8
    assert spectrum.frequency_range == pytest.approx(
        (911.815464937295, 1860.60021088335)
    )
    assert spectrum.mean_gap == pytest.approx(
        (1860.60021088335 - 911.815464937295) / 7
    )
    assert set(spectrum.categories) == {"longitudinal", "transverse"}
    assert spectrum.values[0]["Q-factor"] == pytest.approx(18.1974490544368)


def test_empirical_spectrum_can_filter_physical_category():
    spectrum = EmpiricalHomSpectrum.from_csv(
        HOM_CSV_SAMPLE, category="transverse"
    )

    assert spectrum.frequencies == pytest.approx(
        (943.61979442182, 1860.58776729986)
    )
    assert spectrum.categories == ("transverse",) * 2


def test_fake_worker_scans_real_csv_close_mode_spacing():
    worker = ProbabilisticHomWorker.from_csv(HOM_CSV_SAMPLE)
    policy = ScanPolicy(911.8, 931.8, 950, window_width=20)

    report = AdaptiveHomScanner(policy).run(solve_with(worker, myAlg01()))

    assert [item.frequency for item in report.modes] == pytest.approx(
        [
            911.815464937295,
            911.905358894828,
            943.566093539863,
            943.61979442182,
        ]
    )
    assert worker.spectrum_model.source == str(HOM_CSV_SAMPLE)


def test_fake_worker_returns_every_requested_default_hom_postprocess():
    settings = json.loads(DEFAULT_PPS.read_text(encoding="utf-8"))
    worker = ProbabilisticHomWorker.from_csv(
        HOM_CSV_SAMPLE,
        postprocess=settings,
    )

    result = worker.runWithParam(
        "all-postprocess",
        params={"nmodes": 1, "fmin": 911.8, "fmax": 912.0},
    )
    returned = {
        item["resultName"]: item["value"]
        for item in result["PostProcessResult"]
    }

    assert list(returned) == [item["resultName"] for item in settings]
    assert returned == pytest.approx(
        {
            "frequency": 911.815464937295,
            "R_divide_Q": 1.21790671001533e-07,
            "R_divide_Q_5mm": 0.493502635777098,
            "R_divide_Q_10mm": 1.99998909734014,
            "Shunt_Inpedence": 2.21627953085607e-06,
            "Total_Loss": 314714344.652206,
            "Q-factor": 18.1974490544368,
        }
    )


def test_fake_worker_maps_custom_result_names_by_method_and_offsets():
    worker = ProbabilisticHomWorker.from_csv(
        HOM_CSV_SAMPLE,
        postprocess=[
            {
                "resultName": "rq_at_5mm",
                "method": "R_over_Q",
                "params": {"iModeNumber": 1, "xoffset": 0, "yoffset": 5},
            },
            {
                "resultName": "quality",
                "method": "Q_Factor",
                "params": {"iModeNumber": 1},
            },
        ],
    )

    result = worker.runWithParam(
        "aliases",
        params={"nmodes": 1, "fmin": 911.8, "fmax": 912.0},
    )

    assert result["PostProcessResult"] == [
        {
            "resultName": "rq_at_5mm",
            "value": pytest.approx(0.493502635777098),
            "params": {"iModeNumber": 1, "xoffset": 0, "yoffset": 5},
        },
        {
            "resultName": "quality",
            "value": pytest.approx(18.1974490544368),
            "params": {"iModeNumber": 1},
        },
    ]


def test_fake_worker_rejects_postprocess_not_present_in_csv():
    with pytest.raises(ValueError, match="cannot satisfy.*unsupported"):
        ProbabilisticHomWorker.from_csv(
            HOM_CSV_SAMPLE,
            postprocess=[
                {
                    "resultName": "unsupported",
                    "method": "Loss_Surface",
                    "params": {"iModeNumber": 1},
                }
            ],
        )


def test_randomized_csv_model_is_seeded_and_preserves_spectrum_envelope():
    source = EmpiricalHomSpectrum.from_csv(HOM_CSV_SAMPLE)
    first = ProbabilisticHomWorker.from_csv_randomized(
        HOM_CSV_SAMPLE, model_seed=17
    )
    repeated = ProbabilisticHomWorker.from_csv_randomized(
        HOM_CSV_SAMPLE, model_seed=17
    )
    different = ProbabilisticHomWorker.from_csv_randomized(
        HOM_CSV_SAMPLE, model_seed=18
    )

    assert first.spectrum == repeated.spectrum
    assert first.spectrum != different.spectrum
    assert len(first.spectrum) == len(source.frequencies)
    assert first.spectrum[0] == source.frequencies[0]
    assert first.spectrum[-1] == source.frequencies[-1]
    assert all(left < right for left, right in zip(first.spectrum, first.spectrum[1:]))
    assert first.spectrum_model.mean_density == pytest.approx(source.mean_density)


def test_randomized_csv_model_returns_jointly_sampled_postprocess_row():
    settings = json.loads(DEFAULT_PPS.read_text(encoding="utf-8"))
    source = EmpiricalHomSpectrum.from_csv(HOM_CSV_SAMPLE)
    worker = ProbabilisticHomWorker.from_csv_randomized(
        HOM_CSV_SAMPLE,
        model_seed=20260919,
        postprocess=settings,
    )
    frequency = worker.spectrum[0]
    result = worker.runWithParam(
        "random-model",
        params={"nmodes": 1, "fmin": frequency, "fmax": frequency + 0.001},
    )
    returned = {
        item["resultName"]: item["value"]
        for item in result["PostProcessResult"]
    }

    source_rows = [
        tuple(row[name] for name in (
            "R_divide_Q",
            "R_divide_Q_5mm",
            "R_divide_Q_10mm",
            "Shunt_Inpedence",
            "Total_Loss",
            "Q-factor",
        ))
        for row in source.values
    ]
    returned_row = tuple(returned[name] for name in (
        "R_divide_Q",
        "R_divide_Q_5mm",
        "R_divide_Q_10mm",
        "Shunt_Inpedence",
        "Total_Loss",
        "Q-factor",
    ))
    assert returned["frequency"] == frequency
    assert returned_row in source_rows


@pytest.mark.parametrize("model_seed", [0, 1, 17, 20260919, 2**32 - 1])
def test_randomized_csv_worker_full_scan_finds_every_generated_mode(model_seed):
    settings = json.loads(DEFAULT_PPS.read_text(encoding="utf-8"))
    worker = ProbabilisticHomWorker.from_csv_randomized(
        HOM_CSV_SAMPLE,
        model_seed=model_seed,
        postprocess=settings,
    )
    start = worker.spectrum[0] - 0.1
    stop = worker.spectrum[-1] + 0.1
    policy = ScanPolicy(
        start,
        min(start + 20.0, stop),
        stop,
        window_width=20.0,
    )

    report = AdaptiveHomScanner(policy).run(solve_with(worker, myAlg01()))

    assert [item.frequency for item in report.modes] == pytest.approx(worker.spectrum)
    assert all(
        set(item.values) == {
            "frequency",
            "R_divide_Q",
            "R_divide_Q_5mm",
            "R_divide_Q_10mm",
            "Shunt_Inpedence",
            "Total_Loss",
            "Q-factor",
        }
        for item in report.modes
    )


def test_empirical_spectrum_rejects_missing_or_nonfinite_frequency(tmp_path):
    missing = tmp_path / "missing.csv"
    missing.write_text("category,value\nlongitudinal,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing column"):
        EmpiricalHomSpectrum.from_csv(missing)

    nonfinite = tmp_path / "nonfinite.csv"
    nonfinite.write_text("frequency\nnan\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        EmpiricalHomSpectrum.from_csv(nonfinite)
