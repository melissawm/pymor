# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright 2013-2017 pyMOR developers and contributors. All rights reserved.
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from pymor.grids.oned import OnedGrid
from time import sleep
from pymor.gui.qt import visualize_patch, stop_gui_processes

import pytest
import numpy as np
from pymor.analyticalproblems.elliptic import StationaryProblem
from pymor.discretizers.cg import discretize_stationary_cg
from pymor.domaindiscretizers.default import discretize_domain_default
from pymor.grids.rect import RectGrid
from pymor.core.exceptions import QtMissing

from pymortests.base import runmodule
from pymor.domaindescriptions.basic import RectDomain, LineDomain
from pymor.functions.basic import GenericFunction


@pytest.fixture(params=(('matplotlib', RectGrid), ('gl', RectGrid), ('matplotlib', OnedGrid)))
def backend_gridtype(request):
    return request.param


def test_visualize_patch(backend_gridtype):
    backend, gridtype = backend_gridtype
    domain = LineDomain() if gridtype is OnedGrid else RectDomain()
    dim = 1 if gridtype is OnedGrid else 2
    rhs = GenericFunction(lambda X: np.ones(X.shape[:-1]) * 10, dim)  # NOQA
    dirichlet = GenericFunction(lambda X: np.zeros(X.shape[:-1]), dim)  # NOQA
    diffusion = GenericFunction(lambda X: np.ones(X.shape[:-1]), dim)  # NOQA
    problem = StationaryProblem(domain=domain, rhs=rhs, dirichlet_data=dirichlet, diffusion=diffusion)
    grid, bi = discretize_domain_default(problem.domain, grid_type=gridtype)
    d, data = discretize_stationary_cg(analytical_problem=problem, grid=grid, boundary_info=bi)
    U = d.solve()
    try:
        visualize_patch(data['grid'], U=U, backend=backend)
    except QtMissing as ie:
        pytest.xfail("Qt missing")
    finally:
        stop_gui_processes()


if __name__ == "__main__":
    runmodule(filename=__file__)
