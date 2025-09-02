# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
"""EXT_bmesh_encoding import and decoding algorithms."""

import struct
from typing import Any, Dict, List, Optional, Tuple

import bmesh
import bpy
from bmesh.types import BMesh, BMFace, BMLoop, BMVert, BMEdge
from mathutils import Vector

from ...common.gltf import parse_glb
from ...common.logger import get_logger

logger = get_logger(__name__)


def safe_ensure_lookup_table(bmesh_seq, seq_name="unknown"):
    """
    Safely ensure lookup table using appropriate method for each BMesh sequence type.
    
    BMLoopSeq doesn't have ensure_lookup_table() method in Blender's API,
    but it does have index_update() which serves the same purpose.
    """
    if hasattr(bmesh_seq, 'ensure_lookup_table'):
        try:
            bmesh_seq.ensure_lookup_table()
        except Exception as e:
            logger.debug(f"Failed to ensure lookup table for {seq_name}: {e}")
    elif hasattr(bmesh_seq, 'index_update'):
        try:
            bmesh_seq.index_update()
            logger.debug(f"Used index_update() for {seq_name} (BMLoopSeq compatibility)")
        except Exception as e:
            logger.debug(f"Failed to update indices for {seq_name}: {e}")
    else:
        logger.debug(f"No lookup table method available for {seq_name}")


class BmeshDecoder:
    """Handles BMesh reconstruction from EXT_bmesh_encoding extension data."""

    def __init__(self):
        pass

    def decode_gltf_extension_to_bmesh(self, extension_data: Dict[str, Any], parse_result: Any) -> Optional[BMesh]:
        """
        Decode EXT_bmesh_encoding extension data to BMesh.

        Supports both buffer-based reconstruction (glTF) and direct data reconstruction.
        Args:
            extension_data: The EXT_bmesh_encoding extension data from glTF primitive
            parse_result: The VRM addon's ParseResult containing glTF data and buffers (can be None for direct data)
        """
        if not extension_data:
            return None

        try:
            # Check if we have explicit BMesh topology data
            if self._has_explicit_topology_data(extension_data):
                # Check if this is direct encoded data (parse_result is None or has encoded_data)
                if parse_result is None or hasattr(parse_result, 'encoded_data'):
                    logger.info("EXT_bmesh_encoding: Using direct data reconstruction")
                    mock_parse_result = self._create_mock_parse_result(extension_data)
                    return self._decode_encoded_data_to_bmesh(extension_data, mock_parse_result)
                else:
                    # Use buffer-based reconstruction for glTF data
                    logger.info("EXT_bmesh_encoding: Using buffer-based reconstruction")
                    return self._reconstruct_from_buffer_format(extension_data, parse_result)
            else:
                # Fallback to standard glTF import
                logger.info("EXT_bmesh_encoding: No topology data found, using fallback")
                return None  # Let standard glTF import handle it

        except Exception as e:
            logger.error(f"Failed to decode EXT_bmesh_encoding: {e}")
            return None

    def decode_into_mesh(self, encoded_data: Dict[str, Any], target_mesh: Optional[bpy.types.Mesh] = None) -> Optional[bpy.types.Mesh]:
        """
        Decode encoded BMesh data directly into a Blender mesh.

        This method handles the direct encoded data format from BmeshEncoder,
        creating a new mesh if none is provided.

        Args:
            encoded_data: The encoded BMesh data from BmeshEncoder
            target_mesh: Optional existing mesh to decode into

        Returns:
            The decoded Blender mesh, or None if decoding failed
        """
        if not encoded_data:
            logger.warning("No encoded data provided to decode_into_mesh")
            return None

        try:
            # Create target mesh if not provided
            if target_mesh is None:
                target_mesh = bpy.data.meshes.new("DecodedBMesh")
                logger.debug("Created new mesh for decoding")

            # For direct encoded data (from BmeshEncoder), we need to handle the buffer format
            # without a parse_result. We'll create a mock parse_result for buffer access.
            mock_parse_result = self._create_mock_parse_result(encoded_data)

            # Decode the BMesh from encoded data
            bm = self._decode_encoded_data_to_bmesh(encoded_data, mock_parse_result)

            if bm is None:
                logger.error("Failed to decode BMesh from encoded data")
                return None

            # Apply the BMesh to the target mesh
            success = self.apply_bmesh_to_blender_mesh(bm, target_mesh)

            # Clean up the BMesh
            bm.free()

            if success:
                logger.info(f"Successfully decoded BMesh into mesh '{target_mesh.name}'")
                return target_mesh
            else:
                logger.error("Failed to apply decoded BMesh to target mesh")
                return None

        except Exception as e:
            logger.error(f"Failed to decode into mesh: {e}")
            return None

    def _create_mock_parse_result(self, encoded_data: Dict[str, Any]) -> Any:
        """
        Create a mock parse result for direct encoded data decoding.

        This allows us to reuse the buffer-based decoding logic without
        requiring a full glTF parse result.
        """
        class MockParseResult:
            def __init__(self, encoded_data):
                self.encoded_data = encoded_data
                self.json_dict = {"bufferViews": [], "buffers": [{"byteLength": 0}]}
                self.filepath = None

        return MockParseResult(encoded_data)

    def _decode_encoded_data_to_bmesh(self, encoded_data: Dict[str, Any], mock_parse_result: Any) -> Optional[BMesh]:
        """
        Decode direct encoded data to BMesh using buffer format reconstruction.

        This handles the case where we have encoded data directly from BmeshEncoder
        rather than glTF extension data.
        """
        try:
            # Check if we have the required topology data
            if not self._has_explicit_topology_data(encoded_data):
                logger.warning("Encoded data missing required topology sections")
                return None

            # Extract topology information
            vertex_data = encoded_data.get("vertices", {})
            edge_data = encoded_data.get("edges", {})
            loop_data = encoded_data.get("loops", {})
            face_data = encoded_data.get("faces", {})

            # Validate topology data
            if not all(isinstance(data, dict) and "count" in data for data in [vertex_data, edge_data, face_data]):
                logger.warning("Invalid topology data structure in encoded data")
                return None

            vertex_count = vertex_data.get("count", 0)
            edge_count = edge_data.get("count", 0)
            face_count = face_data.get("count", 0)

            logger.info(f"Decoding direct data: {vertex_count} vertices, {edge_count} edges, {face_count} faces")

            # Create new BMesh
            bm = bmesh.new()

            try:
                # Reconstruct vertices
                vertex_map = self._reconstruct_vertices_from_direct_data(bm, vertex_data)
                if not vertex_map:
                    logger.error("Failed to reconstruct vertices from direct data")
                    bm.free()
                    return None

                # Reconstruct edges
                edge_map = self._reconstruct_edges_from_direct_data(bm, edge_data, vertex_map)

                # Reconstruct faces
                face_map = self._reconstruct_faces_from_direct_data(bm, face_data, vertex_map, edge_map)

                # Apply loop data if available
                if loop_data and loop_data.get("count", 0) > 0:
                    self._apply_loop_data_from_direct_data(bm, loop_data, vertex_map, edge_map, face_map)

                # Ensure lookup tables are valid
                safe_ensure_lookup_table(bm.verts, "verts")
                safe_ensure_lookup_table(bm.edges, "edges")
                safe_ensure_lookup_table(bm.faces, "faces")
                safe_ensure_lookup_table(bm.loops, "loops")

                logger.info(f"Successfully decoded BMesh: {len(bm.verts)} verts, {len(bm.edges)} edges, {len(bm.faces)} faces")
                return bm

            except Exception as e:
                logger.error(f"Failed to decode BMesh from direct data: {e}")
                bm.free()
                return None

        except Exception as e:
            logger.error(f"Failed to decode encoded data to BMesh: {e}")
            return None

    def _reconstruct_vertices_from_direct_data(self, bm: BMesh, vertex_data: Dict[str, Any]) -> Dict[int, BMVert]:
        """Reconstruct vertices from direct encoded data."""
        vertex_map = {}
        vertex_count = vertex_data.get("count", 0)

        if vertex_count == 0:
            return vertex_map

        # Get position data
        positions_attr = vertex_data.get("positions")
        if positions_attr is None:
            return vertex_map

        # Handle direct data format
        positions = None
        if isinstance(positions_attr, dict) and "data" in positions_attr:
            data = positions_attr["data"]
            if isinstance(data, (bytes, bytearray)):
                positions = struct.unpack(f"<{vertex_count * 3}f", data)
                logger.debug(f"Read {len(positions)//3} vertex positions from direct data")
            else:
                logger.warning(f"Positions data is not bytes/bytearray: {type(data)}")
        else:
            logger.warning(f"Positions attribute has unexpected format: {type(positions_attr)}")

        if not positions:
            return vertex_map

        # Create vertices
        for i in range(vertex_count):
            pos_idx = i * 3
            position = (positions[pos_idx], positions[pos_idx + 1], positions[pos_idx + 2])
            vert = bm.verts.new(position)
            vertex_map[i] = vert

        return vertex_map

    def _reconstruct_edges_from_direct_data(self, bm: BMesh, edge_data: Dict[str, Any], vertex_map: Dict[int, BMVert]) -> Dict[int, BMEdge]:
        """Reconstruct edges from direct encoded data."""
        edge_map = {}
        edge_count = edge_data.get("count", 0)

        if edge_count == 0:
            return edge_map

        # Get edge vertex data
        vertices_attr = edge_data.get("vertices")
        if vertices_attr is None:
            return edge_map

        # Handle direct data format
        edge_vertices = None
        if isinstance(vertices_attr, dict) and "data" in vertices_attr:
            data = vertices_attr["data"]
            if isinstance(data, (bytes, bytearray)):
                edge_vertices = struct.unpack(f"<{edge_count * 2}I", data)
                logger.debug(f"Read {len(edge_vertices)//2} edge vertex pairs from direct data")
            else:
                logger.warning(f"Edge vertices data is not bytes/bytearray: {type(data)}")
        else:
            logger.warning(f"Edge vertices attribute has unexpected format: {type(vertices_attr)}")

        if not edge_vertices:
            return edge_map

        # Get smooth flags if available
        smooth_flags = None
        attributes = edge_data.get("attributes", {})
        if "_SMOOTH" in attributes:
            smooth_attr = attributes["_SMOOTH"]
            if isinstance(smooth_attr, dict) and "data" in smooth_attr:
                data = smooth_attr["data"]
                if isinstance(data, (bytes, bytearray)):
                    smooth_flags = struct.unpack(f"<{edge_count}B", data)
                    logger.debug(f"Read {len(smooth_flags)} edge smooth flags from direct data")

        # Create edges
        for i in range(edge_count):
            vert_idx1 = edge_vertices[i * 2]
            vert_idx2 = edge_vertices[i * 2 + 1]

            vert1 = vertex_map.get(vert_idx1)
            vert2 = vertex_map.get(vert_idx2)

            if vert1 and vert2:
                try:
                    edge = bm.edges.new([vert1, vert2])
                    edge_map[i] = edge

                    # Apply smooth flag if available
                    if smooth_flags and i < len(smooth_flags):
                        edge.smooth = bool(smooth_flags[i])

                except ValueError:
                    # Edge already exists, find it
                    for existing_edge in bm.edges:
                        if set(existing_edge.verts) == {vert1, vert2}:
                            edge_map[i] = existing_edge
                            if smooth_flags and i < len(smooth_flags):
                                existing_edge.smooth = bool(smooth_flags[i])
                            break

        return edge_map

    def _reconstruct_faces_from_direct_data(self, bm: BMesh, face_data: Dict[str, Any], vertex_map: Dict[int, BMVert], edge_map: Dict[int, BMEdge]) -> Dict[int, BMFace]:
        """Reconstruct faces from direct encoded data."""
        face_map = {}
        face_count = face_data.get("count", 0)

        if face_count == 0:
            return face_map

        # Get face vertex data and offsets
        vertices_attr = face_data.get("vertices")
        offsets_attr = face_data.get("offsets")

        if vertices_attr is None or offsets_attr is None:
            return face_map

        # Handle offsets
        offsets = None
        if isinstance(offsets_attr, dict) and "data" in offsets_attr:
            data = offsets_attr["data"]
            if isinstance(data, (bytes, bytearray)):
                offsets = struct.unpack(f"<{face_count + 1}I", data)
                logger.debug(f"Read {len(offsets)} face offsets from direct data")
            else:
                logger.warning(f"Offsets data is not bytes/bytearray: {type(data)}")

        if not offsets:
            return face_map

        # Handle face vertices
        max_vertex_offset = offsets[face_count]
        face_vertices_data = None
        if isinstance(vertices_attr, dict) and "data" in vertices_attr:
            data = vertices_attr["data"]
            if isinstance(data, (bytes, bytearray)):
                face_vertices_data = struct.unpack(f"<{max_vertex_offset}I", data)
                logger.debug(f"Read {len(face_vertices_data)} face vertex indices from direct data")
            else:
                logger.warning(f"Face vertices data is not bytes/bytearray: {type(data)}")

        if not face_vertices_data:
            return face_map

        # Handle face smooth flags if available
        face_smooth_flags = None
        smooth_attr = face_data.get("smooth")
        if smooth_attr is not None:
            if isinstance(smooth_attr, dict) and "data" in smooth_attr:
                data = smooth_attr["data"]
                if isinstance(data, (bytes, bytearray)):
                    face_smooth_flags = struct.unpack(f"<{face_count}B", data)
                    smooth_count = sum(1 for flag in face_smooth_flags if flag)
                    flat_count = len(face_smooth_flags) - smooth_count
                    logger.debug(f"Read {len(face_smooth_flags)} face smooth flags from direct data: {smooth_count} smooth, {flat_count} flat")
                else:
                    logger.warning(f"Face smooth data is not bytes/bytearray: {type(data)}")
            else:
                logger.warning(f"Face smooth attribute has unexpected format: {type(smooth_attr)}")

        # Create faces
        for i in range(face_count):
            vertex_start = offsets[i]
            vertex_end = offsets[i + 1] if i + 1 < len(offsets) else max_vertex_offset

            # Get vertex indices for this face
            face_vertex_indices = face_vertices_data[vertex_start:vertex_end]

            # Convert to BMVert objects
            face_verts = []
            for vert_idx in face_vertex_indices:
                vert = vertex_map.get(vert_idx)
                if vert:
                    face_verts.append(vert)

            if len(face_verts) >= 3:
                try:
                    face = bm.faces.new(face_verts)
                    face_map[i] = face

                    # Apply stored face smooth flag if available
                    if face_smooth_flags and i < len(face_smooth_flags):
                        face.smooth = bool(face_smooth_flags[i])
                        logger.debug(f"Applied smooth flag {bool(face_smooth_flags[i])} to face {i}")

                except ValueError as e:
                    logger.warning(f"Failed to create face {i}: {e}")

        return face_map

    def _apply_loop_data_from_direct_data(self, bm: BMesh, loop_data: Dict[str, Any], vertex_map: Dict[int, BMVert], edge_map: Dict[int, BMEdge], face_map: Dict[int, BMFace]) -> None:
        """Apply loop data from direct encoded data."""
        loop_count = loop_data.get("count", 0)
        if loop_count == 0:
            return

        # Handle UV attributes
        attributes = loop_data.get("attributes", {})
        uv_data = {}

        for attr_name, attr_data in attributes.items():
            if attr_name.startswith("TEXCOORD_") and isinstance(attr_data, dict) and "data" in attr_data:
                data = attr_data["data"]
                if isinstance(data, (bytes, bytearray)):
                    uv_coords = struct.unpack(f"<{loop_count * 2}f", data)
                    uv_data[attr_name] = uv_coords
                    logger.debug(f"Read {len(uv_coords)//2} UV coordinates for {attr_name}")

        # Apply UV data
        if uv_data:
            if not bm.loops.layers.uv:
                bm.loops.layers.uv.new()

            uv_layer = bm.loops.layers.uv.active
            if uv_layer:
                loop_index = 0
                for face in bm.faces:
                    for loop in face.loops:
                        if loop_index < loop_count and "TEXCOORD_0" in uv_data:
                            uv_coords = uv_data["TEXCOORD_0"]
                            uv_idx = loop_index * 2
                            if uv_idx + 1 < len(uv_coords):
                                loop[uv_layer].uv = (uv_coords[uv_idx], uv_coords[uv_idx + 1])
                        loop_index += 1

    def _has_explicit_topology_data(self, extension_data: Dict[str, Any]) -> bool:
        """Check if extension data contains explicit BMesh topology."""
        required_keys = ["vertices", "edges", "loops", "faces"]
        return all(key in extension_data for key in required_keys)

    def _reconstruct_from_buffer_format(self, extension_data: Dict[str, Any], parse_result: Any) -> Optional[BMesh]:
        """
        Reconstruct non-manifold BMesh from EXT_bmesh_encoding extension data.
        
        Uses mesh-based reconstruction to restore non-manifold boundary representation
        with proper half-edge connectivity, preserving N-gons and non-manifold edges.
        """
        logger.info("Reconstructing non-manifold boundary representation from EXT_bmesh_encoding")
        logger.info(f"Extension data structure: {list(extension_data.keys())}")
        
        # Extract topology information from extension data
        vertex_data = extension_data.get("vertices", {})
        edge_data = extension_data.get("edges", {})
        loop_data = extension_data.get("loops", {})
        face_data = extension_data.get("faces", {})

        # Debug: Log detailed structure of each topology section
        logger.info(f"Vertex data structure: {list(vertex_data.keys()) if isinstance(vertex_data, dict) else type(vertex_data)}")
        logger.info(f"Edge data structure: {list(edge_data.keys()) if isinstance(edge_data, dict) else type(edge_data)}")
        logger.info(f"Loop data structure: {list(loop_data.keys()) if isinstance(loop_data, dict) else type(loop_data)}")
        logger.info(f"Face data structure: {list(face_data.keys()) if isinstance(face_data, dict) else type(face_data)}")

        # Validate that we have the necessary topology data
        if not all(isinstance(data, dict) and "count" in data for data in [vertex_data, edge_data, face_data]):
            logger.warning("EXT_bmesh_encoding: Missing required topology data for non-manifold reconstruction")
            logger.warning(f"Vertex data valid: {isinstance(vertex_data, dict) and 'count' in vertex_data}")
            logger.warning(f"Edge data valid: {isinstance(edge_data, dict) and 'count' in edge_data}")
            logger.warning(f"Face data valid: {isinstance(face_data, dict) and 'count' in face_data}")
            return None

        vertex_count = vertex_data.get("count", 0)
        edge_count = edge_data.get("count", 0)
        face_count = face_data.get("count", 0)
        loop_count = loop_data.get("count", 0)

        logger.info(f"Reconstructing BMesh: {vertex_count} vertices, {edge_count} edges, {face_count} faces, {loop_count} loops")

        # Create new BMesh for non-manifold reconstruction
        bm = bmesh.new()
        
        try:
            # Step 1: Reconstruct vertices from buffer data
            vertex_map = self._reconstruct_vertices_from_buffers(bm, vertex_data, parse_result)
            if not vertex_map:
                logger.error("Failed to reconstruct vertices from buffer data")
                bm.free()
                return None

            # Step 1.5: Apply vertex attributes (normals, colors, etc.)
            self._apply_vertex_attributes_from_buffers(bm, vertex_data, vertex_map, parse_result)

            # Step 2: Reconstruct non-manifold edges from buffer data
            edge_map = self._reconstruct_edges_from_buffers(bm, edge_data, vertex_map, parse_result)

            # Step 3: Reconstruct N-gon faces from buffer data
            face_map = self._reconstruct_faces_from_buffers(bm, face_data, vertex_map, edge_map, parse_result)

            # Step 4: Apply loop topology and UV data from buffer data
            if loop_count > 0:
                self._apply_loop_data_from_buffers(bm, loop_data, vertex_map, edge_map, face_map, parse_result)

            # Step 5: Ensure all lookup tables are valid for non-manifold operations
            safe_ensure_lookup_table(bm.verts, "verts")
            safe_ensure_lookup_table(bm.edges, "edges") 
            safe_ensure_lookup_table(bm.faces, "faces")
            safe_ensure_lookup_table(bm.loops, "loops")

            logger.info(f"Successfully reconstructed non-manifold BMesh: {len(bm.verts)} verts, {len(bm.edges)} edges, {len(bm.faces)} faces")
            return bm

        except Exception as e:
            logger.error(f"Failed to reconstruct non-manifold BMesh: {e}")
            bm.free()
            return None


    def decode_implicit_triangle_fan(self, triangles: List[Tuple]) -> List[List[int]]:
        """
        Decode triangle fan back to polygon faces.
        
        This provides graceful fallback when EXT_bmesh_encoding is not fully supported.
        """
        if not triangles:
            return []

        faces = []
        current_face_vertices = []
        prev_anchor = None

        for triangle in triangles:
            if len(triangle) < 3:
                continue
                
            anchor = triangle[0]
            
            if anchor != prev_anchor:
                # New face starts
                if current_face_vertices:
                    faces.append(current_face_vertices)
                current_face_vertices = list(triangle)
                prev_anchor = anchor
            else:
                # Continue triangle fan for same face
                # Add the new vertex from this triangle
                new_vertex = triangle[2]  # Third vertex of triangle
                if new_vertex not in current_face_vertices:
                    current_face_vertices.append(new_vertex)

        # Handle last face
        if current_face_vertices:
            faces.append(current_face_vertices)

        return faces

    def apply_bmesh_to_blender_mesh(self, bm: BMesh, mesh: bpy.types.Mesh) -> bool:
        """Apply reconstructed BMesh data to Blender mesh."""
        try:
            # Store BMesh face smooth flags before conversion
            bmesh_smooth_flags = {}
            for i, face in enumerate(bm.faces):
                bmesh_smooth_flags[i] = face.smooth

            # Update the mesh with BMesh data
            bm.to_mesh(mesh)

            # Manually transfer face smooth flags from BMesh to mesh
            # The bm.to_mesh() call may not preserve face smooth flags correctly
            if bmesh_smooth_flags:
                for i, face in enumerate(mesh.polygons):
                    if i in bmesh_smooth_flags:
                        face.use_smooth = bmesh_smooth_flags[i]
                        logger.debug(f"Transferred smooth flag {bmesh_smooth_flags[i]} to mesh face {i}")

            # Handle smooth shading based on Blender version
            # Note: Face smooth flags were already set during BMesh reconstruction
            # Only apply auto smooth for older Blender versions when no face smooth flags are set
            if bpy.app.version < (4, 1) and not bmesh_smooth_flags:
                # Blender 4.0 and earlier: use auto smooth only when no face smooth flags are manually set
                mesh.use_auto_smooth = True
                logger.info("Applied auto smooth for Blender 4.0 and earlier (no manual face smooth flags)")
            else:
                # Blender 4.1+ or when face smooth flags are manually set: preserve face smooth flags
                logger.info("Preserved face smooth flags from BMesh reconstruction")

            # Ensure proper mesh finalization for smooth shading preservation
            mesh.update()
            mesh.calc_loop_triangles()

            # Calculate normals to respect edge smooth flags
            # Use the correct method based on Blender version
            if hasattr(mesh, 'calc_normals'):
                mesh.calc_normals()
            elif hasattr(mesh, 'calc_normals_split'):
                mesh.calc_normals_split()
            else:
                logger.warning("No normal calculation method available")

            logger.info("Successfully applied BMesh to Blender mesh with surface smoothness preservation")
            return True

        except Exception as e:
            logger.error(f"Failed to apply BMesh to Blender mesh: {e}")
            return False

    @staticmethod
    def detect_extension_in_primitive(primitive_data: Dict[str, Any]) -> bool:
        """Check if a glTF primitive contains EXT_bmesh_encoding extension."""
        extensions = primitive_data.get("extensions", {})
        return "EXT_bmesh_encoding" in extensions

    @staticmethod
    def extract_extension_data(primitive_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract EXT_bmesh_encoding extension data from glTF primitive."""
        extensions = primitive_data.get("extensions", {})
        return extensions.get("EXT_bmesh_encoding")

    def _read_buffer_view(self, parse_result: Any, buffer_view_index: int, component_type: int, count: int, type_name: str) -> Optional[Any]:
        """Read data from a glTF buffer view using VRM addon's parse_result."""
        try:
            # Check if this is a mock parse result for direct data
            if hasattr(parse_result, 'encoded_data') and parse_result.encoded_data is not None:
                logger.debug("Using mock parse result for direct data decoding")
                # For direct encoded data, we need to handle it differently
                # The buffer_view_index is actually a key in the encoded_data
                return self._read_direct_encoded_data(parse_result.encoded_data, buffer_view_index, component_type, count, type_name)

            # Check if parse_result is None (direct data mode)
            if parse_result is None:
                logger.debug("No parse result provided, cannot read buffer view data")
                return None

            # Access buffer views from VRM addon's parsed JSON data
            json_dict = parse_result.json_dict
            buffer_views = json_dict.get('bufferViews', [])

            if not buffer_views or buffer_view_index >= len(buffer_views):
                logger.warning(f"Buffer view {buffer_view_index} not found in {len(buffer_views)} buffer views")
                return None

            buffer_view = buffer_views[buffer_view_index]

            # Access buffer data from parse_result
            buffer_index = buffer_view.get('buffer', 0)
            if buffer_index != 0:
                logger.warning(f"EXT_bmesh_encoding only supports buffer 0, got buffer {buffer_index}")
                return None

            # ParseResult doesn't store buffer data directly, need to re-parse the file
            try:
                _, buffer0_bytes = parse_glb(parse_result.filepath.read_bytes())
                buffer_data = buffer0_bytes
            except Exception as e:
                logger.error(f"Failed to re-parse glTF file for buffer access: {e}")
                return None

            byte_offset = buffer_view.get('byteOffset', 0)
            byte_length = buffer_view.get('byteLength', 0)

            if byte_offset + byte_length > len(buffer_data):
                logger.error(f"Buffer view {buffer_view_index} extends beyond buffer bounds")
                return None

            data = buffer_data[byte_offset:byte_offset + byte_length]

            # Parse based on component type and format
            if component_type == 5126:  # GL_FLOAT
                if type_name == "VEC3":
                    return struct.unpack(f"<{count * 3}f", data)
                elif type_name == "VEC2":
                    return struct.unpack(f"<{count * 2}f", data)
                else:  # SCALAR
                    return struct.unpack(f"<{count}f", data)
            elif component_type == 5125:  # GL_UNSIGNED_INT
                return struct.unpack(f"<{count}I", data)
            elif component_type == 5121:  # GL_UNSIGNED_BYTE
                return struct.unpack(f"<{count}B", data)
            else:
                logger.warning(f"Unsupported component type: {component_type}")
                return None

        except Exception as e:
            logger.error(f"Failed to read buffer view {buffer_view_index}: {e}")
            return None

    def _read_direct_encoded_data(self, encoded_data: Dict[str, Any], buffer_view_index: int, component_type: int, count: int, type_name: str) -> Optional[Any]:
        """Read data from direct encoded data format."""
        try:
            # For direct encoded data, buffer_view_index is actually a key in the encoded_data
            # We need to map the buffer view index to the appropriate data structure
            logger.debug(f"Reading direct encoded data for buffer view {buffer_view_index}, type: {type_name}, count: {count}")

            # This method is called when we have direct encoded data, but the buffer_view_index
            # approach doesn't work. Instead, we should return None and let the calling
            # methods handle the direct data format directly.
            #
            # The issue is that the encoder produces data in this format:
            # {
            #   "positions": {"data": bytes, "componentType": 5126, "type": "VEC3", ...},
            #   "vertices": {"data": bytes, "componentType": 5125, "type": "SCALAR", ...},
            #   ...
            # }
            #
            # But the decoder expects buffer view indices. The calling methods should
            # handle this by checking for direct data format first.

            logger.debug("Direct encoded data reading not supported via buffer view index - use direct data methods instead")
            return None

        except Exception as e:
            logger.error(f"Failed to read direct encoded data for buffer view {buffer_view_index}: {e}")
            return None

    def _reconstruct_vertices_from_buffers(self, bm: BMesh, vertex_data: Dict[str, Any], parse_result: Any) -> Dict[int, BMVert]:
        """Reconstruct vertices from buffer data."""
        vertex_map = {}
        vertex_count = vertex_data.get("count", 0)
        
        if vertex_count == 0:
            return vertex_map

        # Read position data
        positions_attr = vertex_data.get("positions")
        if positions_attr is None:
            return vertex_map

        logger.info(f"Positions attribute type: {type(positions_attr)}")
        
        # Handle both buffer view index (int) and direct data (dict with 'data' field)
        positions = None
        if isinstance(positions_attr, int):
            # Buffer view index - read from buffer
            positions = self._read_buffer_view(parse_result, positions_attr, 5126, vertex_count, "VEC3")
            if positions:
                logger.info(f"Successfully read {len(positions)//3} vertex positions from buffer view {positions_attr}")
            else:
                logger.warning(f"Failed to read vertex positions from buffer view {positions_attr}")
        elif isinstance(positions_attr, dict) and "data" in positions_attr:
            # Direct data - unpack from bytearray
            data = positions_attr["data"]
            if isinstance(data, (bytes, bytearray)):
                positions = struct.unpack(f"<{vertex_count * 3}f", data)
                logger.info(f"Successfully read {len(positions)//3} vertex positions from direct data")
            else:
                logger.warning(f"Positions data is not bytes/bytearray: {type(data)}")
        else:
            logger.warning(f"Positions attribute has unexpected format: {type(positions_attr)}")

        if not positions:
            return vertex_map

        # Create vertices
        for i in range(vertex_count):
            pos_idx = i * 3
            position = (positions[pos_idx], positions[pos_idx + 1], positions[pos_idx + 2])
            vert = bm.verts.new(position)
            vertex_map[i] = vert

        return vertex_map

    def _apply_vertex_attributes_from_buffers(self, bm: BMesh, vertex_data: Dict[str, Any], vertex_map: Dict[int, BMVert], parse_result: Any) -> None:
        """Apply vertex attributes (normals, colors, etc.) from buffer data."""
        vertex_count = vertex_data.get("count", 0)
        if vertex_count == 0:
            return
            
        # Read vertex attributes if present
        attributes = vertex_data.get("attributes", {})
        if not attributes:
            logger.debug("No vertex attributes found in extension data")
            return
            
        logger.info(f"Applying vertex attributes: {list(attributes.keys())}")
        
        # Apply vertex normals
        if "NORMAL" in attributes:
            normal_attr = attributes["NORMAL"]
            logger.info(f"NORMAL attribute type: {type(normal_attr)}, content: {normal_attr}")
            
            # Handle both buffer view index (int) and direct data (dict with 'data' field)
            normals = None
            if isinstance(normal_attr, int):
                # Buffer view index - read from buffer
                normal_buffer_index = normal_attr
                normals = self._read_buffer_view(parse_result, normal_buffer_index, 5126, vertex_count, "VEC3")
                if normals:
                    logger.info(f"Successfully read {len(normals)//3} vertex normals from buffer view {normal_buffer_index}")
                else:
                    logger.warning(f"Failed to read vertex normals from buffer view {normal_buffer_index}")
            elif isinstance(normal_attr, dict) and "data" in normal_attr:
                # Direct data - unpack from bytearray
                data = normal_attr["data"]
                if isinstance(data, (bytes, bytearray)):
                    normals = struct.unpack(f"<{vertex_count * 3}f", data)
                    logger.info(f"Successfully read {len(normals)//3} vertex normals from direct data")
                else:
                    logger.warning(f"NORMAL data is not bytes/bytearray: {type(data)}")
            else:
                logger.warning(f"NORMAL attribute has unexpected format: {type(normal_attr)}")
            
            # Apply normals if we got them
            if normals:
                for i in range(vertex_count):
                    vert = vertex_map.get(i)
                    if vert:
                        normal_idx = i * 3
                        if normal_idx + 2 < len(normals):
                            stored_normal = Vector((
                                normals[normal_idx],
                                normals[normal_idx + 1],
                                normals[normal_idx + 2]
                            ))
                            vert.normal = stored_normal
                            logger.debug(f"Applied vertex normal {stored_normal} to vertex {i}")
                logger.info(f"Vertex normal preservation: Applied normals to {vertex_count} vertices")
            else:
                logger.warning("No vertex normals available to apply")
        
        # Apply vertex colors
        color_index = 0
        while f"COLOR_{color_index}" in attributes:
            color_buffer_index = attributes[f"COLOR_{color_index}"]
            colors = self._read_buffer_view(parse_result, color_buffer_index, 5126, vertex_count, "VEC4")
            if colors:
                logger.info(f"Successfully read {len(colors)//4} vertex colors from buffer (COLOR_{color_index})")
                
                # Ensure color layer exists
                if not bm.loops.layers.color:
                    bm.loops.layers.color.new()
                
                color_layer = bm.loops.layers.color.active
                if color_layer:
                    # Apply colors to loops (since Blender vertex colors are per-loop)
                    loop_index = 0
                    for face in bm.faces:
                        for loop in face.loops:
                            vertex_idx = loop.vert.index if hasattr(loop.vert, 'index') else None
                            # Find vertex index in our map
                            for v_idx, vert in vertex_map.items():
                                if vert == loop.vert:
                                    vertex_idx = v_idx
                                    break
                            
                            if vertex_idx is not None and vertex_idx < vertex_count:
                                color_idx = vertex_idx * 4
                                if color_idx + 3 < len(colors):
                                    color = (colors[color_idx], colors[color_idx + 1], colors[color_idx + 2], colors[color_idx + 3])
                                    loop[color_layer] = color[:3]  # BMesh color layers use RGB, not RGBA
                                    logger.debug(f"Applied vertex color {color[:3]} to loop at vertex {vertex_idx}")
                            loop_index += 1
                    logger.info(f"Vertex color preservation: Applied COLOR_{color_index} to loops")
            else:
                logger.warning(f"Failed to read vertex colors from buffer (COLOR_{color_index})")
            
            color_index += 1
        
        # Handle other vertex attributes (extensible for future use)
        for attr_name, buffer_index in attributes.items():
            if attr_name not in ["NORMAL"] and not attr_name.startswith("COLOR_"):
                logger.debug(f"Vertex attribute '{attr_name}' found but not yet supported")

    def _reconstruct_edges_from_buffers(self, bm: BMesh, edge_data: Dict[str, Any], vertex_map: Dict[int, BMVert], parse_result: Any) -> Dict[int, BMEdge]:
        """Reconstruct edges from buffer data."""
        edge_map = {}
        edge_count = edge_data.get("count", 0)
        
        if edge_count == 0:
            return edge_map

        # Read edge vertex pairs
        vertices_attr = edge_data.get("vertices")
        if vertices_attr is None:
            return edge_map

        logger.info(f"Edge vertices attribute type: {type(vertices_attr)}")
        
        # Handle both buffer view index (int) and direct data (dict with 'data' field)
        edge_vertices = None
        if isinstance(vertices_attr, int):
            # Buffer view index - read from buffer
            edge_vertices = self._read_buffer_view(parse_result, vertices_attr, 5125, edge_count * 2, "VEC2")
            if edge_vertices:
                logger.info(f"Successfully read {len(edge_vertices)//2} edge vertex pairs from buffer view {vertices_attr}")
            else:
                logger.warning(f"Failed to read edge vertices from buffer view {vertices_attr}")
        elif isinstance(vertices_attr, dict) and "data" in vertices_attr:
            # Direct data - unpack from bytearray
            data = vertices_attr["data"]
            if isinstance(data, (bytes, bytearray)):
                edge_vertices = struct.unpack(f"<{edge_count * 2}I", data)
                logger.info(f"Successfully read {len(edge_vertices)//2} edge vertex pairs from direct data")
            else:
                logger.warning(f"Edge vertices data is not bytes/bytearray: {type(data)}")
        else:
            logger.warning(f"Edge vertices attribute has unexpected format: {type(vertices_attr)}")

        if not edge_vertices:
            return edge_map

        # Read edge smooth flags if available
        smooth_flags = None
        attributes = edge_data.get("attributes", {})
        logger.info(f"Edge attributes available: {list(attributes.keys()) if attributes else 'None'}")
        
        if "_SMOOTH" in attributes:
            smooth_attr = attributes["_SMOOTH"]
            logger.info(f"_SMOOTH attribute type: {type(smooth_attr)}, content: {smooth_attr}")
            
            # Handle both buffer view index (int) and direct data (dict with 'data' field)
            if isinstance(smooth_attr, int):
                # Buffer view index - read from buffer
                smooth_buffer_index = smooth_attr
                smooth_flags = self._read_buffer_view(parse_result, smooth_buffer_index, 5121, edge_count, "SCALAR")
                if smooth_flags:
                    smooth_count = sum(1 for flag in smooth_flags if flag)
                    hard_count = len(smooth_flags) - smooth_count
                    logger.info(f"Successfully read {len(smooth_flags)} edge smooth flags from buffer view {smooth_buffer_index}: {smooth_count} smooth, {hard_count} hard")
                else:
                    logger.warning(f"Failed to read edge smooth flags from buffer view {smooth_buffer_index}")
            elif isinstance(smooth_attr, dict) and "data" in smooth_attr:
                # Direct data - unpack from bytearray
                data = smooth_attr["data"]
                if isinstance(data, (bytes, bytearray)):
                    smooth_flags = struct.unpack(f"<{edge_count}B", data)
                    smooth_count = sum(1 for flag in smooth_flags if flag)
                    hard_count = len(smooth_flags) - smooth_count
                    logger.info(f"Successfully read {len(smooth_flags)} edge smooth flags from direct data: {smooth_count} smooth, {hard_count} hard")
                else:
                    logger.warning(f"_SMOOTH data is not bytes/bytearray: {type(data)}")
            else:
                logger.warning(f"_SMOOTH attribute has unexpected format: {type(smooth_attr)}")
        else:
            logger.warning("No '_SMOOTH' attribute found in edge data - all edges will default to smooth")

        # Create edges
        for i in range(edge_count):
            vert_idx1 = edge_vertices[i * 2]
            vert_idx2 = edge_vertices[i * 2 + 1]
            
            vert1 = vertex_map.get(vert_idx1)
            vert2 = vertex_map.get(vert_idx2)
            
            if vert1 and vert2:
                try:
                    edge = bm.edges.new([vert1, vert2])
                    edge_map[i] = edge
                    
                    # Apply smooth flag if available
                    if smooth_flags and i < len(smooth_flags):
                        edge.smooth = bool(smooth_flags[i])
                        logger.debug(f"Applied smooth flag {bool(smooth_flags[i])} to edge {i}")
                        
                except ValueError:
                    # Edge already exists, find it
                    for existing_edge in bm.edges:
                        if set(existing_edge.verts) == {vert1, vert2}:
                            edge_map[i] = existing_edge
                            
                            # Apply smooth flag to existing edge if available
                            if smooth_flags and i < len(smooth_flags):
                                existing_edge.smooth = bool(smooth_flags[i])
                                logger.debug(f"Applied smooth flag {bool(smooth_flags[i])} to existing edge {i}")
                            break

        # Log smooth flag preservation status
        if smooth_flags:
            logger.info(f"Edge smooth flag preservation: Applied smooth flags to {len(edge_map)} edges")
        else:
            logger.warning("Edge smooth flag preservation: No smooth flags found in buffer data")

        return edge_map

    def _reconstruct_faces_from_buffers(self, bm: BMesh, face_data: Dict[str, Any], vertex_map: Dict[int, BMVert], edge_map: Dict[int, BMEdge], parse_result: Any) -> Dict[int, BMFace]:
        """Reconstruct faces from buffer data."""
        face_map = {}
        face_count = face_data.get("count", 0)

        if face_count == 0:
            return face_map

        # Check if this is direct encoded data
        is_direct_data = hasattr(parse_result, 'encoded_data') and parse_result.encoded_data is not None

        # Read face vertex data and offsets
        vertices_attr = face_data.get("vertices")
        offsets_attr = face_data.get("offsets")

        if vertices_attr is None or offsets_attr is None:
            return face_map

        # Handle direct data vs buffer view data
        offsets = None
        face_vertices_data = None

        if is_direct_data:
            # Handle direct encoded data
            if isinstance(offsets_attr, dict) and "data" in offsets_attr:
                data = offsets_attr["data"]
                if isinstance(data, (bytes, bytearray)):
                    offsets = struct.unpack(f"<{face_count + 1}I", data)
                    logger.debug(f"Read {len(offsets)} face offsets from direct data")

            if isinstance(vertices_attr, dict) and "data" in vertices_attr:
                data = vertices_attr["data"]
                if isinstance(data, (bytes, bytearray)):
                    max_vertex_offset = offsets[face_count] if offsets else 0
                    face_vertices_data = struct.unpack(f"<{max_vertex_offset}I", data)
                    logger.debug(f"Read {len(face_vertices_data)} face vertex indices from direct data")
        else:
            # Handle buffer view data
            if isinstance(offsets_attr, int):
                offsets = self._read_buffer_view(parse_result, offsets_attr, 5125, face_count + 1, "SCALAR")
            if isinstance(vertices_attr, int):
                max_vertex_offset = offsets[face_count] if offsets else 0
                face_vertices_data = self._read_buffer_view(parse_result, vertices_attr, 5125, max_vertex_offset, "SCALAR")

        if not offsets or not face_vertices_data:
            logger.warning("Failed to read face data from buffer or direct data")
            return face_map

        # Read face normals if available
        normals_buffer_index = face_data.get("normals")
        face_normals = None
        if normals_buffer_index is not None:
            if is_direct_data and isinstance(normals_buffer_index, dict) and "data" in normals_buffer_index:
                data = normals_buffer_index["data"]
                if isinstance(data, (bytes, bytearray)):
                    face_normals = struct.unpack(f"<{face_count * 3}f", data)
                    logger.info(f"Successfully read {len(face_normals)//3} face normals from direct data")
            elif not is_direct_data and isinstance(normals_buffer_index, int):
                face_normals = self._read_buffer_view(parse_result, normals_buffer_index, 5126, face_count, "VEC3")
                if face_normals:
                    logger.info(f"Successfully read {len(face_normals)//3} face normals from buffer")
                else:
                    logger.warning("Failed to read face normals from buffer")

        # Read face smooth flags if available
        smooth_buffer_index = face_data.get("smooth")
        face_smooth_flags = None
        if smooth_buffer_index is not None:
            if is_direct_data and isinstance(smooth_buffer_index, dict) and "data" in smooth_buffer_index:
                data = smooth_buffer_index["data"]
                if isinstance(data, (bytes, bytearray)):
                    face_smooth_flags = struct.unpack(f"<{face_count}B", data)
                    smooth_count = sum(1 for flag in face_smooth_flags if flag)
                    flat_count = len(face_smooth_flags) - smooth_count
                    logger.info(f"Successfully read {len(face_smooth_flags)} face smooth flags from direct data: {smooth_count} smooth, {flat_count} flat")
            elif not is_direct_data and isinstance(smooth_buffer_index, int):
                face_smooth_flags = self._read_buffer_view(parse_result, smooth_buffer_index, 5121, face_count, "SCALAR")
                if face_smooth_flags:
                    smooth_count = sum(1 for flag in face_smooth_flags if flag)
                    flat_count = len(face_smooth_flags) - smooth_count
                    logger.info(f"Successfully read {len(face_smooth_flags)} face smooth flags from buffer: {smooth_count} smooth, {flat_count} flat")
                else:
                    logger.warning("Failed to read face smooth flags from buffer")

        # Create faces
        for i in range(face_count):
            vertex_start = offsets[i]
            vertex_end = offsets[i + 1] if i + 1 < len(offsets) else len(face_vertices_data)

            # Get vertex indices for this face
            face_vertex_indices = face_vertices_data[vertex_start:vertex_end]

            # Convert to BMVert objects
            face_verts = []
            for vert_idx in face_vertex_indices:
                vert = vertex_map.get(vert_idx)
                if vert:
                    face_verts.append(vert)

            if len(face_verts) >= 3:
                try:
                    face = bm.faces.new(face_verts)
                    face_map[i] = face

                    # Apply stored face normal if available
                    if face_normals and i * 3 + 2 < len(face_normals):
                        normal_idx = i * 3
                        stored_normal = Vector((
                            face_normals[normal_idx],
                            face_normals[normal_idx + 1],
                            face_normals[normal_idx + 2]
                        ))

                        # Apply the stored normal to the face
                        face.normal = stored_normal
                        logger.debug(f"Applied stored normal {stored_normal} to face {i}")

                    # Apply stored face smooth flag if available
                    if face_smooth_flags and i < len(face_smooth_flags):
                        face.smooth = bool(face_smooth_flags[i])
                        logger.debug(f"Applied smooth flag {bool(face_smooth_flags[i])} to face {i}")

                except ValueError as e:
                    logger.warning(f"Failed to create face {i}: {e}")
                    # Remove the face from the map if creation failed
                    if i in face_map:
                        del face_map[i]

        # Log normal preservation status
        if face_normals:
            logger.info(f"Face normal preservation: Applied normals to {len(face_map)} faces")
        else:
            logger.warning("Face normal preservation: No normals found in buffer data")

        logger.info(f"Successfully reconstructed {len(face_map)} faces from {face_count} face definitions")
        return face_map

    def _apply_loop_data_from_buffers(self, bm: BMesh, loop_data: Dict[str, Any], vertex_map: Dict[int, BMVert], edge_map: Dict[int, BMEdge], face_map: Dict[int, BMFace], parse_result: Any) -> None:
        """Apply loop data (UV coordinates, etc.) from buffer data."""
        loop_count = loop_data.get("count", 0)
        if loop_count == 0:
            return

        # Read UV attributes if present
        attributes = loop_data.get("attributes", {})
        uv_data = {}
        
        for attr_name, buffer_index in attributes.items():
            if attr_name.startswith("TEXCOORD_"):
                uv_coords = self._read_buffer_view(parse_result, buffer_index, 5126, loop_count, "VEC2")
                if uv_coords:
                    uv_data[attr_name] = uv_coords

        # Apply UV data to loops
        if uv_data:
            # Ensure UV layer exists
            if not bm.loops.layers.uv:
                bm.loops.layers.uv.new()
            
            uv_layer = bm.loops.layers.uv.active
            if uv_layer:
                loop_index = 0
                for face in bm.faces:
                    for loop in face.loops:
                        if loop_index < loop_count and "TEXCOORD_0" in uv_data:
                            uv_coords = uv_data["TEXCOORD_0"]
                            uv_idx = loop_index * 2
                            if uv_idx + 1 < len(uv_coords):
                                loop[uv_layer].uv = (uv_coords[uv_idx], uv_coords[uv_idx + 1])
                        loop_index += 1
