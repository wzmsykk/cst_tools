import json

import pytest

from csttool.mesh_convergence import (
    MeshConvergenceAnalyzer,
    MeshConvergenceSettings,
    scalar_postprocess_values,
)


def test_analyzer_stops_after_two_consecutive_stable_mesh_levels(tmp_path):
    samples = {
        10: {"Frequency": 100.0, "R_over_Q": 50.0},
        15: {"Frequency": 100.5, "R_over_Q": 50.4},
        20: {"Frequency": 100.6, "R_over_Q": 50.5},
        25: {"Frequency": 100.65, "R_over_Q": 50.52},
        30: {"Frequency": 200.0, "R_over_Q": 80.0},
    }
    settings = MeshConvergenceSettings(
        enabled=True, start=10, stop=30, step=5, tolerance=0.01
    )

    report = MeshConvergenceAnalyzer(settings).run(samples.__getitem__)
    json_path, csv_path = report.write(tmp_path)

    assert report.converged is True
    assert report.recommended_cells_per_wavelength == 20
    assert [point.cells_per_wavelength for point in report.points] == [10, 15, 20]
    assert json.loads(json_path.read_text(encoding="utf-8"))["converged"] is True
    assert "relative_change:R_over_Q" in csv_path.read_text(encoding="utf-8-sig")


def test_analyzer_reports_non_convergence_at_configured_limit():
    settings = MeshConvergenceSettings(
        enabled=True, start=10, stop=20, step=5, tolerance=0.001
    )

    report = MeshConvergenceAnalyzer(settings).run(
        lambda level: {"Frequency": float(level)}
    )

    assert report.converged is False
    assert report.recommended_cells_per_wavelength is None
    assert len(report.points) == 3


def test_scalar_postprocess_values_accepts_single_mode_maps_only():
    values = scalar_postprocess_values(
        {
            "PostProcessResult": [
                {"resultName": "Frequency", "value": {"1": 500.0}},
                {"resultName": "R_over_Q", "value": 42.0},
            ]
        }
    )
    assert values == {"Frequency": 500.0, "R_over_Q": 42.0}

    with pytest.raises(ValueError, match="单模标量"):
        scalar_postprocess_values(
            {
                "PostProcessResult": [
                    {"resultName": "Frequency", "value": {"1": 500, "2": 600}}
                ]
            }
        )
