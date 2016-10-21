# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright 2013-2016 pyMOR developers and contributors. All rights reserved.
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

import numpy as np

from pymor.algorithms.gram_schmidt import gram_schmidt
from pymor.reductors.basic import reduce_generic_pg
from pymor.operators.constructions import VectorArrayOperator


def bt(discretization, r=None, tol=None, typ='lyap', me_solver=None, method='bfsr'):
    r"""Reduce using the Balanced Truncation method to order `r` or with tolerance `tol`.

    .. [A05]  A. C. Antoulas, Approximation of Large-Scale Dynamical
              Systems,
              SIAM, 2005.
    .. [MG91] D. Mustafa, K. Glover, Controller Reduction by
              :math:`\mathcal{H}_\infty`-Balanced Truncation,
              IEEE Transactions on Automatic Control, 36(6), 668-682, 1991.
    .. [OJ88] P. C. Opdenacker, E. A. Jonckheere, A Contraction Mapping
              Preserving Balanced Reduction Scheme and Its Infinity Norm
              Error Bounds,
              IEEE Transactions on Circuits and Systems, 35(2), 184-189,
              1988.

    Parameters
    ----------
    discretization
        The |LTISystem| which is to be reduced.
    r
        Order of the reduced model if `tol` is `None`, maximum order if
        `tol` is specified.
    tol
        Tolerance for the error bound if `r` is `None`.
    typ
        Type of the Gramian (see
        :func:`pymor.discretizations.iosys.LTISystem.compute_gramian`).
    me_solver
        Matrix equation solver to use (see
        :func:`pymor.algorithms.lyapunov.solve_lyap` or
        :func:`pymor.algorithms.riccati.solve_ricc`).
    method
        Projection method used:

        - `'sr'`: square root method
        - `'bfsr'`: balancing-free square root method

    Returns
    -------
    rom
        Reduced |LTISystem|.
    rc
        The reconstructor providing a `reconstruct(U)` method which
        reconstructs high-dimensional solutions from solutions `U` of the
        reduced |LTISystem|.
    reduction_data
        Dictionary of additional data produced by the reduction process.
        Contains projection matrices `V` and `W`.
    """
    assert r is not None or tol is not None
    assert r is None or 0 < r < discretization.n
    assert method in ('sr', 'bfsr')

    discretization.compute_sv_U_V(typ, me_solver=me_solver)

    if r is not None and r > min([len(discretization._gramian[typ]['cf']), len(discretization._gramian[typ]['of'])]):
        raise ValueError('r needs to be smaller than the sizes of Gramian factors.' +
                         ' Try reducing the tolerance in the low-rank Lyapunov equation solver.')

    if tol is not None:
        bounds = np.zeros((discretization.n,))
        sv = np.zeros((discretization.n,))
        len_sv = len(discretization._sv[typ])
        sv[:len_sv] = discretization._sv[typ]
        sv[len_sv:] = discretization._sv[typ][-1]
        sv_reverse = sv[-1:0:-1]
        if typ == 'lyap':
            bounds[:-1] = 2 * sv_reverse.cumsum()[::-1]
        elif typ == 'lqg':
            bounds[:-1] = 2 * (sv_reverse / np.sqrt(1 + sv_reverse ** 2)).cumsum()[::-1]
        elif isinstance(typ, tuple) and typ[0] == 'br':
            bounds[:-1] = 2 * typ[1] * sv_reverse.cumsum()[::-1]
        r_tol = np.argmax(bounds <= tol) + 1
        r = r_tol if r is None else min([r, r_tol])

    V = VectorArrayOperator(discretization._gramian[typ]['cf']).apply(discretization._V[typ], ind=list(range(r)))
    W = VectorArrayOperator(discretization._gramian[typ]['of']).apply(discretization._U[typ], ind=list(range(r)))

    if method == 'sr':
        alpha = 1 / np.sqrt(discretization._sv[typ][:r])
        V.scal(alpha)
        W.scal(alpha)
        rom, rc, _ = reduce_generic_pg(discretization, V, W, use_default=['E'])
    elif method == 'bfsr':
        V = gram_schmidt(V, atol=0, rtol=0)
        W = gram_schmidt(W, atol=0, rtol=0)
        rom, rc, _ = reduce_generic_pg(discretization, V, W)

    reduction_data = {'V': V, 'W': W}

    return rom, rc, reduction_data