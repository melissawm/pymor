# This file is part of the pyMor project (http://www.pymor.org).
# Copyright Holders: Felix Albrecht, Rene Milk, Stephan Rave
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

'''This module contains algorithms for extending a given basis by a new vector.

The methods are mainly designed to be used in conjunction with
:func:`pymor.algorithms.greedy.greedy`. Each method is of the form ::

    extension_algorithm(basis, U, ...)

and returns a tuple `new_basis, data` where new_basis holds the extened basis
and data is a dict contaning additional information about the extension
process. The `data` dict at least has the key `hierarchic` whose value signifies
if the new basis contains the old basis as its first vectors.

If the basis extension fails, e.g. because the new vector is not linearly
independent from the basis, a :class:`pymor.core.exceptions.ExtensionError` exception
is raised.
'''

from __future__ import absolute_import, division, print_function

import numpy as np

from pymor.core.exceptions import ExtensionError
from pymor.la import VectorArrayInterface, NumpyVectorArray
from pymor.la.gram_schmidt import gram_schmidt
from pymor.la.pod import pod
from pymor.operators import NumpyMatrixOperator
from pymor.tools import float_cmp_all


def trivial_basis_extension(basis, U, U_ind=None, copy_basis=True, copy_U=True):
    '''Trivially extend basis by just adding the new vector.

    We check that the new vector is not already contained in the basis, but we do
    not check for linear independence.

    Parameters
    ----------
    basis
        The basis to extend.
    U
        The new basis vector.
    U_ind
        Indices of the new basis vectors in U.
    copy_basis
        If copy_basis is False, the old basis is extended in-place.
    copy_U
        If copy_U is False, the new basis vectors are removed from U.

    Returns
    -------
    The new basis.

    Raises
    ------
    ExtensionError
        Is raised if U is already contained in basis.
    '''
    if basis is None:
        basis = type(U).empty(U.dim, reserve=len(U))

    if np.any(U.almost_equal(basis, ind=U_ind)):
        raise ExtensionError

    new_basis = basis.copy() if copy_basis else basis
    new_basis.append(U, o_ind=U_ind, remove_from_other=(not copy_U))

    return new_basis, {'hierarchic': True}


def numpy_trivial_basis_extension(basis, U):
    '''Trivially extend basis by just adding the new vector.

    We check that the new vector is not already contained in the basis, but we do
    not check for linear independence.

    Parameters
    ----------
    basis
        The basis to extend.
    U
        The new basis vector.

    Returns
    -------
    The new basis.

    Raises
    ------
    ExtensionError
        Is raised if U is already contained in basis.
    '''
    assert isinstance(U, NumpyVectorArray)
    if basis is None:
        return U, {'hierarchic': True}
    assert isinstance(basis, NumpyVectorArray)
    basis = basis.data
    U = U.data

    if not all(not float_cmp_all(B, U) for B in basis):
        raise ExtensionError

    new_basis = np.empty((basis.shape[0] + 1, basis.shape[1]))
    new_basis[:-1, :] = basis
    new_basis[-1, :] = U

    return NumpyVectorArray(new_basis), {'hierarchic': True}


def gram_schmidt_basis_extension(basis, U, U_ind=None, product=None, copy_basis=True, copy_U=True):
    '''Extend basis using Gram-Schmidt orthonormalization.

    Parameters
    ----------
    basis
        The basis to extend.
    U
        The new basis vectors.
    U_ind
        Indices of the new basis vectors in U.
    product
        The scalar product w.r.t. which to orthonormalize; if None, the l2-scalar
        product on the coefficient vector is used.
    copy_basis
        If copy_basis is False, the old basis is extended in-place.
    copy_U
        If copy_U is False, the new basis vectors are removed from U.

    Returns
    -------
    The new basis.

    Raises
    ------
    ExtensionError
        Gram-Schmidt orthonormalization fails. Usually this is the case when U
        is not linearily independent from the basis. However this can also happen
        due to rounding errors ...
    '''
    if basis is None:
        basis = type(U).empty(U.dim, reserve=len(U))

    basis_length = len(basis)

    new_basis = basis.copy() if copy_basis else basis
    new_basis.append(U, o_ind=U_ind, remove_from_other=(not copy_U))
    gram_schmidt(new_basis, offset=len(basis), product=product, copy=False)

    if len(new_basis) <= basis_length:
        raise ExtensionError

    return new_basis, {'hierarchic': True}


def pod_basis_extension(basis, U, count=1, copy_basis=True, product=None):
    '''Extend basis with the first `count` POD modes of the projection error of U

    Parameters
    ----------
    basis
        The basis to extend. The basis is expected to be orthonormal w.r.t. `product`.
    U
        The vectors to which the POD is applied.
    count
        Number of POD modes that are to be appended to the basis.
    product
        The scalar product w.r.t. which to orthonormalize; if None, the l2-scalar
        product on the coefficient vector is used.
    copy_basis
        If copy_basis is False, the old basis is extended in-place.

    Returns
    -------
    The new basis.

    Raises
    ------
    ExtensionError
        POD produces new vectors. Usually this is the case when U
        is not linearily independent from the basis. However this can also happen
        due to rounding errors ...
    '''
    if basis is None:
        return pod(U, modes=count, product=product), {'hierarchic': True}

    basis_length = len(basis)

    new_basis = basis.copy() if copy_basis else basis

    if product is None:
        U_proj_err = U - basis.lincomb(U.dot(basis, pairwise=False))
    else:
        U_proj_err = U - basis.lincomb(product.apply2(U, basis, pairwise=False))

    new_basis.append(pod(U_proj_err, modes=count, product=product))

    if len(new_basis) <= basis_length:
        raise ExtensionError

    return new_basis, {'hierarchic': True}