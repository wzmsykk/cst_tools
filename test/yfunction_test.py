import numpy as np

from csttool.yfunction import myYFunc00, yfunc


def test_quadratic_objective_and_gradient():
    objective = myYFunc00()
    point = np.array([1.5, -2.0, 0.5])

    assert objective.Y(point) == 6.5
    np.testing.assert_array_equal(objective.pGrad(point), [3.0, -4.0, 1.0])


def test_yfunc_delegates_to_selected_objective():
    objective = yfunc(myYFunc00)

    assert objective.Y([3.0, 4.0]) == 25.0
    np.testing.assert_array_equal(objective.pGrad([3.0, 4.0]), [6.0, 8.0])
