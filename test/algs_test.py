from math import inf

import numpy as np

from algs.nsga.nsgaii_np import nsgaii, nsgaii_var
from algs.nsga.zdts import zdt1, zdt2, zdt4


def make_var(objectives):
    var = nsgaii_var([0.0] * len(objectives))
    var.setObjs(objectives)
    return var


def test_zdt_reference_points():
    assert zdt1(nofdvs=3)([0.25, 0.0, 0.0]) == (0.25, 0.5)
    assert zdt2(nofdvs=3)([0.5, 0.0, 0.0]) == (0.5, 0.75)
    assert zdt4(nofdvs=3)([0.25, 0.0, 0.0]) == (0.25, 0.5)


def test_dominance_requires_no_worse_objectives_and_one_better():
    best = make_var([1.0, 2.0])
    worse = make_var([2.0, 2.0])
    tradeoff = make_var([0.5, 3.0])

    assert best.dom(worse)
    assert not worse.dom(best)
    assert not best.dom(tradeoff)


def test_fast_non_dominated_sort_assigns_fronts():
    engine = nsgaii()
    first_a = make_var([1.0, 3.0])
    first_b = make_var([2.0, 2.0])
    first_c = make_var([3.0, 1.0])
    dominated = make_var([3.0, 3.0])

    fronts = engine.fnds([first_a, first_b, first_c, dominated])

    assert set(fronts[0]) == {first_a, first_b, first_c}
    assert fronts[1] == [dominated]
    assert {var.rank for var in fronts[0]} == {1}
    assert dominated.rank == 2


def test_crowding_distance_preserves_boundary_points():
    engine = nsgaii()
    front = [make_var([0.0, 1.0]), make_var([0.5, 0.5]), make_var([1.0, 0.0])]

    engine.crowding_dis_assign(front)

    assert front[0].crowed_dis == inf
    assert front[2].crowed_dis == inf
    assert np.isclose(front[1].crowed_dis, 2.0)
