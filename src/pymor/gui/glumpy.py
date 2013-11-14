# This file is part of the pyMor project (http://www.pymor.org).
# Copyright Holders: Felix Albrecht, Rene Milk, Stephan Rave
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from __future__ import absolute_import, division, print_function

import math as m

import numpy as np
from PySide.QtOpenGL import QGLWidget
from PySide.QtGui import QSizePolicy, QPainter, QFontMetrics
from glumpy.graphics.vertex_buffer import VertexBuffer
import OpenGL.GL as gl
import OpenGL.GLUT as glut

from pymor.grids.constructions import flatten_grid
from pymor.grids.referenceelements import triangle, square
from pymor.la.numpyvectorarray import NumpyVectorArray


def compile_vertex_shader(source):
    """Compile a vertex shader from source."""
    vertex_shader = gl.glCreateShader(gl.GL_VERTEX_SHADER)
    gl.glShaderSource(vertex_shader, source)
    gl.glCompileShader(vertex_shader)
    # check compilation error
    result = gl.glGetShaderiv(vertex_shader, gl.GL_COMPILE_STATUS)
    if not(result):
        raise RuntimeError(gl.glGetShaderInfoLog(vertex_shader))
    return vertex_shader


def link_shader_program(vertex_shader):
    """Create a shader program with from compiled shaders."""
    program = gl.glCreateProgram()
    gl.glAttachShader(program, vertex_shader)
    gl.glLinkProgram(program)
    # check linking error
    result = gl.glGetProgramiv(program, gl.GL_LINK_STATUS)
    if not(result):
        raise RuntimeError(gl.glGetProgramInfoLog(program))
    return program

VS = """
#version 120
// Attribute variable that contains coordinates of the vertices.
attribute vec4 position;

vec3 getJetColor(float value) {
     float fourValue = 4 * value;
     float red   = min(fourValue - 1.5, -fourValue + 4.5);
     float green = min(fourValue - 0.5, -fourValue + 3.5);
     float blue  = min(fourValue + 0.5, -fourValue + 2.5);

     return clamp( vec3(red, green, blue), 0.0, 1.0 );
}
void main()
{
    gl_Position = position;
    gl_FrontColor = vec4(getJetColor(gl_Color.x), 1);
}
"""


class GlumpyPatchWidget(QGLWidget):

    def __init__(self, parent, grid, vmin=None, vmax=None, bounding_box=[[0,0], [1,1]], codim=2):
        assert grid.reference_element in (triangle, square)
        assert codim in (0, 2)
        super(GlumpyPatchWidget, self).__init__(parent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        subentities, coordinates, entity_map = flatten_grid(grid)
        self.subentities = subentities
        self.coordinates = coordinates
        self.entity_map = entity_map
        self.reference_element = grid.reference_element
        self.U = np.zeros(len(entity_map))
        self.vmin = vmin
        self.vmax = vmax
        self.bounding_box = bounding_box
        self.codim = codim
        self.update_vbo = False

    def resizeGL(self, w, h):
        gl.glViewport(0, 0, w, h)
        gl.glLoadIdentity()
        self.update()

    def upload_buffer(self):
        if self.codim == 2:
            self.vbo.vertices['color'][:, 0] = self.U
        elif self.reference_element == triangle:
            self.vbo.vertices['color'][:, 0] = np.repeat(self.U, 3)
        else:
            self.vbo.vertices['color'][:, 0] = np.tile(np.repeat(self.U, 3), 2)
        self.vbo.upload()
        self.update_vbo = False

    def initializeGL(self):
        gl.glClearColor(1.0, 1.0, 1.0, 1.0)
        self.shaders_program = link_shader_program(compile_vertex_shader(VS))
        bb = self.bounding_box
        size = np.array([bb[1][0] - bb[0][0], bb[1][1] - bb[0][1]])
        scale = 1 / size
        shift = - np.array(bb[0]) - size / 2
        if self.reference_element == triangle:
            if self.codim == 2:
                x, y = (self.coordinates[:, 0] + shift[0]) * scale[0], (self.coordinates[:, 1] + shift[1]) * scale[1]
                lpos = np.array([(x[i], y[i], 0, 0.5) for i in xrange(len(self.entity_map))],
                                dtype='f')
                vertex_data = np.array([(lpos[i], (1, 1, 1, 1)) for i in xrange(len(self.entity_map))],
                                       dtype=[('position', 'f4', 4), ('color', 'f4', 4)])
                self.vbo = VertexBuffer(vertex_data, indices=self.subentities)
            else:
                num_entities = len(self.subentities)
                vertex_data = np.empty(num_entities * 3, dtype=[('position', 'f4', 4), ('color', 'f4', 4)])
                VERTEX_POS = self.coordinates[self.subentities]
                VERTEX_POS += shift
                VERTEX_POS *= scale
                vertex_data['position'][:, 0:2] = VERTEX_POS.reshape((-1, 2))
                vertex_data['position'][:, 2] = 0
                vertex_data['position'][:, 3] = 0.5
                vertex_data['color'] = 1
                self.vbo = VertexBuffer(vertex_data, indices=np.arange(num_entities * 3, dtype=np.uint32))
        else:
            if self.codim == 0:
                num_entities = len(self.subentities)
                vertex_data = np.empty(num_entities * 6, dtype=[('position', 'f4', 4), ('color', 'f4', 4)])
                VERTEX_POS = self.coordinates[self.subentities]
                VERTEX_POS += shift
                VERTEX_POS *= scale
                vertex_data['position'][0:num_entities * 3, 0:2] = VERTEX_POS[:, 0:3, :].reshape((-1, 2))
                vertex_data['position'][num_entities * 3:, 0:2] = VERTEX_POS[:, [0, 2, 3], :].reshape((-1, 2))
                vertex_data['position'][:, 2] = 0
                vertex_data['position'][:, 3] = 0.5
                vertex_data['color'] = 1
                self.vbo = VertexBuffer(vertex_data, indices=np.arange(num_entities * 6, dtype=np.uint32))
            else:
                x, y = (self.coordinates[:, 0] + shift[0]) * scale[0], (self.coordinates[:, 1] + shift[1]) * scale[1]
                lpos = np.array([(x[i], y[i], 0, 0.5) for i in xrange(len(self.entity_map))],
                                dtype='f')
                vertex_data = np.array([(lpos[i], (1, 1, 1, 1)) for i in xrange(len(self.entity_map))],
                                       dtype=[('position', 'f4', 4), ('color', 'f4', 4)])
                self.vbo = VertexBuffer(vertex_data, indices=np.vstack((self.subentities[:, 0:3],
                                                                        self.subentities[:, [0, 2, 3]])))

        gl.glUseProgram(self.shaders_program)
        self.upload_buffer()

    def paintGL(self):
        if self.update_vbo:
            self.upload_buffer()
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        self.vbo.draw(gl.GL_TRIANGLES, 'pc')

    def set(self, U):
        # normalize U
        U = np.array(U)
        vmin = np.min(U) if self.vmin is None else self.vmin
        vmax = np.max(U) if self.vmax is None else self.vmax
        U -= vmin
        U /= float(vmax - vmin)
        if self.codim == 2:
            self.U = U[self.entity_map]
        else:
            self.U = U
        self.update_vbo = True
        self.update()


class ColorBarWidget(QGLWidget):

    def __init__(self, parent, vmin=None, vmax=None):
        super(ColorBarWidget, self).__init__(parent)
        fm = QFontMetrics(self.font())
        self.vmin = float(vmin or 0)
        self.vmax = float(vmax or 1)
        precision = m.log(max(abs(self.vmin), abs(self.vmax) / abs(self.vmin - self.vmax)) , 10) + 1
        precision = int(min(max(precision, 3), 8))
        self.vmin_str = format(('{:.' + str(precision) + '}').format(self.vmin))
        self.vmax_str = format(('{:.' + str(precision) + '}').format(self.vmax))
        self.vmin_width = fm.width(self.vmin_str)
        self.vmax_width = fm.width(self.vmax_str)
        self.text_height = fm.height() * 1.5
        self.text_ascent = fm.ascent() * 1.5
        self.text_descent = fm.descent() * 1.5
        self.setMinimumSize(max(self.vmin_width, self.vmax_width) + 20, 300)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding))
        self.setAutoFillBackground(False)

    def resizeGL(self, w, h):
        gl.glViewport(0, 0, w, h)
        gl.glLoadIdentity()
        self.update()

    def initializeGL(self):
        gl.glClearColor(1.0, 1.0, 1.0, 1.0)
        self.shaders_program = link_shader_program(compile_vertex_shader(VS))
        gl.glUseProgram(self.shaders_program)

    def set(self, U):
        # normalize U
        self.vmin = np.min(U) if self.vmin is None else self.vmin
        self.vmax = np.max(U) if self.vmax is None else self.vmax

    def paintGL(self):
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        gl.glUseProgram(self.shaders_program)

        gl.glBegin(gl.GL_QUAD_STRIP)
        bar_start = -1 + self.text_height / self.height() * 2
        bar_height = (1 - 2 * self.text_height / self.height()) * 2
        steps = 40
        for i in xrange(steps + 1):
            y = i * (1 / steps)
            gl.glColor(y, 0, 0)
            gl.glVertex(-0.5, (bar_height*y + bar_start), 0.0)
            gl.glVertex(0.5, (bar_height*y + bar_start), 0.0)
        gl.glEnd()
        p = QPainter(self)
        p.drawText((self.width() - self.vmax_width)/2, self.text_ascent, self.vmax_str)
        p.drawText((self.width() - self.vmin_width)/2, self.height() - self.text_height + self.text_ascent, self.vmin_str)
        p.end()