# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
import struct
from typing import Any, Optional

from bpy.types import Mesh
from mathutils import Vector

from ..common.logger import get_logger

logger = get_logger(__name__)


class ExtMeshBmeshExporter:
    """Export extension for EXT_mesh_bmesh glTF extension."""

    def __init__(self, gltf_data: dict[str, Any], buffers: list[bytearray]) -> None:
        self.gltf_data = gltf_data
        self.buffers = buffers
        self.buffer_views = gltf_data.get("bufferViews", [])
        self.accessors = gltf_data.get("accessors", [])

    def should_export_bmesh(self, mesh: Mesh) -> bool:
        """Determine if mesh should be exported with EXT_mesh_bmesh."""
        # Check if mesh has complex topology (quads, n-gons)
        for polygon in mesh.polygons:
            if polygon.loop_total > 4 or polygon.loop_total == 4:  # n-gon
                return True
        return False

    def analyze_mesh_topology(self, mesh: Mesh) -> dict[str, Any]:
        """Analyze Blender mesh and extract BMesh-like topology."""
        bmesh_data = {
            "vertices": [],
            "edges": [],
            "loops": [],
            "faces": []
        }

        # Extract vertices
        for i, vertex in enumerate(mesh.vertices):
            bmesh_data["vertices"].append({
                "id": i,
                "position": vertex.co,
                "edges": [],
                "attributes": {}
            })

        # Extract edges
        edge_map = {}  # (v1, v2) -> edge_index
        for i, edge in enumerate(mesh.edges):
            v1, v2 = edge.vertices
            edge_key = tuple(sorted([v1, v2]))
            edge_map[edge_key] = i

            bmesh_data["edges"].append({
                "id": i,
                "vertices": [v1, v2],
                "faces": [],
                "attributes": {}
            })

        # Extract faces and loops
        loop_index = 0
        for face_index, polygon in enumerate(mesh.polygons):
            face_vertices = []
            face_loops = []

            # Get vertices for this face
            for loop_index_in_face in range(polygon.loop_total):
                loop = mesh.loops[polygon.loop_start + loop_index_in_face]
                vertex_index = loop.vertex_index
                face_vertices.append(vertex_index)

                # Create loop data
                loop_data = {
                    "id": loop_index,
                    "vertex": vertex_index,
                    "edge": self._find_edge_for_loop(
                        vertex_index, polygon, mesh, edge_map
                    ),
                    "face": face_index,
                    "next": (loop_index + 1) % polygon.loop_total + polygon.loop_start,
                    "prev": (loop_index - 1) % polygon.loop_total + polygon.loop_start,
                    "radial_next": loop_index,  # Simplified for now
                    "radial_prev": loop_index,  # Simplified for now
                    "attributes": {}
                }
                bmesh_data["loops"].append(loop_data)
                face_loops.append(loop_index)
                loop_index += 1

            # Create face data
            bmesh_data["faces"].append({
                "id": face_index,
                "vertices": face_vertices,
                "edges": self._get_face_edges(face_vertices, edge_map),
                "loops": face_loops,
                "normal": polygon.normal,
                "attributes": {}
            })

        return bmesh_data

    def _find_edge_for_loop(
        self,
        vertex_index: int,
        polygon: Any,
        mesh: Mesh,
        edge_map: dict[tuple[int, int], int]
    ) -> int:
        """Find the edge index for a loop."""
        # This is a simplified implementation
        # In a full implementation, we'd need to properly track edge-loop relationships
        return 0

    def _get_face_edges(self, face_vertices: list[int], edge_map: dict[tuple[int, int], int]) -> list[int]:
        """Get edge indices for a face."""
        edges = []
        num_vertices = len(face_vertices)
        for i in range(num_vertices):
            v1 = face_vertices[i]
            v2 = face_vertices[(i + 1) % num_vertices]
            edge_key = tuple(sorted([v1, v2]))
            if edge_key in edge_map:
                edges.append(edge_map[edge_key])
        return edges

    def create_buffer_view(self, data: bytes) -> int:
        """Create a buffer view and return its index."""
        # Align to 4-byte boundary
        while len(self.buffers[0]) % 4 != 0:
            self.buffers[0].append(0)

        buffer_view_index = len(self.buffer_views)
        byte_offset = len(self.buffers[0])

        buffer_view = {
            "buffer": 0,
            "byteOffset": byte_offset,
            "byteLength": len(data)
        }
        self.buffer_views.append(buffer_view)

        # Add data to buffer
        self.buffers[0].extend(data)

        return buffer_view_index

    def create_accessor(
        self,
        buffer_view_index: int,
        component_type: int,
        count: int,
        accessor_type: str,
        min_val: Optional[list[float]] = None,
        max_val: Optional[list[float]] = None
    ) -> int:
        """Create an accessor and return its index."""
        accessor_index = len(self.accessors)
        accessor = {
            "bufferView": buffer_view_index,
            "componentType": component_type,
            "count": count,
            "type": accessor_type
        }

        if min_val is not None:
            accessor["min"] = min_val
        if max_val is not None:
            accessor["max"] = max_val

        self.accessors.append(accessor)
        return accessor_index

    def pack_vector3_array(self, vectors: list[Vector]) -> bytes:
        """Pack array of Vector3 into bytes."""
        data = bytearray()
        for vec in vectors:
            data.extend(struct.pack("<fff", vec.x, vec.y, vec.z))
        return data

    def pack_uint_array(self, values: list[int]) -> bytes:
        """Pack array of unsigned integers into bytes."""
        data = bytearray()
        for value in values:
            data.extend(struct.pack("<I", value))
        return data

    def create_sparse_accessor(self, values: list[Any], component_type: int,
                              accessor_type: str) -> int:
        """Create a sparse accessor for efficient storage of mostly default values."""
        count = len(values)

        # Find non-default values
        components = {"VEC2": 2, "VEC3": 3, "VEC4": 4}.get(accessor_type, 1)
        default_value = 0 if accessor_type == "SCALAR" else [0] * components
        non_default_indices = []
        non_default_values = []

        for i, value in enumerate(values):
            if value != default_value:
                non_default_indices.append(i)
                non_default_values.append(value)

        if len(non_default_values) == 0:
            # All values are default, create regular accessor with single value
            if accessor_type == "SCALAR":
                data = struct.pack("<I", 0)
            else:
                components = {"VEC2": 2, "VEC3": 3, "VEC4": 4}.get(accessor_type, 1)
                data = struct.pack("<" + "I" * components, *[0] * components)

            buffer_view_index = self.create_buffer_view(data)
            return self.create_accessor(buffer_view_index, component_type, 1, accessor_type)

        # Create sparse accessor
        # Pack indices
        indices_data = self.pack_uint_array(non_default_indices)
        indices_buffer_view = self.create_buffer_view(indices_data)

        # Pack values
        if accessor_type == "SCALAR":
            values_data = self.pack_uint_array(non_default_values)
        else:
            components = {"VEC2": 2, "VEC3": 3, "VEC4": 4}.get(accessor_type, 1)
            values_data = bytearray()
            for value in non_default_values:
                if isinstance(value, list):
                    values_data.extend(struct.pack("<" + "f" * components, *value))
                else:
                    values_data.extend(struct.pack("<f", float(value)))
        values_buffer_view = self.create_buffer_view(values_data)

        # Create accessor
        accessor_index = len(self.accessors)
        accessor = {
            "componentType": component_type,
            "count": count,
            "type": accessor_type,
            "sparse": {
                "count": len(non_default_values),
                "indices": {
                    "bufferView": indices_buffer_view,
                    "componentType": 5125  # UNSIGNED_INT
                },
                "values": {
                    "bufferView": values_buffer_view
                }
            }
        }
        self.accessors.append(accessor)

        logger.info(
            "Created sparse accessor with %d/%d non-default values",
            len(non_default_values),
            count
        )
        return accessor_index

    def export_bmesh_topology(self, bmesh_data: dict[str, Any]) -> dict[str, Any]:
        """Export BMesh topology to EXT_mesh_bmesh format."""
        extension_data = {}

        # Export vertices
        if bmesh_data["vertices"]:
            vertices_data = {}
            vertex_count = len(bmesh_data["vertices"])

            # Pack vertex positions
            positions = [v["position"] for v in bmesh_data["vertices"]]
            positions_data = self.pack_vector3_array(positions)
            positions_buffer_view = self.create_buffer_view(positions_data)
            positions_accessor = self.create_accessor(
                positions_buffer_view, 5126, vertex_count, "VEC3"  # FLOAT, VEC3
            )

            vertices_data["count"] = vertex_count
            vertices_data["positions"] = positions_accessor

            extension_data["vertices"] = vertices_data

        # Export edges
        if bmesh_data["edges"]:
            edges_data = {}
            edge_count = len(bmesh_data["edges"])

            # Pack edge vertices
            edge_vertices = []
            for edge in bmesh_data["edges"]:
                edge_vertices.extend(edge["vertices"])
            edge_vertices_data = self.pack_uint_array(edge_vertices)
            edge_vertices_buffer_view = self.create_buffer_view(edge_vertices_data)
            edge_vertices_accessor = self.create_accessor(
                edge_vertices_buffer_view, 5125, len(edge_vertices), "SCALAR"  # UNSIGNED_INT
            )

            edges_data["count"] = edge_count
            edges_data["vertices"] = edge_vertices_accessor

            extension_data["edges"] = edges_data

        # Export loops
        if bmesh_data["loops"]:
            loops_data = {}
            loop_count = len(bmesh_data["loops"])

            # Pack topology data
            topology_vertex = [loop["vertex"] for loop in bmesh_data["loops"]]
            topology_edge = [loop["edge"] for loop in bmesh_data["loops"]]
            topology_face = [loop["face"] for loop in bmesh_data["loops"]]
            topology_next = [loop["next"] for loop in bmesh_data["loops"]]
            topology_prev = [loop["prev"] for loop in bmesh_data["loops"]]
            topology_radial_next = [loop["radial_next"] for loop in bmesh_data["loops"]]
            topology_radial_prev = [loop["radial_prev"] for loop in bmesh_data["loops"]]

            # Create sparse accessors for topology
            loops_data["count"] = loop_count
            loops_data["topology_vertex"] = self.create_sparse_accessor(
                topology_vertex, 5125, "SCALAR"  # UNSIGNED_INT
            )
            loops_data["topology_edge"] = self.create_sparse_accessor(
                topology_edge, 5125, "SCALAR"
            )
            loops_data["topology_face"] = self.create_sparse_accessor(
                topology_face, 5125, "SCALAR"
            )
            loops_data["topology_next"] = self.create_sparse_accessor(
                topology_next, 5125, "SCALAR"
            )
            loops_data["topology_prev"] = self.create_sparse_accessor(
                topology_prev, 5125, "SCALAR"
            )
            loops_data["topology_radial_next"] = self.create_sparse_accessor(
                topology_radial_next, 5125, "SCALAR"
            )
            loops_data["topology_radial_prev"] = self.create_sparse_accessor(
                topology_radial_prev, 5125, "SCALAR"
            )

            extension_data["loops"] = loops_data

        # Export faces
        if bmesh_data["faces"]:
            faces_data = {}
            face_count = len(bmesh_data["faces"])

            # Pack face vertices (variable-length)
            all_face_vertices = []
            face_offsets = []
            vertex_offset = 0

            for face in bmesh_data["faces"]:
                face_vertices = face["vertices"]
                all_face_vertices.extend(face_vertices)
                face_offsets.append([vertex_offset, vertex_offset + len(face_vertices), vertex_offset])
                vertex_offset += len(face_vertices)

            face_vertices_data = self.pack_uint_array(all_face_vertices)
            face_vertices_buffer_view = self.create_buffer_view(face_vertices_data)
            face_vertices_accessor = self.create_accessor(
                face_vertices_buffer_view, 5125, len(all_face_vertices), "SCALAR"
            )

            # Pack face offsets
            offsets_data = bytearray()
            for offset in face_offsets:
                offsets_data.extend(struct.pack("<III", *offset))
            offsets_buffer_view = self.create_buffer_view(offsets_data)
            offsets_accessor = self.create_accessor(
                offsets_buffer_view, 5125, face_count, "VEC3"  # UNSIGNED_INT, VEC3
            )

            faces_data["count"] = face_count
            faces_data["vertices"] = face_vertices_accessor
            faces_data["offsets"] = offsets_accessor

            extension_data["faces"] = faces_data

        return extension_data

    def export_mesh(self, mesh: Mesh, mesh_name: str) -> Optional[dict[str, Any]]:
        """Export a mesh with EXT_mesh_bmesh extension."""
        if not self.should_export_bmesh(mesh):
            return None

        try:
            # Analyze mesh topology
            bmesh_data = self.analyze_mesh_topology(mesh)

            # Export BMesh topology
            extension_data = self.export_bmesh_topology(bmesh_data)

            logger.info("Successfully exported EXT_mesh_bmesh for mesh: %s", mesh_name)
            return extension_data

        except Exception:
            logger.exception("Failed to export EXT_mesh_bmesh for mesh '%s'", mesh_name)
            return None
