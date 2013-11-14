# -*- coding: utf-8 -*-
# This file is part of the pyMor project (http://www.pymor.org).
# Copyright Holders: Felix Albrecht, Rene Milk, Stephan Rave
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from __future__ import absolute_import, division, print_function

from numbers import Number

import numpy as np
from scipy.sparse import issparse

from pymor.core.exceptions import CommunicationError
from pymor.core.interfaces import BasicInterface, abstractmethod, abstractproperty
from pymor.la.interfaces import VectorArrayInterface, Communicable
from pymor.tools import float_cmp


class NumpyVectorArray(VectorArrayInterface, Communicable):

    @classmethod
    def empty(cls, dim, reserve=0):
        va = cls(np.empty((0, 0)))
        va._array = np.empty((reserve, dim))
        va._len = 0
        return va

    @classmethod
    def zeros(cls, dim, count=1):
        return cls(np.zeros((count, dim)))

    def __init__(self, instance, dtype=None, copy=False, order=None, subok=False):
        if isinstance(instance, np.ndarray) and not copy:
            self._array = instance
        elif isinstance(instance, Communicable):
            self._array = instance.data
            if copy:
                self._array = self._array.copy()
        elif issparse(instance):
            self._array = np.array(instance.todense(), copy=False)
        else:
            self._array = np.array(instance, dtype=dtype, copy=copy, order=order, subok=subok, ndmin=2)
        if self._array.ndim != 2:
            assert self._array.ndim == 1
            self._array = np.reshape(self._array, (1,-1))
        self._len = len(self._array)

    def _data(self):
        return self._array[:self._len]

    def __len__(self):
        return self._len

    @property
    def dim(self):
        return self._array.shape[1]

    def copy(self, ind=None):
        assert self.check_ind(ind)

        if ind is None:
            return NumpyVectorArray(self._array[:self._len], copy=True)
        else:
            C = NumpyVectorArray(self._array[ind], copy=False)
            if not C._array.flags['OWNDATA']:
                C._array = np.array(C._array)
            return C

    def append(self, other, o_ind=None, remove_from_other=False):
        assert other.check_ind(o_ind)
        assert other is not self or not remove_from_other

        if o_ind is None:
            len_other = other._len
            if len_other <= self._array.shape[0] - self._len:
                self._array[self._len:self._len + len_other] = other._array
            else:
                self._array = np.vstack((self._array[:self._len], other._array[:len_other]))
            self._len += len_other
        else:
            if not hasattr(o_ind, '__len__'):
                len_other = 1
                o_ind = [o_ind]
            else:
                len_other = len(o_ind)
            if len_other <= self._array.shape[0] - self._len:
                other._array.take(o_ind, axis=0, out=self._array[self._len:self._len + len_other])
            else:
                self._array = np.append(self._array[:self._len], other._array[o_ind], axis=0)
            self._len += len_other
        if remove_from_other:
            other.remove(o_ind)

    def remove(self, ind=None):
        assert self.check_ind(ind)

        if ind is None:
            self._array = np.zeros((0, self.dim))
            self._len = 0
        else:
            if hasattr(ind, '__len__'):
                if len(ind) == 0:
                    return
                remaining = sorted(set(xrange(len(self))) - set(ind))
                self._array = self._array[remaining]
            else:
                assert -self._len < ind < self._len
                self._array = self._array[range(ind) + range(ind + 1, self._len)]
            self._len = self._array.shape[0]
        if not self._array.flags['OWNDATA']:
            self._array = self._array.copy()

    def replace(self, other, ind=None, o_ind=None, remove_from_other=False):
        assert self.check_ind(ind)
        assert other.check_ind(o_ind)
        assert self.dim == other.dim
        assert other is not self or not remove_from_other

        if ind is None:
            if o_ind is None:
                if other is self:
                    return
                assert other._len == self._len
                self._array = other._array[:other._len]
            else:
                if not hasattr(o_ind, '__len__'):
                    o_ind = [o_ind]
                assert self._len == len(o_ind)
                self._array = other._array[o_ind]
            self._len = self._array.shape[0]
        else:
            len_ind = self.len_ind(ind)
            other_array = np.array(self._array) if other is self else other._array
            if o_ind is None:
                assert len_ind == other._len
                self._array[ind] = other_array[:other._len]
            else:
                len_oind = other.len_ind(o_ind)
                assert len_ind == len_oind
                self._array[ind] = other_array[o_ind]
        assert self._array.flags['OWNDATA']

        if remove_from_other:
            other.remove(o_ind)

    def almost_equal(self, other, ind=None, o_ind=None, rtol=None, atol=None):
        assert self.check_ind(ind)
        assert other.check_ind(o_ind)
        assert self.dim == other.dim

        A = self._array[:self._len] if ind is None else \
                self._array[ind] if hasattr(ind, '__len__') else self._array[ind:ind + 1]
        B = other._array[:other._len] if o_ind is None else \
                other._array[o_ind] if hasattr(o_ind, '__len__') else other._array[o_ind:o_ind + 1]

        R = np.all(float_cmp(A, B, rtol=rtol, atol=atol), axis=1).squeeze()
        if R.ndim == 0:
            R = R[np.newaxis, ...]
        return R

    def scal(self, alpha, ind=None):
        assert self.check_ind(ind)

        if ind is None:
            self._array[:self._len] *= alpha
        else:
            self._array[ind] *= alpha

    def axpy(self, alpha, x, ind=None, x_ind=None):
        assert self.check_ind(ind)
        assert x.check_ind(x_ind)
        assert self.dim == x.dim

        if alpha == 0:
            return

        B = x._array[:x._len] if x_ind is None else x._array[x_ind]

        if alpha == 1:
            if ind is None:
                self._array[:self._len] += B
            else:
                self._array[ind] += B
        elif alpha == -1:
            if ind is None:
                self._array[:self._len] -= B
            else:
                self._array[ind] -= B
        else:
            if ind is None:
                self._array[:self._len] += B * alpha
            else:
                self._array[ind] += B * alpha

    def dot(self, other, pairwise, ind=None, o_ind=None):
        assert self.check_ind(ind)
        assert other.check_ind(o_ind)
        assert self.dim == other.dim

        A = self._array[:self._len] if ind is None else \
                self._array[ind] if hasattr(ind, '__len__') else self._array[ind:ind + 1]
        B = other._array[:other._len] if o_ind is None else \
                other._array[o_ind] if hasattr(o_ind, '__len__') else other._array[o_ind:o_ind + 1]

        if pairwise:
            return np.sum(A * B, axis=1)
        else:
            return A.dot(B.T)

    def lincomb(self, coefficients, ind=None):
        assert self.check_ind(ind)
        assert 1 <= coefficients.ndim <= 2

        if coefficients.ndim == 1:
            coefficients = coefficients[np.newaxis, ...]

        assert ind is None and coefficients.shape[1] == len(self) \
            or not hasattr(ind, '__len__') and coefficients.shape[1] == 1 \
            or hasattr(ind, '__len__') and coefficients.shape[1] == len(ind)

        if ind is None:
            return NumpyVectorArray(coefficients.dot(self._array[:self._len]), copy=False)
        elif hasattr(ind, '__len__'):
            return NumpyVectorArray(coefficients.dot(self._array[ind]), copy=False)
        else:
            return NumpyVectorArray(coefficients.dot(self._array[ind:ind + 1]), copy=False)

    def l1_norm(self, ind=None):
        assert self.check_ind(ind)

        A = self._array[:self._len] if ind is None else \
                self._array[ind] if hasattr(ind, '__len__') else self._array[ind:ind + 1]

        return np.sum(np.abs(A), axis=1)

    def l2_norm(self, ind=None):
        assert self.check_ind(ind)

        A = self._array[:self._len] if ind is None else \
                self._array[ind] if hasattr(ind, '__len__') else self._array[ind:ind + 1]

        return np.sum(np.power(A, 2), axis=1)**(1/2)

    def components(self, component_indices, ind=None):
        assert self.check_ind(ind)
        assert isinstance(component_indices, list) \
            or isinstance(component_indices, np.ndarray) and component_indices.ndim == 1

        if ind is None:
            return self._array[:self._len, component_indices]
        else:
            if not hasattr(ind, '__len__'):
                ind = [ind]
            return self._array[ind, component_indices]

    def amax(self, ind=None):
        assert self.check_ind(ind)

        A = self._array[:self._len] if ind is None else \
                self._array[ind] if hasattr(ind, '__len__') else self._array[ind:ind + 1]

        A = np.abs(A)
        max_ind = np.argmax(A, axis=1)
        max_val = A[np.arange(len(A)), max_ind]
        return (max_ind, max_val)

    def __str__(self):
        return self._array[:self._len].__str__()

    def __repr__(self):
        return 'NumpyVectorArray({})'.format(self._array[:self._len].__str__())