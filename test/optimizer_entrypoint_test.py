"""Ensure optional CLI optimizers implement the application contract."""

import pytest

from csttool.nsgaii_TM020 import Tm020NsgaAlgorithm
from csttool.nsgaii_WTC import WtcNsgaAlgorithm


@pytest.mark.parametrize("algorithm_type", [Tm020NsgaAlgorithm, WtcNsgaAlgorithm])
def test_optimizer_configuration_roundtrip_and_atomic_validation(algorithm_type):
    algorithm = algorithm_type()
    algorithm.set_editable_attributes({"mesh_cells_per_wavelength": 25})
    previous = algorithm.get_editable_attributes()
    assert previous["mesh_cells_per_wavelength"] == 25
    with pytest.raises(ValueError):
        algorithm.set_editable_attributes({"generations": 0})
    assert algorithm.get_editable_attributes() == previous
    with pytest.raises(ValueError, match="Unsupported"):
        algorithm.set_editable_attributes({"misspelled_setting": 1})
