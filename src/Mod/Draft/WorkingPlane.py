# ***************************************************************************
# *   Copyright (c) 2009, 2010 Ken Cline <cline@frii.com>                   *
# *   Copyright (c) 2023 FreeCAD Project Association                        *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************
"""Provide the working plane code and utilities for the Draft Workbench.

This module provides the plane class which provides a virtual working plane
in FreeCAD and a couple of utility functions.
The working plane is mostly intended to be used in the Draft Workbench
to draw 2D objects in various orientations, not only in the standard XY,
YZ, and XZ planes.
"""
## @package WorkingPlane
#  \ingroup DRAFT
#  \brief This module handles the Working Plane and grid of the Draft module.
#
#  This module provides the plane class which provides a virtual working plane
#  in FreeCAD and a couple of utility functions.

import math
import lazy_loader.lazy_loader as lz

import FreeCAD
import DraftVecUtils
from FreeCAD import Vector
from draftutils import utils
from draftutils.messages import _wrn
from draftutils.translate import translate

DraftGeomUtils = lz.LazyLoader("DraftGeomUtils", globals(), "DraftGeomUtils")
Part = lz.LazyLoader("Part", globals(), "Part")
FreeCADGui = lz.LazyLoader("FreeCADGui", globals(), "FreeCADGui")

__title__ = "FreeCAD Working Plane utility"
__author__ = "Ken Cline"
__url__ = "https://www.freecad.org"


class PlaneBase:
    """PlaneBase is the base class for the Plane class and the PlaneGui class.

    Parameters
    ----------
    u: Base.Vector or WorkingPlane.PlaneBase, optional
        Defaults to Vector(1, 0, 0).
        If a WP is provided:
            A copy of the WP is created, all other parameters are then ignored.
        If a vector is provided:
            Unit vector for the `u` attribute (+X axis).

    v: Base.Vector, optional
        Defaults to Vector(0, 1, 0).
        Unit vector for the `v` attribute (+Y axis).

    w: Base.Vector, optional
        Defaults to Vector(0, 0, 1).
        Unit vector for the `axis` attribute (+Z axis).

    pos: Base.Vector, optional
        Defaults to Vector(0, 0, 0).
        Vector for the `position` attribute (origin).

    Note that the u, v and w vectors are not checked for validity.
    """

    def __init__(self,
                 u=Vector(1, 0, 0), v=Vector(0, 1, 0), w=Vector(0, 0, 1),
                 pos=Vector(0, 0, 0)):

        if isinstance(u, PlaneBase):
            self.match(u)
            return
        self.u = Vector(u)
        self.v = Vector(v)
        self.axis = Vector(w)
        self.position = Vector(pos)

    def __repr__(self):
        text = "Workplane"
        text += " x=" + str(DraftVecUtils.rounded(self.u))
        text += " y=" + str(DraftVecUtils.rounded(self.v))
        text += " z=" + str(DraftVecUtils.rounded(self.axis))
        text += " pos=" + str(DraftVecUtils.rounded(self.position))
        return text

    def copy(self):
        """Return a new WP that is a copy of the present object."""
        wp = PlaneBase()
        self.match(source=self, target=wp)
        return wp

    def _copy_value(self, val):
        """Return a copy of a value, primarily required for vectors."""
        return val.__class__(val)

    def match(self, source, target=None):
        """Match the main properties of two working planes.

        Parameters
        ----------
        source: WP object
            WP to copy properties from.
        target: WP object, optional
            Defaults to `None`.
            WP to copy properties to. If `None` the present object is used.
        """
        if target is None:
            target = self
        for prop in self._get_prop_list():
            setattr(target, prop, self._copy_value(getattr(source, prop)))

    def get_parameters(self):
        """Return a data dictionary with the main properties of the WP."""
        data = {}
        for prop in self._get_prop_list():
            data[prop] = self._copy_value(getattr(self, prop))
        return data

    def set_parameters(self, data):
        """Set the main properties of the WP according to a data dictionary."""
        for prop in self._get_prop_list():
            setattr(self, prop, self._copy_value(data[prop]))

    def align_to_3_points(self, p1, p2, p3, offset=0):
        """Align the WP to 3 points with an optional offset.

        The points must define a plane.

        Parameters
        ----------
        p1: Base.Vector
            New WP `position`.
        p2: Base.Vector
            Point on the +X axis. (p2 - p1) defines the WP `u` axis.
        p3: Base.Vector
            Defines the plane.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        return self.align_to_edge_or_wire(Part.makePolygon([p1, p2, p3]), offset)

    def align_to_edges_vertexes(self, shapes, offset=0):
        """Align the WP to the endpoints of edges and/or the points of vertexes
        with an optional offset.

        The points must define a plane.

        The first 2 points define the WP `position` and `u` axis.

        Parameters
        ----------
        shapes: iterable
            One or more edges and/or vertexes.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        points = [vert.Point for shape in shapes for vert in shape.Vertexes]
        if len(points) < 2:
            return False
        return self.align_to_edge_or_wire(Part.makePolygon(points), offset)

    def align_to_edge_or_wire(self, shape, offset=0):
        """Align the WP to an edge or wire with an optional offset.

        The shape must define a plane.

        If the shape is an edge with a `Center` then that defines the WP
        `position`. The vector between the center and its start point then
        defines the WP `u` axis.

        In other cases the start point of the first edge defines the WP
        `position` and the 1st derivative at that point the WP `u` axis.

        Parameters
        ----------
        shape: Part.Edge or Part.Wire
            Edge or wire.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        tol = 1e-7
        plane = shape.findPlane()
        if plane is None:
            return False
        self.axis = plane.Axis
        if shape.ShapeType == "Edge" and hasattr(shape.Curve, "Center"):
            pos = shape.Curve.Center
            vec = shape.Vertexes[0].Point - pos
            if vec.Length > tol:
                self.u = vec
                self.u.normalize()
                self.v = self.axis.cross(self.u)
            else:
                self.u, self.v, _ = self._axes_from_rotation(plane.Rotation)
        elif shape.Edges[0].Length > tol:
            pos = shape.Vertexes[0].Point
            self.u = shape.Edges[0].derivative1At(0)
            self.u.normalize()
            self.v = self.axis.cross(self.u)
        else:
            pos = shape.Vertexes[0].Point
            self.u, self.v, _ = self._axes_from_rotation(plane.Rotation)
        self.position = pos + (self.axis * offset)
        return True

    def align_to_face(self, shape, offset=0):
        """Align the WP to a face with an optional offset.

        The face must be planar.

        The center of gravity of the face defines the WP `position` and the
        normal of the face the WP `axis`. The WP `u` and `v` vectors are
        determined by the DraftGeomUtils.uv_vectors_from_face function.
        See there.

        Parameters
        ----------
        shape: Part.Face
            Face.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        if shape.Surface.isPlanar() is False:
            return False
        place = DraftGeomUtils.placement_from_face(shape)
        self.u, self.v, self.axis = self._axes_from_rotation(place.Rotation)
        self.position = place.Base + (self.axis * offset)
        return True

    def align_to_placement(self, place, offset=0):
        """Align the WP to a placement with an optional offset.

        Parameters
        ----------
        place: Base.Placement
            Placement.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.

        Returns
        -------
        `True`
        """
        self.u, self.v, self.axis = self._axes_from_rotation(place.Rotation)
        self.position = place.Base + (self.axis * offset)
        return True

    def align_to_point_and_axis(self, point, axis, offset=0, upvec=Vector(1, 0, 0)):
        """Align the WP to a point and an axis with an optional offset and an
        optional up-vector.

        If the axis and up-vector are parallel the FreeCAD.Rotation algorithm
        will replace the up-vector: Vector(0, 0, 1) is tried first, then
        Vector(0, 1, 0), and finally Vector(1, 0, 0).

        Parameters
        ----------
        point: Base.Vector
            New WP `position`.
        axis: Base.Vector
            New WP `axis`.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.
        upvec: Base.Vector, optional
            Defaults to Vector(1, 0, 0).
            Up-vector.

        Returns
        -------
        `True`
        """
        tol = 1e-7
        if axis.Length < tol:
            return False
        if upvec.Length < tol:
            return False
        axis = Vector(axis).normalize()
        upvec = Vector(upvec).normalize()
        if axis.isEqual(upvec, tol) or axis.isEqual(upvec.negative(), tol):
            upvec = axis
        rot = FreeCAD.Rotation(Vector(), upvec, axis, "ZYX")
        self.u, self.v, _ = self._axes_from_rotation(rot)
        self.axis = axis
        self.position = point + (self.axis * offset)
        return True

    def align_to_point_and_axis_svg(self, point, axis, offset=0):
        """Align the WP to a point and an axis with an optional offset.

        It aligns `u` and `v` based on the magnitude of the components
        of `axis`.

        Parameters
        ----------
        point: Base.Vector
            The new `position` of the plane, adjusted by
            the `offset`.
        axis: Base.Vector
            A vector whose unit vector will be used as the new `axis`
            of the plane.
            The magnitudes of the `x`, `y`, `z` components of the axis
            determine the orientation of `u` and `v` of the plane.
        offset: float, optional
            Defaults to zero. A value which will be used to offset
            the plane in the direction of its `axis`.

        Returns
        -------
        `True`

        Cases
        -----
        The `u` and `v` are always calculated the same

            * `u` is the cross product of the positive or negative of `axis`
              with a `reference vector`.
              ::
                  u = [+1|-1] axis.cross(ref_vec)
            * `v` is `u` rotated 90 degrees around `axis`.

        Whether the `axis` is positive or negative, and which reference
        vector is used, depends on the absolute values of the `x`, `y`, `z`
        components of the `axis` unit vector.

         #. If `x > y`, and `y > z`
             The reference vector is +Z
             ::
                 u = -1 axis.cross(+Z)
         #. If `y > z`, and `z >= x`
             The reference vector is +X.
             ::
                 u = -1 axis.cross(+X)
         #. If `y >= x`, and `x > z`
             The reference vector is +Z.
             ::
                 u = +1 axis.cross(+Z)
         #. If `x > z`, and `z >= y`
             The reference vector is +Y.
             ::
                 u = +1 axis.cross(+Y)
         #. If `z >= y`, and `y > x`
             The reference vector is +X.
             ::
                 u = +1 axis.cross(+X)
         #. otherwise
             The reference vector is +Y.
             ::
                 u = -1 axis.cross(+Y)
        """
        self.axis = Vector(axis).normalize()
        ref_vec = Vector(0.0, 1.0, 0.0)

        if ((abs(axis.x) > abs(axis.y)) and (abs(axis.y) > abs(axis.z))):
            ref_vec = Vector(0.0, 0., 1.0)
            self.u = axis.negative().cross(ref_vec)
            self.u.normalize()
            self.v = DraftVecUtils.rotate(self.u, math.pi/2, self.axis)
            # projcase = "Case new"

        elif ((abs(axis.y) > abs(axis.z)) and (abs(axis.z) >= abs(axis.x))):
            ref_vec = Vector(1.0, 0.0, 0.0)
            self.u = axis.negative().cross(ref_vec)
            self.u.normalize()
            self.v = DraftVecUtils.rotate(self.u, math.pi/2, self.axis)
            # projcase = "Y>Z, View Y"

        elif ((abs(axis.y) >= abs(axis.x)) and (abs(axis.x) > abs(axis.z))):
            ref_vec = Vector(0.0, 0., 1.0)
            self.u = axis.cross(ref_vec)
            self.u.normalize()
            self.v = DraftVecUtils.rotate(self.u, math.pi/2, self.axis)
            # projcase = "ehem. XY, Case XY"

        elif ((abs(axis.x) > abs(axis.z)) and (abs(axis.z) >= abs(axis.y))):
            self.u = axis.cross(ref_vec)
            self.u.normalize()
            self.v = DraftVecUtils.rotate(self.u, math.pi/2, self.axis)
            # projcase = "X>Z, View X"

        elif ((abs(axis.z) >= abs(axis.y)) and (abs(axis.y) > abs(axis.x))):
            ref_vec = Vector(1.0, 0., 0.0)
            self.u = axis.cross(ref_vec)
            self.u.normalize()
            self.v = DraftVecUtils.rotate(self.u, math.pi/2, self.axis)
            # projcase = "Y>X, Case YZ"

        else:
            self.u = axis.negative().cross(ref_vec)
            self.u.normalize()
            self.v = DraftVecUtils.rotate(self.u, math.pi/2, self.axis)
            # projcase = "else"

        # spat_vec = self.u.cross(self.v)
        # spat_res = spat_vec.dot(axis)
        # Console.PrintMessage(projcase + " spat Prod = " + str(spat_res) + "\n")

        offsetVector = Vector(axis)
        offsetVector.multiply(offset)
        self.position = point.add(offsetVector)

        return True

    def get_global_coords(self, point, as_vector=False):
        """Translate a point or vector from the local (WP) coordinate system to
        the global coordinate system.

        Parameters
        ----------
        point: Base.Vector
            Point.
        as_vector: bool, optional
            Defaults to `False`.
            If `True` treat point as a vector.

        Returns
        -------
        Base.Vector
        """
        pos = Vector() if as_vector else self.position
        mtx = FreeCAD.Matrix(self.u, self.v, self.axis, pos)
        return mtx.multVec(point)

    def get_local_coords(self, point, as_vector=False):
        """Translate a point or vector from the global coordinate system to
        the local (WP) coordinate system.

        Parameters
        ----------
        point: Base.Vector
            Point.
        as_vector: bool, optional
            Defaults to `False`.
            If `True` treat point as a vector.

        Returns
        -------
        Base.Vector
        """
        pos = Vector() if as_vector else self.position
        mtx = FreeCAD.Matrix(self.u, self.v, self.axis, pos)
        return mtx.inverse().multVec(point)

    def get_closest_axis(self, vec):
        """Return a string indicating the positive or negative WP axis closest
        to a vector.

        Parameters
        ----------
        vec: Base.Vector
            Vector.

        Returns
        -------
        str
            `"x"`, `"y"` or `"z"`.
        """
        xyz = list(self.get_local_coords(vec, as_vector=True))
        x, y, z = [abs(coord) for coord in xyz]
        if x >= y and x >= z:
            return "x"
        elif y >= x and y >= z:
            return "y"
        else:
            return "z"

    def get_placement(self):
        """Return a placement calculated from the WP."""
        return FreeCAD.Placement(self.position, FreeCAD.Rotation(self.u, self.v, self.axis, "ZYX"))

    def is_global(self):
        """Return `True` if the WP matches the global coordinate system exactly."""
        return self.u == Vector(1, 0, 0) \
            and self.v == Vector(0, 1, 0) \
            and self.axis == Vector(0, 0, 1) \
            and self.position == Vector()

    def is_ortho(self):
        """Return `True` if all WP axes are  parallel to a global axis."""
        rot = FreeCAD.Rotation(self.u, self.v, self.axis, "ZYX")
        ypr = [round(ang, 6) for ang in rot.getYawPitchRoll()]
        return all([ang%90 == 0 for ang in ypr])

    def project_point(self, point, direction=None, force_projection=True):
        """Project a point onto the WP and return the global coordinates of the
        projected point.

        Parameters
        ----------
        point: Base.Vector
            Point to project.
        direction: Base.Vector, optional
            Defaults to `None` in which case the WP `axis` is used.
            Direction of projection.
        force_projection: bool, optional
            Defaults to `True`.
            See DraftGeomUtils.project_point_on_plane

        Returns
        -------
        Base.Vector
        """
        return DraftGeomUtils.project_point_on_plane(point,
                                                     self.position,
                                                     self.axis,
                                                     direction,
                                                     force_projection)

    def set_to_top(self, offset=0):
        """Sets the WP to the top position with an optional offset."""
        self.u = Vector(1, 0, 0)
        self.v = Vector(0, 1, 0)
        self.axis = Vector(0, 0, 1)
        self.position = self.axis * offset

    def set_to_front(self, offset=0):
        """Sets the WP to the front position with an optional offset."""
        self.u = Vector(1, 0, 0)
        self.v = Vector(0, 0, 1)
        self.axis = Vector(0, -1, 0)
        self.position = self.axis * offset

    def set_to_side(self, offset=0):
        """Sets the WP to the right side position with an optional offset."""
        self.u = Vector(0, 1, 0)
        self.v = Vector(0, 0, 1)
        self.axis = Vector(1, 0, 0)
        self.position = self.axis * offset

    def _axes_from_rotation(self, rot):
        """Return a tuple with the `u`, `v` and `axis` vectors from a Base.Rotation."""
        mtx = rot.toMatrix()
        return mtx.col(0), mtx.col(1), mtx.col(2)

    def _axes_from_view_rotation(self, rot):
        """Return a tuple with the `u`, `v` and `axis` vectors from a Base.Rotation
        derived from a view. The Yaw, Pitch and Roll angles are rounded if they are
        near multiples of 45 degrees.
        """
        ypr = [round(ang, 3) for ang in rot.getYawPitchRoll()]
        if all([ang%45 == 0 for ang in ypr]):
            rot.setEulerAngles("YawPitchRoll", *ypr)
        return self._axes_from_rotation(rot)

    def _get_prop_list(self):
        return ["u",
                "v",
                "axis",
                "position"]


class Plane(PlaneBase):
    """The old Plane class.

    Parameters
    ----------
    u: Base.Vector or WorkingPlane.Plane, optional
        Defaults to Vector(1, 0, 0).
        If a WP is provided:
            A copy of the WP is created, all other parameters are then ignored.
        If a vector is provided:
            Unit vector for the `u` attribute (+X axis).

    v: Base.Vector, optional
        Defaults to Vector(0, 1, 0).
        Unit vector for the `v` attribute (+Y axis).

    w: Base.Vector, optional
        Defaults to Vector(0, 0, 1).
        Unit vector for the `axis` attribute (+Z axis).

    pos: Base.Vector, optional
        Defaults to Vector(0, 0, 0).
        Vector for the `position` attribute (origin).

    Note that the u, v and w vectors are not checked for validity.

    Other attributes
    ----------------
    weak: bool
        A weak WP is in "Auto" mode and will adapt to the current view.

    stored: None/list
        A placeholder for a stored state.
    """

    def __init__(self,
                 u=Vector(1, 0, 0), v=Vector(0, 1, 0), w=Vector(0, 0, 1),
                 pos=Vector(0, 0, 0),
                 weak=True):

        if isinstance(u, Plane):
            self.match(u)
            return
        super().__init__(u, v, w, pos)
        self.weak = weak
        # a placeholder for a stored state
        self.stored = None

    def copy(self):
        """See PlaneBase.copy."""
        wp = Plane()
        self.match(source=self, target=wp)
        return wp

    def offsetToPoint(self, point, direction=None):
        """Return the signed distance from a point to the plane. The direction
        argument is ignored.

        The returned value is the negative of the local Z coordinate of the point.
        """
        return -DraftGeomUtils.distance_to_plane(point, self.position, self.axis)

    def projectPoint(self, point, direction=None, force_projection=True):
        """See PlaneBase.project_point."""
        return super().project_point(point, direction, force_projection)

    def alignToPointAndAxis(self, point, axis, offset=0, upvec=None):
        """See PlaneBase.align_to_point_and_axis."""
        if upvec is None:
            upvec = Vector(1, 0, 0)
        super().align_to_point_and_axis(point, axis, offset, upvec)
        self.weak = False
        return True

    def alignToPointAndAxis_SVG(self, point, axis, offset=0):
        """See PlaneBase.align_to_point_and_axis_svg."""
        super().align_to_point_and_axis_svg(point, axis, offset)
        self.weak = False
        return True

    def alignToCurve(self, shape, offset=0):
        """Align the WP to a curve. NOT IMPLEMENTED.

        Parameters
        ----------
        shape: Part.Shape
            Edge or Wire.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.

        Returns
        -------
        `False`
        """
        return False

    def alignToEdges(self, shapes, offset=0):
        """Align the WP to edges with an optional offset.

        The eges must define a plane.

        The endpoints of the first edge defines the WP `position` and `u` axis.

        Parameters
        ----------
        shapes: iterable
            Two edges.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        if super().align_to_edges_vertexes(shapes, offset) is False:
            return False
        self.weak = False
        return True

    def alignToFace(self, shape, offset=0, parent=None):
        """Align the WP to a face with an optional offset.

        The face must be planar.

        The center of gravity of the face defines the WP `position` and the
        normal of the face the WP `axis`. The WP `u` and `v` vectors are
        determined by the DraftGeomUtils.uv_vectors_from_face function.
        See there.

        Parameters
        ----------
        shape: Part.Face
            Face.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`.
        parent: object
            Defaults to `None`.
            The ParentGeoFeatureGroup of the object the face belongs to.

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        if shape.ShapeType == "Face" and shape.Surface.isPlanar():
            place = DraftGeomUtils.placement_from_face(shape)
            if parent:
                place = parent.getGlobalPlacement() * place
            super().align_to_placement(place, offset)
            self.weak = False
            return True
        else:
            return False

    def alignTo3Points(self, p1, p2, p3, offset=0):
        """Align the plane to a temporary face created from three points.

        Parameters
        ----------
        p1: Base.Vector
            First point.
        p2: Base.Vector
            Second point.
        p3: Base.Vector
            Third point.
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        w = Part.makePolygon([p1, p2, p3, p1])
        f = Part.Face(w)
        return self.alignToFace(f, offset)

    def alignToSelection(self, offset=0):
        """Align the plane to a selection with an optional offset.

        The selection must define a plane.

        Parameter
        ---------
        offset: float, optional
            Defaults to zero.
            Offset along the WP `axis`

        Returns
        -------
        `True`/`False`
            `True` if successful.
        """
        sel_ex = FreeCADGui.Selection.getSelectionEx()
        if not sel_ex:
            return False

        shapes = list()
        names = list()
        for obj in sel_ex:
            # check that the geometric property is a Part.Shape object
            geom_is_shape = False
            if isinstance(obj.Object, FreeCAD.GeoFeature):
                geom = obj.Object.getPropertyOfGeometry()
                if isinstance(geom, Part.Shape):
                    geom_is_shape = True
            if not geom_is_shape:
                _wrn(translate(
                    "draft",
                    "Object without Part.Shape geometry:'{}'".format(
                        obj.ObjectName)) + "\n")
                return False
            if geom.isNull():
                _wrn(translate(
                    "draft",
                    "Object with null Part.Shape geometry:'{}'".format(
                        obj.ObjectName)) + "\n")
                return False
            if obj.HasSubObjects:
                shapes.extend(obj.SubObjects)
                names.extend([obj.ObjectName + "." + n for n in obj.SubElementNames])
            else:
                shapes.append(geom)
                names.append(obj.ObjectName)

        normal = None
        for n in range(len(shapes)):
            if not DraftGeomUtils.is_planar(shapes[n]):
                _wrn(translate(
                   "draft", "'{}' object is not planar".format(names[n])) + "\n")
                return False
            if not normal:
                normal = DraftGeomUtils.get_normal(shapes[n])
                shape_ref = n

        # test if all shapes are coplanar
        if normal:
            for n in range(len(shapes)):
                if not DraftGeomUtils.are_coplanar(shapes[shape_ref], shapes[n]):
                    _wrn(translate(
                        "draft", "{} and {} aren't coplanar".format(
                        names[shape_ref],names[n])) + "\n")
                    return False
        else:
            # suppose all geometries are straight lines or points
            points = [vertex.Point for shape in shapes for vertex in shape.Vertexes]
            if len(points) >= 3:
                poly = Part.makePolygon(points)
                if not DraftGeomUtils.is_planar(poly):
                    _wrn(translate(
                        "draft", "All Shapes must be coplanar") + "\n")
                    return False
                normal = DraftGeomUtils.get_normal(poly)
            else:
                normal = None

        if not normal:
            _wrn(translate(
                "draft", "Selected Shapes must define a plane") + "\n")
            return False

        # set center of mass
        ctr_mass = Vector(0,0,0)
        ctr_pts = Vector(0,0,0)
        mass = 0
        for shape in shapes:
            if hasattr(shape, "CenterOfMass"):
                ctr_mass += shape.CenterOfMass*shape.Mass
                mass += shape.Mass
            else:
                ctr_pts += shape.Point
        if mass > 0:
            ctr_mass /= mass
        # all shapes are vertexes
        else:
            ctr_mass = ctr_pts/len(shapes)

        super().align_to_point_and_axis(ctr_mass, normal, offset)
        self.weak = False
        return True

    def setup(self, direction=None, point=None, upvec=None, force=False):
        """Set up the working plane if it exists but is undefined.

        If `direction` and `point` are present,
        it calls `alignToPointAndAxis(point, direction, 0, upvec)`.

        Otherwise, it gets the camera orientation to define
        a working plane that is perpendicular to the current view,
        centered at the origin, and with `v` pointing up on the screen.

        This method only works when the `weak` attribute is `True`.
        This method also sets `weak` to `True`.

        This method only works when `FreeCAD.GuiUp` is `True`,
        that is, when the graphical interface is loaded.
        Otherwise it fails silently.

        Parameters
        ----------
        direction : Base::Vector3, optional
            It defaults to `None`. It is the new `axis` of the plane.
        point : Base::Vector3, optional
            It defaults to `None`. It is the new `position` of the plane.
        upvec : Base::Vector3, optional
            It defaults to `None`. It is the new `v` orientation of the plane.
        force : Bool
            If True, it sets the plane even if the plane is not in weak mode

        To do
        -----
        When the interface is not loaded it should fail and print
        a message, `_wrn()`.
        """
        if self.weak or force:
            if direction and point:
                self.alignToPointAndAxis(point, direction, 0, upvec)
            elif FreeCAD.GuiUp:
                try:
                    import FreeCADGui
                    from pivy import coin
                    view = FreeCADGui.ActiveDocument.ActiveView
                    camera = view.getCameraNode()
                    rot = camera.getField("orientation").getValue()
                    coin_up = coin.SbVec3f(0, 1, 0)
                    upvec = Vector(rot.multVec(coin_up).getValue())
                    vdir = view.getViewDirection()
                    # don't change the plane if the axis and v vector
                    # are already correct:
                    tol = Part.Precision.angular()
                    if abs(math.pi - vdir.getAngle(self.axis)) > tol \
                            or abs(math.pi - upvec.getAngle(self.v)) > tol:
                        self.alignToPointAndAxis(Vector(0, 0, 0),
                                                 vdir.negative(), 0, upvec)
                except Exception:
                    pass
            if force:
                self.weak = False
            else:
                self.weak = True

    def reset(self):
        """Reset the plane.

        Set `weak` to `True`.
        """
        self.weak = True

    def setTop(self):
        """sets the WP to top position and updates the GUI"""
        self.alignToPointAndAxis(FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Vector(0, 0, 1), 0.0)
        if FreeCAD.GuiUp:
            import FreeCADGui
            from draftutils.translate import translate
            if hasattr(FreeCADGui,"Snapper"):
                FreeCADGui.Snapper.setGrid()
            if hasattr(FreeCADGui,"draftToolBar"):
                FreeCADGui.draftToolBar.wplabel.setText(translate("draft", "Top"))

    def setFront(self):
        """sets the WP to front position and updates the GUI"""
        self.alignToPointAndAxis(FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Vector(0, 1, 0), 0.0)
        if FreeCAD.GuiUp:
            import FreeCADGui
            from draftutils.translate import translate
            if hasattr(FreeCADGui,"Snapper"):
                FreeCADGui.Snapper.setGrid()
            if hasattr(FreeCADGui,"draftToolBar"):
                FreeCADGui.draftToolBar.wplabel.setText(translate("draft", "Front"))

    def setSide(self):
        """sets the WP to top position and updates the GUI"""
        self.alignToPointAndAxis(FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Vector(-1, 0, 0), 0.0)
        if FreeCAD.GuiUp:
            import FreeCADGui
            from draftutils.translate import translate
            if hasattr(FreeCADGui,"Snapper"):
                FreeCADGui.Snapper.setGrid()
            if hasattr(FreeCADGui,"draftToolBar"):
                FreeCADGui.draftToolBar.wplabel.setText(translate("draft", "Side"))

    def getRotation(self):
        """Return a placement describing the plane orientation only.

        If `FreeCAD.GuiUp` is `True`, that is, if the graphical interface
        is loaded, it will test if the active object is an `Arch` container
        and will calculate the placement accordingly.

        Returns
        -------
        Base::Placement
            A placement, comprised of a `Base` (`Base::Vector3`),
            and a `Rotation` (`Base::Rotation`).
        """
        m = DraftVecUtils.getPlaneRotation(self.u, self.v)
        p = FreeCAD.Placement(m)
        # Arch active container
        if FreeCAD.GuiUp:
            import FreeCADGui
            if FreeCADGui.ActiveDocument:
                view = FreeCADGui.ActiveDocument.ActiveView
                if view and hasattr(view,"getActiveOject"):
                    a = view.getActiveObject("Arch")
                    if a:
                        p = a.Placement.inverse().multiply(p)
        return p

    def getPlacement(self, rotated=False):
        """Return the placement of the plane.

        Parameters
        ----------
        rotated : bool, optional
            It defaults to `False`. If it is `True`, it switches `axis`
            with `-v` to produce a rotated placement.

        Returns
        -------
        Base::Placement
            A placement, comprised of a `Base` (`Base::Vector3`),
            and a `Rotation` (`Base::Rotation`).
        """
        if rotated:
            m = DraftVecUtils.getPlaneRotation(self.u, self.axis)
        else:
            m = DraftVecUtils.getPlaneRotation(self.u, self.v)
        m.move(self.position)
        p = FreeCAD.Placement(m)
        # Arch active container if based on App Part
        # if FreeCAD.GuiUp:
        #    import FreeCADGui
        #    view = FreeCADGui.ActiveDocument.ActiveView
        #    a = view.getActiveObject("Arch")
        #    if a:
        #        p = a.Placement.inverse().multiply(p)
        return p

    def getNormal(self):
        """Return the normal vector of the plane (axis).

        Returns
        -------
        Base::Vector3
            The `axis` attribute of the plane.
        """
        n = self.axis
        # Arch active container if based on App Part
        # if FreeCAD.GuiUp:
        #    import FreeCADGui
        #    view = FreeCADGui.ActiveDocument.ActiveView
        #    a = view.getActiveObject("Arch")
        #    if a:
        #        n = a.Placement.inverse().Rotation.multVec(n)
        return n

    def setFromPlacement(self, pl, rebase=False):
        """Set the plane from a placement.

        It normally uses only the rotation, unless `rebase` is `True`.

        Parameters
        ----------
        pl : Base::Placement or Base::Matrix4D
            A placement, comprised of a `Base` (`Base::Vector3`),
            and a `Rotation` (`Base::Rotation`),
            or a `Base::Matrix4D` that defines a placement.
        rebase : bool, optional
            It defaults to `False`.
            If `True`, it will use `pl.Base` as the new `position`
            of the plane. Otherwise it will only consider `pl.Rotation`.

        To do
        -----
        If `pl` is a `Base::Matrix4D`, it shouldn't try to use `pl.Base`
        because a matrix has no `Base`.
        """
        rot = FreeCAD.Placement(pl).Rotation
        self.u = rot.multVec(FreeCAD.Vector(1, 0, 0))
        self.v = rot.multVec(FreeCAD.Vector(0, 1, 0))
        self.axis = rot.multVec(FreeCAD.Vector(0, 0, 1))
        if rebase:
            self.position = pl.Base

    def inverse(self):
        """Invert the direction of the plane.

        It inverts the `u` and `axis` vectors.
        """
        self.u = self.u.negative()
        self.axis = self.axis.negative()

    def save(self):
        """Store the plane attributes.

        Store `u`, `v`, `axis`, `position` and `weak`
        in a list in `stored`.
        """
        self.stored = [self.u, self.v, self.axis, self.position, self.weak]

    def restore(self):
        """Restore the plane attributes that were saved.

        Restores the attributes `u`, `v`, `axis`, `position` and `weak`
        from `stored`, and set `stored` to `None`.
        """
        if self.stored:
            self.u = self.stored[0]
            self.v = self.stored[1]
            self.axis = self.stored[2]
            self.position = self.stored[3]
            self.weak = self.stored[4]
            self.stored = None

    def getLocalCoords(self, point):
        """Return the coordinates of the given point, from the plane.

        If the `point` was constructed using the plane as origin,
        return the relative coordinates from the `point` to the plane.

        A vector is calculated from the plane's `position`
        to the external `point`, and this vector is projected onto
        each of the `u`, `v` and `axis` of the plane to determine
        the local, relative vector.

        Parameters
        ----------
        point : Base::Vector3
            The point external to the plane.

        Returns
        -------
        Base::Vector3
            The relative coordinates of the point from the plane.

        See Also
        --------
        getGlobalCoords, getLocalRot, getGlobalRot

        Notes
        -----
        The following graphic explains the coordinates.
        ::
                                  g GlobalCoords (1, 11)
                                  |
                                  |
                                  |
                              (n) p point (1, 6)
                                  | LocalCoords (1, 1)
                                  |
            ----plane--------c-------- position (0, 5)

        In the graphic

            * `p` is an arbitrary point, external to the plane
            * `c` is the plane's `position`
            * `g` is the global coordinates of `p` when added to the plane
            * `n` is the relative coordinates of `p` when referred to the plane

        To do
        -----
        Maybe a better name would be getRelativeCoords?
        """
        pt = point.sub(self.position)
        xv = DraftVecUtils.project(pt, self.u)
        x = xv.Length
        # If the angle between the projection xv and u
        # is larger than 1 radian (57.29 degrees), use the negative
        # of the magnitude. Why exactly 1 radian?
        if xv.getAngle(self.u) > 1:
            x = -x
        yv = DraftVecUtils.project(pt, self.v)
        y = yv.Length
        if yv.getAngle(self.v) > 1:
            y = -y
        zv = DraftVecUtils.project(pt, self.axis)
        z = zv.Length
        if zv.getAngle(self.axis) > 1:
            z = -z
        return Vector(x, y, z)

    def getGlobalCoords(self, point):
        """Return the coordinates of the given point, added to the plane.

        If the `point` was constructed using the plane as origin,
        return the absolute coordinates from the `point`
        to the global origin.

        The `u`, `v`, and `axis` vectors scale the components of `point`,
        and the result is added to the planes `position`.

        Parameters
        ----------
        point : Base::Vector3
            The external point.

        Returns
        -------
        Base::Vector3
            The coordinates of the point from the absolute origin.

        See Also
        --------
        getLocalCoords, getLocalRot, getGlobalRot

        Notes
        -----
        The following graphic explains the coordinates.
        ::
                                  g GlobalCoords (1, 11)
                                  |
                                  |
                                  |
                              (n) p point (1, 6)
                                  | LocalCoords (1, 1)
                                  |
            ----plane--------c-------- position (0, 5)

        In the graphic

            * `p` is an arbitrary point, external to the plane
            * `c` is the plane's `position`
            * `g` is the global coordinates of `p` when added to the plane
            * `n` is the relative coordinates of `p` when referred to the plane

        """
        vx = Vector(self.u).multiply(point.x)
        vy = Vector(self.v).multiply(point.y)
        vz = Vector(self.axis).multiply(point.z)
        pt = (vx.add(vy)).add(vz)
        return pt.add(self.position)

    def getLocalRot(self, point):
        """Like getLocalCoords, but doesn't use the plane's position.

        If the `point` was constructed using the plane as origin,
        return the relative coordinates from the `point` to the plane.
        However, in this case, the plane is assumed to have its `position`
        at the global origin, therefore, the returned coordinates
        will only consider the orientation of the plane.

        The external `point` is a vector, which is projected onto
        each of the `u`, `v` and `axis` of the plane to determine
        the local, relative vector.

        Parameters
        ----------
        point : Base::Vector3
            The point external to the plane.

        Returns
        -------
        Base::Vector3
            The relative coordinates of the point from the plane,
            if the plane had its `position` at the global origin.

        See Also
        --------
        getLocalCoords, getGlobalCoords, getGlobalRot
        """
        xv = DraftVecUtils.project(point, self.u)
        x = xv.Length
        if xv.getAngle(self.u) > 1:
            x = -x
        yv = DraftVecUtils.project(point, self.v)
        y = yv.Length
        if yv.getAngle(self.v) > 1:
            y = -y
        zv = DraftVecUtils.project(point, self.axis)
        z = zv.Length
        if zv.getAngle(self.axis) > 1:
            z = -z
        return Vector(x, y, z)

    def getGlobalRot(self, point):
        """Like getGlobalCoords, but doesn't use the plane's position.

        If the `point` was constructed using the plane as origin,
        return the absolute coordinates from the `point`
        to the global origin.
        However, in this case, the plane is assumed to have its `position`
        at the global origin, therefore, the returned coordinates
        will only consider the orientation of the plane.

        The `u`, `v`, and `axis` vectors scale the components of `point`.

        Parameters
        ----------
        point : Base::Vector3
            The external point.

        Returns
        -------
        Base::Vector3
            The coordinates of the point from the absolute origin.

        See Also
        --------
        getGlobalCoords, getLocalCoords, getLocalRot
        """
        vx = Vector(self.u).multiply(point.x)
        vy = Vector(self.v).multiply(point.y)
        vz = Vector(self.axis).multiply(point.z)
        pt = (vx.add(vy)).add(vz)
        return pt

    def getClosestAxis(self, point):
        """Return the closest axis of the plane to the given point (vector).

        It tests the angle that the `point` vector makes with the unit vectors
        `u`, `v`, and `axis`, as well their negatives.
        The smallest angle indicates the closest axis.

        Parameters
        ----------
        point : Base::Vector3
            The external point to test.

        Returns
        -------
        str
            * It is `'x'` if the closest axis is `u` or `-u`.
            * It is `'y'` if the closest axis is `v` or `-v`.
            * It is `'z'` if the closest axis is `axis` or `-axis`.
        """
        ax = point.getAngle(self.u)
        ay = point.getAngle(self.v)
        az = point.getAngle(self.axis)
        bx = point.getAngle(self.u.negative())
        by = point.getAngle(self.v.negative())
        bz = point.getAngle(self.axis.negative())
        b = min(ax, ay, az, bx, by, bz)
        if b in [ax, bx]:
            return "x"
        elif b in [ay, by]:
            return "y"
        elif b in [az, bz]:
            return "z"
        else:
            return None

    def isGlobal(self):
        """Return True if the plane axes are equal to the global axes.

        Return `False` if any of `u`, `v`, or `axis` does not correspond
        to `+X`, `+Y`, or `+Z`, respectively.
        """
        if self.u != Vector(1, 0, 0):
            return False
        if self.v != Vector(0, 1, 0):
            return False
        if self.axis != Vector(0, 0, 1):
            return False
        return True

    def isOrtho(self):
        """Return True if the plane axes are orthogonal with the global axes.

        Orthogonal means that the angle between `u` and the global axis `+Y`
        is a multiple of 90 degrees, meaning 0, -90, 90, -180, 180,
        -270, 270, or 360 degrees.
        And similarly for `v` and `axis`.
        All three axes should be orthogonal to the `+Y` axis.

        Due to rounding errors, the angle difference is rounded
        to 6 decimal digits to do the test.

        Returns
        -------
        bool
            Returns `True` if all three `u`, `v`, and `axis`
            are orthogonal with the global axis `+Y`.
            Otherwise it returns `False`.
        """
        ortho = [0, -1.570796, 1.570796,
                 -3.141593, 3.141593,
                 -4.712389, 4.712389, 6.283185]
        # Shouldn't the angle difference be calculated with
        # the other global axes `+X` and `+Z` as well?
        if round(self.u.getAngle(Vector(0, 1, 0)), 6) in ortho:
            if round(self.v.getAngle(Vector(0, 1, 0)), 6) in ortho:
                if round(self.axis.getAngle(Vector(0, 1, 0)), 6) in ortho:
                    return True
        return False

    def getDeviation(self):
        """Return the angle between the u axis and the horizontal plane.

        It defines a projection of `u` on the horizontal plane
        (without a Z component), and then measures the angle between
        this projection and `u`.

        It also considers the cross product of the projection
        and `u` to determine the sign of the angle.

        Returns
        -------
        float
            Angle between the `u` vector, and a projected vector
            on the global horizontal plane.

        See Also
        --------
        DraftVecUtils.angle
        """
        proj = Vector(self.u.x, self.u.y, 0)
        if self.u.getAngle(proj) == 0:
            return 0
        else:
            norm = proj.cross(self.u)
            return DraftVecUtils.angle(self.u, proj, norm)

    def getParameters(self):
        """Return a dictionary with the data which define the plane:
        `u`, `v`, `axis`, `weak`.

        Returns
        -------
        dict
            dictionary of the form:
            {"position":position, "u":x, "v":v, "axis":axis, "weak":weak}
        """
        return {"position":self.position, "u":self.u, "v":self.v, "axis":self.axis, "weak":self.weak}

    def setFromParameters(self, data):
        """Set the plane according to data.

        Parameters
        ----------
        data: dict
            dictionary of the form:
            {"position":position, "u":x, "v":v, "axis":axis, "weak":weak}
       """
        self.position = data["position"]
        self.u = data["u"]
        self.v = data["v"]
        self.axis = data["axis"]
        self.weak = data["weak"]

        return None

plane = Plane


# Compatibility function (V0.22, 2023):
def getPlacementFromPoints(points):
    """Return a placement from a list of 3 or 4 points. The 4th point is no longer used.

    Calls DraftGeomUtils.placement_from_points(). See there.
    """
    utils.use_instead("DraftGeomUtils.placement_from_points")
    return DraftGeomUtils.placement_from_points(*points[:3])


# Compatibility function (V0.22, 2023):
def getPlacementFromFace(face, rotated=False):
    """Return a placement from a face.

    Calls DraftGeomUtils.placement_from_face(). See there.
    """
    utils.use_instead("DraftGeomUtils.placement_from_face")
    return DraftGeomUtils.placement_from_face(face, rotated=rotated)
