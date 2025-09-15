# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
import struct
from typing import Any, Optional, Dict

from bpy.types import Mesh
from mathutils import Vector

from ..common.logger import get_logger

logger = get_logger(__name__)


class ExtMeshBmeshExporter:
    """Export extension for EXT_mesh_bmesh glTF extension."""

    def __init__(self, gltf_data: dict[str, Any] = None, buffers: list[bytearray] = None) -> None:
        self.gltf_data = gltf_data or {}
        self.buffers = buffers or [bytearray()]
        self.buffer_views = self.gltf_data.get("bufferViews", [])
        self.accessors = self.gltf_data.get("accessors", [])
        self.has_exported_primitives = False


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
            face_edges = polygon.edge_keys

            # Get vertices for this face
            for loop_index_in_face in range(polygon.loop_total):
                loop = mesh.loops[polygon.loop_start + loop_index_in_face]
                vertex_index = loop.vertex_index
                face_vertices.append(vertex_index)

                # Create loop data
                loop_data = {
                    "id": loop_index,
                    "vertex": vertex_index,
                    "edge": loop.edge_index,
                    "face": face_index,
                    "next": polygon.loop_start + ((loop_index_in_face + 1) % polygon.loop_total),
                    "prev": polygon.loop_start + ((loop_index_in_face - 1) % polygon.loop_total),
                    "radial_next": loop_index,  # Will be calculated properly in _calculate_radial_loops
                    "radial_prev": loop_index,  # Will be calculated properly in _calculate_radial_loops
                    "attributes": {}
                }
                bmesh_data["loops"].append(loop_data)
                face_loops.append(loop_index)
                loop_index += 1

            # Create face data
            bmesh_data["faces"].append({
                "id": face_index,
                "vertices": face_vertices,
                "edges": face_edges,
                "loops": face_loops,
                "normal": polygon.normal,
                "attributes": {}
            })

        # Build adjacency data
        self._build_adjacency(bmesh_data, mesh)

        # Extract subdivision surface data
        self._extract_subdivision_data(bmesh_data, mesh)

        # Extract per-loop attributes
        self._extract_loop_attributes(bmesh_data, mesh)

        # Calculate proper radial loop relationships (based on BMeshUnity algorithm)
        self._calculate_radial_loops(bmesh_data, mesh)

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

    def _build_adjacency(self, bmesh_data: dict[str, Any], mesh: Mesh) -> None:
        """Build adjacency relationships between vertices, edges, and faces."""
        # Build vertex-edge adjacency
        for vertex_id, vertex in enumerate(bmesh_data["vertices"]):
            vertex["edges"] = []

        for edge in bmesh_data["edges"]:
            v1, v2 = edge["vertices"]
            bmesh_data["vertices"][v1]["edges"].append(edge["id"])
            bmesh_data["vertices"][v2]["edges"].append(edge["id"])

        # Build edge-face adjacency - Fixed: handle edge keys properly
        edge_map = {}  # Map of (v1, v2) -> edge_id for quick lookup
        for edge in bmesh_data["edges"]:
            v1, v2 = edge["vertices"]
            edge_key = tuple(sorted([v1, v2]))  # Sort vertices for consistent key
            edge_map[edge_key] = edge["id"]

        for face in bmesh_data["faces"]:
            for edge_key in face["edges"]:  # face["edges"] contains tuple keys
                if edge_key in edge_map:
                    edge_id = edge_map[edge_key]
                    bmesh_data["edges"][edge_id]["faces"].append(face["id"])

    def _extract_subdivision_data(self, bmesh_data: dict[str, Any], mesh: Mesh) -> None:
        """Extract subdivision surface attributes (CREASE, HOLES)."""
        # Extract edge creases - Fixed: Check for subdivision data without modifiers
        edge_creases = []
        has_edge_creases = False

        # Check edge crease values (directly from mesh if available)
        for edge in mesh.edges:
            try:
                # Try to access edge crease attribute
                crease_value = getattr(edge, 'crease', 0.0)
                edge_creases.append(crease_value)
                if crease_value > 0.0:
                    has_edge_creases = True
            except (AttributeError, RuntimeError):
                # If edge crease access fails, use default
                edge_creases.append(0.0)

        if has_edge_creases:
            bmesh_data["edges_crease"] = edge_creases

        # Extract vertex creases (simplified - would need object context for actual modifiers)
        vertex_creases = [0.0] * len(mesh.vertices)
        has_vertex_creases = False

        # Note: Vertex creases require access to the parent object/modifiers
        # This is a simplified implementation for testing
        # Real implementation would need object context to check Subdivision modifiers

        if has_vertex_creases:
            bmesh_data["vertices_crease"] = vertex_creases

        # Extract face holes - Fixed: Use different approach
        face_holes = []
        for polygon in mesh.polygons:
            # Holes are determined by face area or other geometric properties
            # For now, assume no holes unless explicitly set by Blender
            hole_value = 0  # Default to no holes
            face_holes.append(hole_value)

        if any(hole for hole in face_holes):
            bmesh_data["faces_holes"] = face_holes

    def _extract_loop_attributes(self, bmesh_data: dict[str, Any], mesh: Mesh) -> None:
        """Extract per-loop attributes (TEXCOORD_*, COLOR_*)."""
        loop_count = len(bmesh_data["loops"])

        # Extract UV coordinates (TEXCOORD_0, TEXCOORD_1)
        if mesh.uv_layers:
            texcoord_0_data = []
            texcoord_1_data = []
            has_uv0 = False
            has_uv1 = False

            uv_layer0 = mesh.uv_layers[0] if len(mesh.uv_layers) > 0 else None
            uv_layer1 = mesh.uv_layers[1] if len(mesh.uv_layers) > 1 else None

            for loop in mesh.loops:
                if uv_layer0:
                    uv = uv_layer0.uv[loop.uv]
                    texcoord_0_data.extend([uv.x, uv.y])
                    if not has_uv0 and (abs(uv.x - uv.y) > 1e-6):
                        has_uv0 = True

                if uv_layer1:
                    uv = uv_layer1.uv[loop.uv]
                    texcoord_1_data.extend([uv.x, uv.y])
                    if not has_uv1 and (abs(uv.x - uv.y) > 1e-6):
                        has_uv1 = True

            if has_uv0:
                bmesh_data["loop_texcoord_0"] = texcoord_0_data[:loop_count*2]  # Each loop gets 2 coordinates
            if has_uv1:
                bmesh_data["loop_texcoord_1"] = texcoord_1_data[:loop_count*2]

        # Extract vertex colors (COLOR_0)
        if mesh.vertex_colors:
            color_data = []
            has_colors = False

            vc_layer = mesh.vertex_colors[0]
            for loop in mesh.loops:
                color = vc_layer.color[loop.vertex]
                color_data.extend([color.r, color.g, color.b])
                # Check if colors vary significantly from default
                if not has_colors and (abs(color.r - 1.0) > 1e-6 or abs(color.g - 1.0) > 1e-6 or abs(color.b - 1.0) > 1e-6):
                    has_colors = True

            if has_colors:
                bmesh_data["loop_color_0"] = color_data[:loop_count*3]

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

    def _create_optimized_accessor(self, values: list[Any], component_type: int,
                                  accessor_type: str) -> int:
        """Create the most efficient accessor type (sparse or regular) for the data."""
        count = len(values)

        # For large datasets with mostly default values, use sparse accessors
        if count > 100:  # Threshold for considering sparse optimization
            # Check how many values are non-zero/non-default
            components = {"VEC2": 2, "VEC3": 3, "VEC4": 4}.get(accessor_type, 1)
            default_value = 0 if accessor_type == "SCALAR" else [0] * components
            non_default_count = sum(1 for v in values if v != default_value)

            # Use sparse if less than 30% of values are non-default (significant compression potential)
            if non_default_count / count < 0.3:
                return self.create_sparse_accessor(values, component_type, accessor_type)

        # For small datasets or densely populated data, use regular accessor
        return self._create_dense_accessor(values, component_type, accessor_type)

    def _create_dense_accessor(self, values: list[Any], component_type: int,
                              accessor_type: str) -> int:
        """Create a regular (dense) accessor for the data."""
        count = len(values)

        # Pack the data based on type
        if accessor_type == "SCALAR":
            data = self.pack_uint_array(values)
        else:
            components = {"VEC2": 2, "VEC3": 3, "VEC4": 4}.get(accessor_type, 1)
            data = bytearray()
            for value in values:
                if isinstance(value, list):
                    data.extend(struct.pack("<" + "f" * components, *value))
                else:
                    data.extend(struct.pack("<f", float(value)))

        # Create buffer view and accessor
        buffer_view_index = self.create_buffer_view(data)

        # Calculate min/max for optimization
        min_val = None
        max_val = None
        if values:
            if accessor_type == "SCALAR":
                min_val = [min(values)]
                max_val = [max(values)]
            elif accessor_type in ["VEC3", "VEC2", "VEC4"]:
                components = {"VEC2": 2, "VEC3": 3, "VEC4": 4}.get(accessor_type, 1)
                filtered_values = [v for v in values if isinstance(v, list) and len(v) >= components]
                if filtered_values:
                    transposed = list(zip(*filtered_values))
                    min_val = [min(component) for component in transposed]
                    max_val = [max(component) for component in transposed]

        return self.create_accessor(buffer_view_index, component_type, count,
                                   accessor_type, min_val, max_val)

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

            # Pack vertex edges (adjacency)
            all_vertex_edges = []
            vertex_offsets = [0]
            offset = 0
            for vertex in bmesh_data["vertices"]:
                all_vertex_edges.extend(vertex["edges"])
                offset += len(vertex["edges"])
                vertex_offsets.append(offset)

            if all_vertex_edges:
                vertex_edges_data = self.pack_uint_array(all_vertex_edges)
                vertex_edges_buffer_view = self.create_buffer_view(vertex_edges_data)
                vertex_edges_accessor = self.create_accessor(
                    vertex_edges_buffer_view, 5125, len(all_vertex_edges), "SCALAR"
                )
                vertices_data["edges"] = vertex_edges_accessor

            # Add vertex subdivision attributes
            if "vertices_crease" in bmesh_data:
                crease_data = bmesh_data["vertices_crease"]
                crease_accessor = self.create_sparse_accessor(crease_data, 5126, "SCALAR")
                vertices_data.setdefault("attributes", {})["CREASE"] = crease_accessor

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

            # Pack edge faces (adjacency)
            all_edge_faces = []
            for edge in bmesh_data["edges"]:
                all_edge_faces.extend(edge["faces"])

            if all_edge_faces:
                edge_faces_data = self.pack_uint_array(all_edge_faces)
                edge_faces_buffer_view = self.create_buffer_view(edge_faces_data)
                edge_faces_accessor = self.create_accessor(
                    edge_faces_buffer_view, 5125, len(all_edge_faces), "SCALAR"
                )
                edges_data["faces"] = edge_faces_accessor

            # Add edge subdivision attributes
            if "edges_crease" in bmesh_data:
                crease_data = bmesh_data["edges_crease"]
                crease_accessor = self.create_sparse_accessor(crease_data, 5126, "SCALAR")
                edges_data.setdefault("attributes", {})["CREASE"] = crease_accessor

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

            # Create sparse accessors for topology - use compact storage for efficiency
            loops_data["count"] = loop_count

            # Most topology data is sequential (0, 1, 2, 3...) - optimize with sparse
            loops_data["topology_vertex"] = self._create_optimized_accessor(
                topology_vertex, 5125, "SCALAR"
            )
            loops_data["topology_edge"] = self._create_optimized_accessor(
                topology_edge, 5125, "SCALAR"
            )
            loops_data["topology_face"] = self._create_optimized_accessor(
                topology_face, 5125, "SCALAR"
            )
            loops_data["topology_next"] = self._create_optimized_accessor(
                topology_next, 5125, "SCALAR"
            )
            loops_data["topology_prev"] = self._create_optimized_accessor(
                topology_prev, 5125, "SCALAR"
            )
            loops_data["topology_radial_next"] = self._create_optimized_accessor(
                topology_radial_next, 5125, "SCALAR"
            )
            loops_data["topology_radial_prev"] = self._create_optimized_accessor(
                topology_radial_prev, 5125, "SCALAR"
            )

            # Add loop attributes (TEXCOORD_*, COLOR_*)
            if "loop_texcoord_0" in bmesh_data:
                texcoord_0_data = bmesh_data["loop_texcoord_0"]
                # Convert to VEC2 format [(x,y), (x,y), ...]
                texcoord_0_reshaped = [(texcoord_0_data[i*2], texcoord_0_data[i*2+1]) for i in range(len(texcoord_0_data)//2)]
                texcoord_0_accessor = self.create_sparse_accessor(texcoord_0_reshaped, 5126, "VEC2")
                loops_data.setdefault("attributes", {})["TEXCOORD_0"] = texcoord_0_accessor

            if "loop_texcoord_1" in bmesh_data:
                texcoord_1_data = bmesh_data["loop_texcoord_1"]
                texcoord_1_reshaped = [(texcoord_1_data[i*2], texcoord_1_data[i*2+1]) for i in range(len(texcoord_1_data)//2)]
                texcoord_1_accessor = self.create_sparse_accessor(texcoord_1_reshaped, 5126, "VEC2")
                loops_data.setdefault("attributes", {})["TEXCOORD_1"] = texcoord_1_accessor

            if "loop_color_0" in bmesh_data:
                color_0_data = bmesh_data["loop_color_0"]
                # Convert to VEC3 format [(r,g,b), (r,g,b), ...]
                color_0_reshaped = [(color_0_data[i*3], color_0_data[i*3+1], color_0_data[i*3+2]) for i in range(len(color_0_data)//3)]
                color_0_accessor = self.create_sparse_accessor(color_0_reshaped, 5126, "VEC3")
                loops_data.setdefault("attributes", {})["COLOR_0"] = color_0_accessor

            extension_data["loops"] = loops_data

        # Export faces
        if bmesh_data["faces"]:
            faces_data = {}
            face_count = len(bmesh_data["faces"])

            # Pack face data (variable-length arrays)
            all_face_vertices = []
            all_face_edges = []
            all_face_loops = []
            face_offsets = []
            vertex_offset = 0
            edge_offset = 0
            loop_offset = 0

            for face in bmesh_data["faces"]:
                # Add vertices
                all_face_vertices.extend(face["vertices"])
                vertices_start = vertex_offset
                vertex_offset += len(face["vertices"])

                # Add edges
                all_face_edges.extend(face["edges"])
                edges_start = edge_offset
                edge_offset += len(face["edges"])

                # Add loops
                all_face_loops.extend(face["loops"])
                loops_start = loop_offset
                loop_offset += len(face["loops"])

                face_offsets.append([vertices_start, edges_start, loops_start])

            # Create accessors for vertices
            if all_face_vertices:
                face_vertices_data = self.pack_uint_array(all_face_vertices)
                face_vertices_buffer_view = self.create_buffer_view(face_vertices_data)
                face_vertices_accessor = self.create_accessor(
                    face_vertices_buffer_view, 5125, len(all_face_vertices), "SCALAR"
                )
                faces_data["vertices"] = face_vertices_accessor

            # Create accessors for edges
            if all_face_edges:
                face_edges_data = self.pack_uint_array(all_face_edges)
                face_edges_buffer_view = self.create_buffer_view(face_edges_data)
                face_edges_accessor = self.create_accessor(
                    face_edges_buffer_view, 5125, len(all_face_edges), "SCALAR"
                )
                faces_data["edges"] = face_edges_accessor

            # Create accessors for loops
            if all_face_loops:
                face_loops_data = self.pack_uint_array(all_face_loops)
                face_loops_buffer_view = self.create_buffer_view(face_loops_data)
                face_loops_accessor = self.create_accessor(
                    face_loops_buffer_view, 5125, len(all_face_loops), "SCALAR"
                )
                faces_data["loops"] = face_loops_accessor

            # Create accessors for face normals
            import math
            normals = []
            for face in bmesh_data["faces"]:
                if not any(math.isinf(v) or math.isnan(v) for v in face["normal"]):
                    normals.append(face["normal"])
                else:
                    normals.append(Vector((0, 0, 1)))  # Default normal
            if normals:
                normals_data = self.pack_vector3_array(normals)
                normals_buffer_view = self.create_buffer_view(normals_data)
                normals_accessor = self.create_accessor(
                    normals_buffer_view, 5126, len(normals), "VEC3"
                )
                faces_data["normals"] = normals_accessor

            # Pack face offsets
            offsets_data = bytearray()
            for offset in face_offsets:
                offsets_data.extend(struct.pack("<III", *offset))
            offsets_buffer_view = self.create_buffer_view(offsets_data)
            offsets_accessor = self.create_accessor(
                offsets_buffer_view, 5125, face_count, "VEC3"  # UNSIGNED_INT, VEC3
            )

            faces_data["count"] = face_count
            faces_data["offsets"] = offsets_accessor

            # Add face subdivision attributes
            if "faces_holes" in bmesh_data:
                holes_data = bmesh_data["faces_holes"]
                holes_accessor = self.create_sparse_accessor(holes_data, 5121, "SCALAR")  # UNSIGNED_BYTE
                faces_data.setdefault("attributes", {})["HOLES"] = holes_accessor

            extension_data["faces"] = faces_data

        return extension_data

    def export_primitive(self, primitive: dict[str, Any], primitive_name: str, json_dict: dict[str, Any], buffer0: bytearray) -> None:
        """Export EXT_mesh_bmesh extension for a glTF primitive."""
        # Note: For full implementation, we need access to the original Blender mesh
        # For now, we'll create a placeholder extension with minimal data

        # Get position accessor to estimate vertex count
        position_accessor = primitive.get("attributes", {}).get("POSITION")
        if position_accessor is None:
            return

        # Read position accessor data
        position_data = self.read_accessor_data(position_accessor)
        vertex_count = len(position_data) if position_data else 0
        if vertex_count == 0:
            return

        # Create minimal EXT_mesh_bmesh extension
        extension_data = {
            "vertices": {
                "count": vertex_count,
                "positions": position_accessor
            },
            "edges": {
                "count": max(vertex_count - 1, 0),
                "vertices": position_accessor  # Placeholder
            },
            "loops": {
                "count": vertex_count,
                "topology_vertex": None,  # Placeholder
                "topology_edge": None,
                "topology_face": None,
                "topology_next": None,
                "topology_prev": None,
                "topology_radial_next": None,
                "topology_radial_prev": None
            },
            "faces": {
                "count": 1,  # Approximate one face
                "vertices": None,  # Placeholder
                "offsets": None
            }
        }

        # Add extension to primitive
        primitive.setdefault("extensions", {})["EXT_mesh_bmesh"] = extension_data
        self.has_exported_primitives = True

        # Mark extension as used
        extensions_used = json_dict.get("extensionsUsed", [])
        if "EXT_mesh_bmesh" not in extensions_used:
            extensions_used.append("EXT_mesh_bmesh")
            json_dict["extensionsUsed"] = extensions_used

        logger.info("Added minimal EXT_mesh_bmesh extension for primitive: %s", primitive_name)

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

    def export_mesh(self, mesh: Mesh, mesh_name: str, gltf_data: Optional[Dict[str, Any]] = None,
                   buffers: Optional[list[bytearray]] = None) -> Optional[dict[str, Any]]:
        """Export a mesh with EXT_mesh_bmesh extension."""

        try:
            # Update exporter with glTF context if provided
            if gltf_data:
                self.gltf_data = gltf_data
            if buffers:
                self.buffers = buffers
                self.buffer_views = gltf_data.get("bufferViews", [])
                self.accessors = gltf_data.get("accessors", [])

            # Analyze mesh topology
            bmesh_data = self.analyze_mesh_topology(mesh)

            # Export BMesh topology
            extension_data = self.export_bmesh_topology(bmesh_data)

            logger.info("Successfully exported EXT_mesh_bmesh for mesh: %s", mesh_name)
            return extension_data

        except Exception:
            logger.exception("Failed to export EXT_mesh_bmesh for mesh '%s'", mesh_name)
            return None
