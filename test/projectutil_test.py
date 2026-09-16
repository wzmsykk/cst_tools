import json

import pytest

from csttool.projectutil import (
    convert_cst_parameters_to_legacy,
    convert_json_params_to_list,
    custom_ascii_2_json,
    getParamsList,
    is_number,
)


def test_convert_cst_parameters_preserves_expression_and_value():
    converted = convert_cst_parameters_to_legacy([
        {"name": "C1", "expr": "L/2", "value": "750", "descr": "derived length"},
        {"name": "L", "expr": "1500", "value": "1500", "descr": "base length"},
    ])

    assert converted[0] == {
        "id": 0,
        "name": "C1",
        "value": "L/2",
        "type": "expression",
        "fixed": True,
        "description": "derived length",
        "expr": "L/2",
        "evaluated_value": "750",
    }
    assert converted[1]["value"] == "1500"
    assert converted[1]["fixed"] is False
    assert converted[1]["evaluated_value"] == "1500"


def test_convert_cst_parameters_rejects_duplicate_names():
    with pytest.raises(ValueError, match="duplicate CST parameter"):
        convert_cst_parameters_to_legacy([
            {"name": "L", "expr": "1", "value": "1"},
            {"name": "L", "expr": "2", "value": "2"},
        ])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("-3.5", True),
        ("1e-4", True),
        ("三", True),
        ("radius + 1", False),
        (None, False),
    ],
)
def test_is_number(value, expected):
    assert is_number(value) is expected


def test_ascii_parameter_conversion_round_trip(tmp_path):
    source = tmp_path / "params.txt"
    destination = tmp_path / "params.json"
    source.write_text(
        "header\nheader\n2\n0 radius 12.5 cavity_radius\n1 length radius*2 derived\n",
        encoding="utf-8",
    )

    custom_ascii_2_json(source, destination)

    params = getParamsList(destination)
    assert params == [
        {
            "id": 0,
            "name": "radius",
            "value": "12.5",
            "type": "double",
            "fixed": False,
            "description": "cavity_radius",
        },
        {
            "id": 1,
            "name": "length",
            "value": "radius*2",
            "type": "expression",
            "fixed": True,
            "description": "derived",
        },
    ]
    assert convert_json_params_to_list(params) == [12.5]
    assert json.loads(destination.read_text(encoding="utf-8")) == params
