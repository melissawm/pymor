#!/usr/bin/env python
# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright 2013-2017 pyMOR developers and contributors. All rights reserved.
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

r"""1D heat equation demo

Discretization of the PDE:

.. math::
    :nowrap:

    \begin{align*}
        \partial_t z(x, t) &= \partial_{xx} z(x, t), & 0 < x < 1,\ t > 0 \\
        \partial_x z(0, t) &= z(0, t) - u(t), & t > 0 \\
        \partial_x z(1, t) &= -z(1, t), & t > 0 \\
        y(t) &= z(1, t), & t > 0
    \end{align*}

where :math:`u(t)` is the input and :math:`y(t)` is the output.
"""

from __future__ import absolute_import, division, print_function

import numpy as np
import scipy.sparse as sps
import matplotlib.pyplot as plt

from pymor.discretizations.iosys import LTISystem
from pymor.reductors.bt import BTReductor
from pymor.reductors.lti import IRKAReductor

import logging
logging.getLogger('pymor.algorithms.gram_schmidt.gram_schmidt').setLevel(logging.ERROR)

if __name__ == '__main__':
    # dimension of the system
    n = 100

    # assemble A, B, and C
    A = sps.diags([n * [-2 * (n - 1) ** 2],
                   (n - 1) * [(n - 1) ** 2],
                   (n - 1) * [(n - 1) ** 2]],
                  [0, -1, 1],
                  format='csc')
    A[0, 0] = -2 * n * (n - 1)
    A[0, 1] *= 2
    A[-1, -1] = -2 * n * (n - 1)
    A[-1, -2] *= 2

    B = np.zeros((n, 1))
    B[0, 0] = 2 * (n - 1)

    C = np.zeros((1, n))
    C[0, n - 1] = 1

    # LTI system
    lti = LTISystem.from_matrices(A, B, C)

    print('n = {}'.format(lti.n))
    print('m = {}'.format(lti.m))
    print('p = {}'.format(lti.p))

    # System poles
    poles = lti.poles(force_dense='True')
    fig, ax = plt.subplots()
    ax.plot(poles.real, poles.imag, '.')
    ax.set_title('System poles')
    plt.show()

    # Bode plot of the full model
    w = np.logspace(-2, 3, 100)
    fig, ax = LTISystem.mag_plot(lti, w=w)
    ax.set_title('Bode plot of the full model')
    plt.show()

    # Hankel singular values
    hsv = lti.hsv()
    fig, ax = plt.subplots()
    ax.semilogy(range(1, len(hsv) + 1), hsv, '.-')
    ax.set_title('Hankel singular values')
    plt.show()

    # Norms of the system
    print('H_2-norm of the full model:   {}'.format(lti.norm()))
    print('H_inf-norm of the full model: {}'.format(lti.norm('Hinf')))

    # Balanced Truncation
    r = 5
    reductor = BTReductor(lti)
    rom_bt = reductor.reduce(r, tol=1e-5)
    print('H_2-norm of the BT ROM:       {}'.format(rom_bt.norm()))
    print('H_inf-norm of the BT ROM:     {}'.format(rom_bt.norm('Hinf')))
    err_bt = lti - rom_bt
    print('H_2-error for the BT ROM:     {}'.format(err_bt.norm()))
    print('H_inf-error for the BT ROM:   {}'.format(err_bt.norm('Hinf')))

    # Bode plot of the full and BT reduced model
    fig, ax = LTISystem.mag_plot((lti, rom_bt), w=w)
    ax.set_title('Bode plot of the full and BT reduced model')
    plt.show()

    # Bode plot of the BT error system
    fig, ax = LTISystem.mag_plot(err_bt, w=w)
    ax.set_title('Bode plot of the BT error system')
    plt.show()

    # Iterative Rational Krylov Algorithm
    sigma = np.logspace(-1, 3, r)
    tol = 1e-4
    maxit = 100
    irka_reductor = IRKAReductor(lti)
    rom_irka = irka_reductor.reduce(r, sigma, tol=tol, maxit=maxit, compute_errors=True)

    # Shift distances
    fig, ax = plt.subplots()
    ax.semilogy(irka_reductor.dist, '.-')
    ax.set_title('Distances between shifts in IRKA iterations')
    plt.show()

    print('H_2-norm of the IRKA ROM:     {}'.format(rom_irka.norm()))
    print('H_inf-norm of the IRKA ROM:   {}'.format(rom_irka.norm('Hinf')))
    err_irka = lti - rom_irka
    print('H_2-error for the IRKA ROM:   {}'.format(err_irka.norm()))
    print('H_inf-error for the IRKA ROM: {}'.format(err_irka.norm('Hinf')))

    # Bode plot of the full and IRKA reduced model
    fig, ax = LTISystem.mag_plot((lti, rom_irka), w=w)
    ax.set_title('Bode plot of the full and IRKA reduced model')
    plt.show()

    # Bode plot of the IRKA error system
    fig, ax = LTISystem.mag_plot(err_irka, w=w)
    ax.set_title('Bode plot of the IRKA error system')
    plt.show()