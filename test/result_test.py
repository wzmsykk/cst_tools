from csttool.result import readModeResult


def write_cst_scalar(path, value):
    path.write_text(f"header\nheader\nvalue {value}\n", encoding="utf-8")


def test_read_mode_result(tmp_path):
    values = {
        "Frequency": 500.25,
        "R_Q": 100.5,
        "ShuntImpedance": 200.75,
        "Q-Factor": 30000.0,
        "Voltage": 4.5,
        "TotalLoss": 0.125,
    }
    for suffix, value in values.items():
        write_cst_scalar(tmp_path / f"Mode2{suffix}.txt", value)

    assert readModeResult(tmp_path, 2) == tuple(values.values())
