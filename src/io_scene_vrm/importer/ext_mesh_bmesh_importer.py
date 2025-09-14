# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
import struct
from typing import Any, Optional

import bpy
from bpy.types import Mesh
from mathutils import Vector

from ..common.logger import get_logger

logger = get_logger(__name__)


class ExtMeshBmeshImporter:
    """Import extension for EXT_mesh_bmesh glTF extension."""

    def __init__(self, gltf_data: dict[str, Any], buffers: list[bytes]) -> None:
        self.gltf_data = gltf_data
        self.buffers = buffers
        self.extension_data: Optional[dict[str, Any]] = None

    def is_supported(self, primitive: dict[str, Any]) -> bool:
        """Check if primitive has EXT_mesh_bmesh extension."""
        extensions = primitive.get("extensions", {})
        return "EXT_mesh_bmesh" in extensions

    def get_extension_data(self, primitive: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Get EXT_mesh_bmesh extension data from primitive."""
        extensions = primitive.get("extensions", {})
        return extensions.get("EXT_mesh_bmesh")

    def read_buffer_view(self, buffer_view_index: int) -> bytes:
        """Read data from a buffer view."""
        if buffer_view_index >= len(self.gltf_data.get("bufferViews", [])):
            msg = "Invalid buffer view index: %d" % buffer_view_index
            raise ValueError(msg)

        buffer_view = self.gltf_data["bufferViews"][buffer_view_index]
        buffer_index = buffer_view["buffer"]
        byte_offset = buffer_view.get("byteOffset", 0)
        byte_length = buffer_view["byteLength"]

        if buffer_index >= len(self.buffers):
            msg = "Invalid buffer index: %d" % buffer_index
            raise ValueError(msg)

        buffer_data = self.buffers[buffer_index]
        return buffer_data[byte_offset:byte_offset + byte_length]

    def read_accessor_data(self, accessor_index: int) -> tuple[list[Any], str]:
        """Read accessor data and return values and component type."""
        if accessor_index >= len(self.gltf_data.get("accessors", [])):
            msg = "Invalid accessor index: %d" % accessor_index
            raise ValueError(msg)

        accessor = self.gltf_data["accessors"][accessor_index]
        buffer_view_index = accessor["bufferView"]
        component_type = accessor["componentType"]
        count = accessor["count"]
        accessor_type = accessor["type"]

        buffer_data = self.read_buffer_view(buffer_view_index)
        byte_offset = accessor.get("byteOffset", 0)

        # Map component type to struct format
        type_map = {
            5120: ("b", 1),  # BYTE
            5121: ("B", 1),  # UNSIGNED_BYTE
            5122: ("h", 2),  # SHORT
            5123: ("H", 2),  # UNSIGNED_SHORT
            5125: ("I", 4),  # UNSIGNED_INT
            5126: ("f", 4),  # FLOAT
        }

        if component_type not in type_map:
            msg = "Unsupported component type: %d" % component_type
            raise ValueError(msg)

        format_char, byte_size = type_map[component_type]

        # Calculate components per element
        if accessor_type == "SCALAR":
            components = 1
        elif accessor_type == "VEC2":
            components = 2
        elif accessor_type == "VEC3":
            components = 3
        elif accessor_type == "VEC4":
            components = 4
        else:
            msg = "Unsupported accessor type: %s" % accessor_type
            raise ValueError(msg)

        # Read data
        values = []
        for i in range(count):
            offset = byte_offset + i * components * byte_size
            if accessor_type == "SCALAR":
                value = struct.unpack_from(format_char, buffer_data, offset)[0]
                values.append(value)
            else:
                value = struct.unpack_from(
                    format_char * components, buffer_data, offset
                )
                values.append(list(value))

        return values, accessor_type

    def read_sparse_accessor(self, accessor_index: int) -> list[Any]:
        """Read sparse accessor data."""
        if accessor_index >= len(self.gltf_data.get("accessors", [])):
            msg = "Invalid accessor index: %d" % accessor_index
            raise ValueError(msg)

        accessor = self.gltf_data["accessors"][accessor_index]
        sparse = accessor.get("sparse")
        if not sparse:
            # Not a sparse accessor, read normally
            values, _ = self.read_accessor_data(accessor_index)
            return values

        count = accessor["count"]
        accessor_type = accessor["type"]

        # Read base values (if any)
        base_values = []
        if "bufferView" in accessor:
            base_values, _ = self.read_accessor_data(accessor_index)

        # Ensure we have enough base values
        while len(base_values) < count:
            if accessor_type == "SCALAR":
                base_values.append(0)
            else:
                components = {"VEC2": 2, "VEC3": 3, "VEC4": 4}.get(accessor_type, 1)
                base_values.append([0] * components)

        # Read sparse overrides
        sparse_indices = sparse["indices"]
        sparse_values = sparse["values"]

        indices_data, _ = self.read_accessor_data(sparse_indices["bufferView"])
        values_data, _ = self.read_accessor_data(sparse_values["bufferView"])

        # Apply sparse overrides
        for i, index in enumerate(indices_data):
            if index < count:
                base_values[index] = values_data[i]

        return base_values

    def reconstruct_bmesh_topology(self, extension_data: dict[str, Any]) -> dict[str, Any]:
        """Reconstruct BMesh topology from EXT_mesh_bmesh data."""
        bmesh_data = {
            "vertices": [],
            "edges": [],
            "loops": [],
            "faces": []
        }

        # Read vertices
        if "vertices" in extension_data:
            vertices_data = extension_data["vertices"]
            vertex_count = vertices_data["count"]

            # Read vertex positions
            if "positions" in vertices_data:
                positions = self.read_sparse_accessor(vertices_data["positions"])
                for i in range(vertex_count):
                    if i < len(positions):
                        pos = positions[i]
                        if isinstance(pos, list) and len(pos) >= 3:
                            bmesh_data["vertices"].append({
                                "id": i,
                                "position": Vector((pos[0], pos[1], pos[2])),
                                "edges": [],
                                "attributes": {}
                            })
                        else:
                            bmesh_data["vertices"].append({
                                "id": i,
                                "position": Vector((0, 0, 0)),
                                "edges": [],
                                "attributes": {}
                            })
                    else:
                        bmesh_data["vertices"].append({
                            "id": i,
                            "position": Vector((0, 0, 0)),
                            "edges": [],
                            "attributes": {}
                        })

        # Read edges
        if "edges" in extension_data:
            edges_data = extension_data["edges"]
            edge_count = edges_data["count"]

            # Read edge vertices
            if "vertices" in edges_data:
                edge_vertices = self.read_sparse_accessor(edges_data["vertices"])
                for i in range(edge_count):
                    if i < len(edge_vertices) and isinstance(edge_vertices[i], list) and len(edge_vertices[i]) >= 2:
                        v1, v2 = edge_vertices[i][:2]
                        bmesh_data["edges"].append({
                            "id": i,
                            "vertices": [int(v1), int(v2)],
                            "faces": [],
                            "attributes": {}
                        })
                    else:
                        bmesh_data["edges"].append({
                            "id": i,
                            "vertices": [0, 0],
                            "faces": [],
                            "attributes": {}
                        })

        # Read loops
        if "loops" in extension_data:
            loops_data = extension_data["loops"]
            loop_count = loops_data["count"]

            # Read loop topology
            topology_vertex = []
            topology_edge = []
            topology_face = []
            topology_next = []
            topology_prev = []
            topology_radial_next = []
            topology_radial_prev = []

            if "topology_vertex" in loops_data:
                topology_vertex = self.read_sparse_accessor(loops_data["topology_vertex"])
            if "topology_edge" in loops_data:
                topology_edge = self.read_sparse_accessor(loops_data["topology_edge"])
            if "topology_face" in loops_data:
                topology_face = self.read_sparse_accessor(loops_data["topology_face"])
            if "topology_next" in loops_data:
                topology_next = self.read_sparse_accessor(loops_data["topology_next"])
            if "topology_prev" in loops_data:
                topology_prev = self.read_sparse_accessor(loops_data["topology_prev"])
            if "topology_radial_next" in loops_data:
                topology_radial_next = self.read_sparse_accessor(loops_data["topology_radial_next"])
            if "topology_radial_prev" in loops_data:
                topology_radial_prev = self.read_sparse_accessor(loops_data["topology_radial_prev"])

            for i in range(loop_count):
                loop_data = {
                    "id": i,
                    "vertex": int(topology_vertex[i]) if i < len(topology_vertex) else 0,
                    "edge": int(topology_edge[i]) if i < len(topology_edge) else 0,
                    "face": int(topology_face[i]) if i < len(topology_face) else 0,
                    "next": int(topology_next[i]) if i < len(topology_next) else i,
                    "prev": int(topology_prev[i]) if i < len(topology_prev) else i,
                    "radial_next": int(topology_radial_next[i]) if i < len(topology_radial_next) else i,
                    "radial_prev": int(topology_radial_prev[i]) if i < len(topology_radial_prev) else i,
                    "attributes": {}
                }
                bmesh_data["loops"].append(loop_data)

        # Read faces
        if "faces" in extension_data:
            faces_data = extension_data["faces"]
            face_count = faces_data["count"]

            # Read face topology
            if "vertices" in faces_data and "offsets" in faces_data:
                face_vertices = self.read_sparse_accessor(faces_data["vertices"])
                face_offsets = self.read_sparse_accessor(faces_data["offsets"])

                for i in range(face_count):
                    if i < len(face_offsets) and isinstance(face_offsets[i], list) and len(face_offsets[i]) >= 3:
                        vertex_start = int(face_offsets[i][0])
                        vertex_end = int(face_offsets[i][1])
                        loop_start = int(face_offsets[i][2]) if len(face_offsets[i]) > 2 else vertex_start

                        vertices = []
                        for j in range(vertex_start, vertex_end):
                            if j < len(face_vertices):
                                vertices.append(int(face_vertices[j]))

                        bmesh_data["faces"].append({
                            "id": i,
                            "vertices": vertices,
                            "edges": [],
                            "loops": list(range(loop_start, loop_start + len(vertices))),
                            "normal": Vector((0, 0, 1)),
                            "attributes": {}
                        })
                    else:
                        bmesh_data["faces"].append({
                            "id": i,
                            "vertices": [],
                            "edges": [],
                            "loops": [],
                            "normal": Vector((0, 0, 1)),
                            "attributes": {}
                        })

        return bmesh_data

    def create_blender_mesh_from_bmesh(self, bmesh_data: dict[str, Any], mesh_name: str) -> Mesh:
        """Create a Blender mesh from reconstructed BMesh data."""
        mesh = bpy.data.meshes.new(mesh_name)

        # Create vertices
        vertices = []
        for vertex in bmesh_data["vertices"]:
            vertices.append(vertex["position"])
        mesh.from_pydata(vertices, [], [])

        # Create faces from BMesh topology
        faces = []
        for face in bmesh_data["faces"]:
            if len(face["vertices"]) >= 3:
                faces.append(face["vertices"])

        if faces:
            mesh.from_pydata(vertices, [], faces)

        # Update mesh
        mesh.update()

        logger.info(
            "Created Blender mesh '%s' with %d vertices and %d faces",
            mesh_name,
            len(vertices),
            len(faces)
        )
        return mesh

    def import_primitive(self, primitive: dict[str, Any], mesh_name: str) -> Optional[Mesh]:
        """Import a primitive with EXT_mesh_bmesh extension."""
        extension_data = self.get_extension_data(primitive)
        if not extension_data:
            return None

        try:
            # Reconstruct BMesh topology
            bmesh_data = self.reconstruct_bmesh_topology(extension_data)

            # Create Blender mesh
            mesh = self.create_blender_mesh_from_bmesh(bmesh_data, mesh_name)

            logger.info("Successfully imported EXT_mesh_bmesh primitive: %s", mesh_name)
            return mesh

        except Exception:
            logger.exception("Failed to import EXT_mesh_bmesh primitive '%s'", mesh_name)
            return None
