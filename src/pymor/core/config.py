# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright 2013-2016 pyMOR developers and contributors. All rights reserved.
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from importlib import import_module
import sys


def _get_fenics_version():
    import dolfin as df
    version = list(map(int, df.__version__.split('.')))
    if version[:2] != [1, 6]:
        import warnings
        warnings.warn('FEniCS support has only been tested with dolfin 1.6.')
    return version


def _get_matplotlib_version():
    import matplotlib
    # matplotlib's default is to use PyQt for Qt4 bindings. However, we use PySide ..
    matplotlib.rcParams['backend.qt4'] = 'PySide'
    return matplotlib.__version__


def _get_ipython_version():
    try:
        import ipyparallel
        return ipyparallel.__version__
    except ImportError:
        import IPython.parallel
        return getattr(IPython.parallel, '__version__', True)


_PACKAGES = {
    'CYTHON': lambda: import_module('cython').__version__,
    'DEALII': lambda: bool(import_module('pydealii')),
    'DOCOPT': lambda: import_module('docopt').__version__,
    'DUNEXT': lambda: bool(import_module('dune.xt.la')),
    'DUNEGDT': lambda: bool(import_module('dune.gdt')),
    'FENICS': _get_fenics_version,
    'GL': lambda: import_module('OpenGL.GL') and import_module('OpenGL').__version__,
    'IPYTHON': _get_ipython_version,
    'MATPLOTLIB': _get_matplotlib_version,
    'MPI': lambda: import_module('mpi4py.MPI') and import_module('mpi4py').__version__,
    'NUMPY': lambda: import_module('numpy').__version__,
    'PYAMG': lambda: import_module('pyamg.version').full_version,
    'PYSIDE': lambda: import_module('PySide.QtGui') and import_module('PySide.QtCore').__version__,
    'PYTEST': lambda: import_module('pytest').__version__,
    'PYVTK': lambda: bool(import_module('evtk')),
    'QTOPENGL': lambda: bool(import_module('PySide.QtOpenGL')),
    'SCIPY': lambda: import_module('scipy').__version__,
    'SCIPY_LSMR': lambda: hasattr(import_module('scipy.sparse.linalg'), 'lsmr'),
    'SPHINX': lambda: import_module('sphinx').__version__,
}


class Config:

    def __init__(self):
        self.PY2 = sys.version_info.major == 2
        self.PY3 = sys.version_info.major == 3
        self.PYTHON_VERSION = '{}.{}.{}'.format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)

    @property
    def version(self):
        from pymor import __version__
        return __version__

    def __getattr__(self, name):
        if name.startswith('HAVE_'):
            package = name[len('HAVE_'):]
        elif name.endswith('_VERSION'):
            package = name[:-len('_VERSION')]
        else:
            raise AttributeError

        if package in _PACKAGES:
            try:
                version = _PACKAGES[package]()
            except ImportError:
                version = False

            if version is not None and version is not False:
                setattr(self, 'HAVE_' + package, True)
                setattr(self, package + '_VERSION', version)
            else:
                setattr(self, 'HAVE_' + package, False)
                setattr(self, package + '_VERSION', None)
        else:
            raise AttributeError

        return getattr(self, name)

    def __dir__(self, old=False):
        if self.PY2:
            keys = set(dir(type(self))).union(self.__dict__.keys())
        else:
            keys = set(super().__dir__())
        keys.update('HAVE_' + package for package in _PACKAGES)
        keys.update(package + '_VERSION' for package in _PACKAGES)
        return list(keys)

    def __repr__(self):
        status = {p: (lambda v: 'missing' if not v else 'present' if v is True else v)(getattr(self, p + '_VERSION'))
                  for p in _PACKAGES}
        key_width = max(len(p) for p in _PACKAGES) + 2
        package_info = ['{:{}} {}'.format(p + ':', key_width, v) for p, v in sorted(status.items())]
        info = '''
pyMOR Version {}

Python: {}

External Packages
{}
{}

Defaults
--------
See pymor.core.defaults.print_defaults.
'''[1:].format(self.version, self.PYTHON_VERSION, '-' * max(map(len, package_info)),
               '\n'.join(package_info))
        return info


config = Config()
