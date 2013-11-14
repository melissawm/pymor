# -*- coding: utf-8 -*-
# This file is part of the pyMor project (http://www.pymor.org).
# Copyright Holders: Felix Albrecht, Rene Milk, Stephan Rave
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from __future__ import absolute_import, division, print_function

from itertools import izip
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix, diags

from pymor.core import ImmutableInterface, abstractmethod
from pymor.functions import FunctionInterface
from pymor.grids.boundaryinfos import SubGridBoundaryInfo
from pymor.grids.referenceelements import triangle, line
from pymor.grids.subgrid import SubGrid
from pymor.la import NumpyVectorArray
from pymor.operators import OperatorBase, NumpyMatrixBasedOperator, NumpyMatrixOperator
from pymor.operators.constructions import Concatenation, ComponentProjection
from pymor.parameters import Parametric
from pymor.tools import method_arguments
from pymor.tools.inplace import iadd_masked, isub_masked
from pymor.tools.quadratures import GaussQuadratures


class NumericalConvectiveFlux(ImmutableInterface, Parametric):

    @abstractmethod
    def evaluate_stage1(self, U, mu=None):
        pass

    @abstractmethod
    def evaluate_stage2(self, stage1_data, unit_outer_normals, volumes, mu=None):
        pass


class LaxFriedrichsFlux(NumericalConvectiveFlux):

    def __init__(self, flux, lxf_lambda=1.0):
        self.flux = flux
        self.lxf_lambda = lxf_lambda
        self.build_parameter_type(inherits=(flux,))

    def evaluate_stage1(self, U, mu=None):
        return U, self.flux(U[..., np.newaxis], mu)

    def evaluate_stage2(self, stage1_data, unit_outer_normals, volumes, mu=None):
        U, F = stage1_data
        return (np.sum(np.sum(F, axis=1) * unit_outer_normals, axis=1) * 0.5
                + (U[..., 0] - U[..., 1]) * (0.5 / self.lxf_lambda)) * volumes


class SimplifiedEngquistOsherFlux(NumericalConvectiveFlux):

    def __init__(self, flux, flux_derivative):
        self.flux = flux
        self.flux_derivative = flux_derivative
        self.build_parameter_type(inherits=(flux, flux_derivative))

    def evaluate_stage1(self, U, mu=None):
        return self.flux(U[..., np.newaxis], mu), self.flux_derivative(U[..., np.newaxis], mu)

    def evaluate_stage2(self, stage1_data, unit_outer_normals, volumes, mu=None):
        F_edge, F_d_edge = stage1_data
        unit_outer_normals = unit_outer_normals[:, np.newaxis, :]
        F_d_edge = np.sum(F_d_edge * unit_outer_normals, axis=2)
        F_edge = np.sum(F_edge * unit_outer_normals, axis=2)
        F_edge[:, 0] = np.where(np.greater_equal(F_d_edge[:, 0], 0), F_edge[:, 0], 0)
        F_edge[:, 1] = np.where(np.less_equal(F_d_edge[:, 1], 0), F_edge[:, 1], 0)
        F_edge = np.sum(F_edge, axis=1)
        F_edge *= volumes
        return F_edge


class EngquistOsherFlux(NumericalConvectiveFlux):

    def __init__(self, flux, flux_derivative, gausspoints=5, intervals=1):
        self.flux = flux
        self.flux_derivative = flux_derivative
        self.gausspoints = gausspoints
        self.intervals = intervals
        self.build_parameter_type(inherits=(flux, flux_derivative))
        points, weights = GaussQuadratures.quadrature(npoints=self.gausspoints)
        points = points / intervals
        points = ((np.arange(self.intervals, dtype=np.float)[:, np.newaxis] * (1 / intervals)) + points[np.newaxis, :]).ravel()
        weights = np.tile(weights, intervals) * (1 / intervals)
        self.points = points
        self.weights = weights

    def evaluate_stage1(self, U, mu=None):
        int_els = np.abs(U)[:, np.newaxis, np.newaxis]
        return [np.concatenate([self.flux_derivative(U[:, np.newaxis] * p, mu)[:, np.newaxis, :] * int_els * w
                               for p, w in izip(self.points, self.weights)], axis=1)]

    def evaluate_stage2(self, stage1_data, unit_outer_normals, volumes, mu=None):
        F0 = np.sum(self.flux.evaluate(np.array([[0.]]), mu=mu) * unit_outer_normals, axis=1)
        Fs = np.sum(stage1_data[0] * unit_outer_normals[:, np.newaxis, np.newaxis, :], axis=3)
        Fs[:, 0, :] = np.maximum(Fs[:, 0, :], 0)
        Fs[:, 1, :] = np.minimum(Fs[:, 1, :], 0)
        Fs = np.sum(np.sum(Fs, axis=2), axis=1) + F0
        Fs *= volumes
        return Fs


class NonlinearAdvectionOperator(OperatorBase):
    '''Base class for nonlinear finite volume advection operators.
    '''

    type_source = type_range = NumpyVectorArray

    def __init__(self, grid, boundary_info, numerical_flux, dirichlet_data=None, name=None):
        assert dirichlet_data is None or isinstance(dirichlet_data, FunctionInterface)

        super(NonlinearAdvectionOperator, self).__init__()
        self.grid = grid
        self.boundary_info = boundary_info
        self.numerical_flux = numerical_flux
        self.dirichlet_data = dirichlet_data
        self.name = name
        if (isinstance(dirichlet_data, FunctionInterface) and boundary_info.has_dirichlet
            and not dirichlet_data.parametric):
            self._dirichlet_values = self.dirichlet_data(grid.centers(1)[boundary_info.dirichlet_boundaries(1)])
            self._dirichlet_values = self._dirichlet_values.ravel()
            self._dirichlet_values_flux_shaped = self._dirichlet_values.reshape((-1,1))
        self.build_parameter_type(inherits=(numerical_flux, dirichlet_data))
        self.dim_source = self.dim_range = grid.size(0)
        self.with_arguments = set(self.with_arguments).union('numerical_flux_{}'.format(arg)
                                                             for arg in numerical_flux.with_arguments)

    with_arguments = set(method_arguments(__init__))

    def with_(self, **kwargs):
        assert 'numerical_flux' not in kwargs or not any(arg.startswith('numerical_flux_') for arg in kwargs)
        num_flux_args = {arg[len('numerical_flux_'):]: kwargs.pop(arg)
                         for arg in list(kwargs) if arg.startswith('numerical_flux_')}
        if num_flux_args:
            kwargs['numerical_flux'] = self.numerical_flux.with_(**num_flux_args)
        return self._with_via_init(kwargs)

    def restricted(self, components):
        source_dofs = np.setdiff1d(np.union1d(self.grid.neighbours(0, 0)[components].ravel(), components),
                                   np.array([-1], dtype=np.int32),
                                   assume_unique=True)
        sub_grid = SubGrid(self.grid, entities=source_dofs)
        sub_boundary_info = SubGridBoundaryInfo(sub_grid, self.grid, self.boundary_info)
        op = self.with_(grid=sub_grid, boundary_info=sub_boundary_info, name='{}_restricted'.format(self.name))
        sub_grid_indices = sub_grid.indices_from_parent_indices(components, codim=0)
        proj = ComponentProjection(sub_grid_indices, op.dim_range, op.type_range)
        return Concatenation(proj, op), sub_grid.parent_indices(0)

    def apply(self, U, ind=None, mu=None):
        assert isinstance(U, NumpyVectorArray)
        assert U.dim == self.dim_source
        mu = self.parse_parameter(mu)

        ind = xrange(len(U)) if ind is None else ind
        U = U.data
        R = np.zeros((len(ind), self.dim_source))

        g = self.grid
        bi = self.boundary_info
        N = g.neighbours(0, 0)
        SUPE = g.superentities(1, 0)
        SUPI = g.superentity_indices(1, 0)
        assert SUPE.ndim == 2
        VOLS = g.volumes(1)
        boundaries = g.boundaries(1)
        unit_outer_normals = g.unit_outer_normals()[SUPE[:,0], SUPI[:,0]]

        if bi.has_dirichlet:
            dirichlet_boundaries = bi.dirichlet_boundaries(1)
            if hasattr(self, '_dirichlet_values'):
                dirichlet_values = self._dirichlet_values
            elif self.dirichlet_data is not None:
                dirichlet_values = self.dirichlet_data(g.centers(1)[dirichlet_boundaries], mu=mu)
            else:
                dirichlet_values = np.zeros_like(dirichlet_boundaries)
            F_dirichlet = self.numerical_flux.evaluate_stage1(dirichlet_values, mu)

        for i, j in enumerate(ind):
            Ui = U[j]
            Ri = R[i]

            F = self.numerical_flux.evaluate_stage1(Ui, mu)
            F_edge = [f[SUPE] for f in F]

            for f in F_edge:
                f[boundaries, 1] = f[boundaries, 0]
            if bi.has_dirichlet:
                for f, f_d in izip(F_edge, F_dirichlet):
                    f[dirichlet_boundaries, 1] = f_d

            NUM_FLUX = self.numerical_flux.evaluate_stage2(F_edge, unit_outer_normals, VOLS, mu)

            if bi.has_neumann:
                NUM_FLUX[bi.neumann_boundaries(1)] = 0

            iadd_masked(Ri, NUM_FLUX, SUPE[:,0])
            isub_masked(Ri, NUM_FLUX, SUPE[:,1])

        R /= g.volumes(0)

        return NumpyVectorArray(R)


def nonlinear_advection_lax_friedrichs_operator(grid, boundary_info, flux, lxf_lambda=1.0, dirichlet_data=None, name=None):
    num_flux = LaxFriedrichsFlux(flux, lxf_lambda)
    return NonlinearAdvectionOperator(grid, boundary_info, num_flux, dirichlet_data, name)


def nonlinear_advection_simplified_engquist_osher_operator(grid, boundary_info, flux, flux_derivative,
                                                           dirichlet_data=None, name=None):
    num_flux = SimplifiedEngquistOsherFlux(flux, flux_derivative)
    return NonlinearAdvectionOperator(grid, boundary_info, num_flux, dirichlet_data, name)


def nonlinear_advection_engquist_osher_operator(grid, boundary_info, flux, flux_derivative, gausspoints=5, intervals=1,
                                                dirichlet_data=None, name=None):
    num_flux = EngquistOsherFlux(flux, flux_derivative, gausspoints=gausspoints, intervals=intervals)
    return NonlinearAdvectionOperator(grid, boundary_info, num_flux, dirichlet_data, name)


class LinearAdvectionLaxFriedrichs(NumpyMatrixBasedOperator):
    '''Linear Finite Volume Advection operator using Lax-Friedrichs-Flux.
    '''

    type_source = type_range = NumpyVectorArray

    def __init__(self, grid, boundary_info, velocity_field, lxf_lambda=1.0, name=None):
        super(LinearAdvectionLaxFriedrichs, self).__init__()
        self.grid = grid
        self.boundary_info = boundary_info
        self.velocity_field = velocity_field
        self.lxf_lambda = lxf_lambda
        self.name = name
        self.build_parameter_type(inherits=(velocity_field,))
        self.dim_source = self.dim_range = grid.size(0)

    def _assemble(self, mu=None):
        mu = self.parse_parameter(mu)

        g = self.grid
        bi = self.boundary_info
        SUPE = g.superentities(1, 0)
        SUPI = g.superentity_indices(1, 0)
        assert SUPE.ndim == 2
        edge_volumes = g.volumes(1)
        boundary_edges = g.boundaries(1)
        inner_edges = np.setdiff1d(np.arange(g.size(1)), boundary_edges)
        dirichlet_edges = bi.dirichlet_boundaries(1) if bi.has_dirichlet else np.array([], ndmin=1, dtype=np.int)
        neumann_edges = bi.neumann_boundaries(1) if bi.has_neumann else np.array([], ndmin=1, dtype=np.int)
        outflow_edges = np.setdiff1d(boundary_edges, np.hstack([dirichlet_edges, neumann_edges]))
        normal_velocities = np.einsum('ei,ei->e',
                                      self.velocity_field(g.centers(1), mu=mu),
                                      g.unit_outer_normals()[SUPE[:,0], SUPI[:,0]])


        nv_inner = normal_velocities[inner_edges]
        l_inner = np.ones_like(nv_inner) * (1. / self.lxf_lambda)
        I0_inner = np.hstack([SUPE[inner_edges, 0], SUPE[inner_edges, 0], SUPE[inner_edges, 1], SUPE[inner_edges, 1]])
        I1_inner = np.hstack([SUPE[inner_edges, 0], SUPE[inner_edges, 1], SUPE[inner_edges, 0], SUPE[inner_edges, 1]])
        V_inner =  np.hstack([nv_inner, nv_inner, -nv_inner, -nv_inner])
        V_inner += np.hstack([l_inner, -l_inner, -l_inner, l_inner])
        V_inner *= np.tile(0.5 * edge_volumes[inner_edges], 4)

        I_out = SUPE[outflow_edges, 0]
        V_out = edge_volumes[outflow_edges] * normal_velocities[outflow_edges]

        I_dir = SUPE[dirichlet_edges, 0]
        V_dir = edge_volumes[outflow_edges] * (0.5 * normal_velocities[dirichlet_edges] + 0.5 / self.lxf_lambda)

        I0 = np.hstack([I0_inner, I_out, I_dir])
        I1 = np.hstack([I1_inner, I_out, I_dir])
        V = np.hstack([V_inner, V_out, V_dir])

        A = coo_matrix((V, (I0, I1)), shape=(g.size(0), g.size(0)))
        A = csr_matrix(A).copy()   # See cg.DiffusionOperatorP1 for why copy() is necessary
        A = diags([1. / g.volumes(0)], [0]) * A

        return NumpyMatrixOperator(A)


class L2Product(NumpyMatrixBasedOperator):
    '''Operator representing the L2-product for finite volume functions.

    To evaluate the product use the apply2 method.

    Parameters
    ----------
    grid
        The grid on which to assemble the product.
    name
        The name of the product.
    '''

    type_source = type_range = NumpyVectorArray
    sparse = True

    def __init__(self, grid, name=None):
        super(L2Product, self).__init__()
        self.dim_source = grid.size(0)
        self.dim_range = self.dim_source
        self.grid = grid
        self.name = name

    def _assemble(self, mu=None):
        assert self.check_parameter(mu)

        A = diags(self.grid.volumes(0), 0)

        return NumpyMatrixOperator(A)


class L2ProductFunctional(NumpyMatrixBasedOperator):
    '''Scalar product with an L2-function for finite volume functions.

    Parameters
    ----------
    grid
        Grid over which to assemble the functional.
    function
        The `Function` with which to take the scalar product.
    name
        The name of the functional.
    '''

    type_source = type_range = NumpyVectorArray
    sparse = False

    def __init__(self, grid, function, name=None):
        assert function.shape_range == tuple()
        super(L2ProductFunctional, self).__init__()
        self.dim_source = grid.size(0)
        self.dim_range = 1
        self.grid = grid
        self.function = function
        self.name = name
        self.build_parameter_type(inherits=(function,))

    def _assemble(self, mu=None):
        mu = self.parse_parameter(mu)
        g = self.grid

        # evaluate function at all quadrature points -> shape = (g.size(0), number of quadrature points, 1)
        F = self.function(g.quadrature_points(0, order=2), mu=mu)

        _, w = g.reference_element.quadrature(order=2)

        # integrate the products of the function with the shape functions on each element
        # -> shape = (g.size(0), number of shape functions)
        F_INTS = np.einsum('ei,e,i->e', F, g.integration_elements(0), w).ravel()
        F_INTS /= g.volumes(0)

        return NumpyMatrixOperator(F_INTS.reshape((1, -1)))