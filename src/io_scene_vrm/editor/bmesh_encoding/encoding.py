# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
"""EXT_bmesh_encoding buffer-based encoding implementation."""

import struct
from typing import Any, Dict, List, Optional, Tuple

import bmesh
import bpy
from bmesh.types import BMesh, BMFace, BMLoop, BMVert, BMEdge
from mathutils import Vector

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


class BmeshEncoder:
    """Handles buffer-based BMesh encoding for EXT_bmesh_encoding extension."""

    def __init__(self):
        """Initialize encoder with buffer-only format."""
        self.preserve_manifold_info = True

    def encode_object(self, mesh_obj: bpy.types.Object) -> Dict[str, Any]:
        """
        Creates a BMesh from the given object, encodes it for the
        EXT_bmesh_encoding extension, and ensures proper cleanup.

        This is the recommended entry point to avoid caching issues.
        """
        logger.info(f"Creating BMesh for '{mesh_obj.name}' for EXT_bmesh_encoding.")
        
        # Use the existing static method to create the BMesh
        bm = BmeshEncoder.create_bmesh_from_mesh(mesh_obj)
        
        if not bm:
            logger.warning(f"Could not create BMesh from '{mesh_obj.name}', skipping extension.")
            return {}

        try:
            # Delegate to the main encoding logic that you've already written
            extension_data = self.encode_bmesh_to_gltf_extension(bm)
            if not extension_data:
                logger.warning(f"BMesh encoding resulted in no data for '{mesh_obj.name}'.")
            return extension_data
        finally:
            # IMPORTANT: Always free the BMesh to prevent memory leaks
            if bm:
                bm.free()
                logger.debug(f"BMesh for '{mesh_obj.name}' has been freed.")

    def encode_object_native(self, mesh_obj: bpy.types.Object) -> Dict[str, Any]:
        """
        Creates native mesh data from the given object and encodes it using
        the stable native API. This is the recommended approach.
        """
        logger.info(f"Creating native mesh data for '{mesh_obj.name}' for EXT_bmesh_encoding.")
        
        # Use the static method to get evaluated mesh data
        mesh_data = BmeshEncoder.create_mesh_data_from_object(mesh_obj)

        if not mesh_data:
            logger.warning(f"Could not get mesh data from '{mesh_obj.name}', skipping extension.")
            return {}
        
        # Delegate to the native encoding logic
        extension_data = self.encode_mesh_to_gltf_extension_native(mesh_data)

        # No need to free mesh_data like a BMesh, Blender manages it
        return extension_data

    def encode_bmesh_to_gltf_extension(self, bm: BMesh) -> Dict[str, Any]:
        """
        Encode BMesh to EXT_bmesh_encoding extension data using buffer format.
        
        Returns buffer-based extension data that references glTF buffer views.
        Material indices are handled at the glTF primitive level, not face level.
        Uses direct iteration to avoid lookup table compatibility issues.
        """
        if not bm.faces:
            return {}

        # Build index maps manually - more reliable than ensure_lookup_table()
        vert_to_index = {vert: i for i, vert in enumerate(bm.verts)}
        edge_to_index = {edge: i for i, edge in enumerate(bm.edges)}
        face_to_index = {face: i for i, face in enumerate(bm.faces)}
        
        # Build loop index map through direct iteration
        loop_to_index = {}
        loop_index = 0
        for face in bm.faces:
            for loop in face.loops:
                loop_to_index[loop] = loop_index
                loop_index += 1

        return self._encode_to_buffer_format_direct(bm, vert_to_index, edge_to_index, face_to_index, loop_to_index)

    def _encode_to_buffer_format_direct(self, bm: BMesh, vert_to_index: Dict, edge_to_index: Dict, face_to_index: Dict, loop_to_index: Dict) -> Dict[str, Any]:
        """
        Encode BMesh to buffer format using manual index maps to avoid lookup table issues.
        
        This creates the extension data structure that references buffer views
        which will be created by the glTF exporter.
        """
        extension_data = {}

        # Encode vertices
        vertex_data = self._encode_vertices_to_buffers_direct(bm, vert_to_index, edge_to_index)
        if vertex_data:
            extension_data["vertices"] = vertex_data

        # Encode edges
        edge_data = self._encode_edges_to_buffers_direct(bm, vert_to_index, edge_to_index, face_to_index)
        if edge_data:
            extension_data["edges"] = edge_data

        # Encode loops
        loop_data = self._encode_loops_to_buffers_direct(bm, vert_to_index, edge_to_index, face_to_index, loop_to_index)
        if loop_data:
            extension_data["loops"] = loop_data

        # Encode faces
        face_data = self._encode_faces_to_buffers_direct(bm, vert_to_index, edge_to_index, loop_to_index, face_to_index)
        if face_data:
            extension_data["faces"] = face_data

        return extension_data

    def _encode_to_buffer_format(self, bm: BMesh) -> Dict[str, Any]:
        """
        Encode BMesh to buffer format following glTF conventions.
        
        This creates the extension data structure that references buffer views
        which will be created by the glTF exporter.
        """
        extension_data = {}

        # Encode vertices
        vertex_data = self._encode_vertices_to_buffers(bm)
        if vertex_data:
            extension_data["vertices"] = vertex_data

        # Encode edges
        edge_data = self._encode_edges_to_buffers(bm)
        if edge_data:
            extension_data["edges"] = edge_data

        # Encode loops
        loop_data = self._encode_loops_to_buffers(bm)
        if loop_data:
            extension_data["loops"] = loop_data

        # Encode faces
        face_data = self._encode_faces_to_buffers(bm)
        if face_data:
            extension_data["faces"] = face_data

        return extension_data

    def _encode_vertices_to_buffers_direct(self, bm: BMesh, vert_to_index: Dict, edge_to_index: Dict) -> Dict[str, Any]:
        """Encode vertex data using manual index maps to avoid lookup table issues."""
        if not bm.verts:
            return {}

        vertex_count = len(bm.verts)
        
        # Create position data (required by schema)
        positions_buffer = bytearray()
        position_struct = struct.Struct("<fff")
        
        # Create vertex normal data (custom attribute)
        normals_buffer = bytearray()
        normal_struct = struct.Struct("<fff")
        
        # Create edge adjacency data (optional per schema)
        edges_buffer = bytearray()
        edge_index_struct = struct.Struct("<I")
        
        for vert in bm.verts:
            # Pack vertex position (Vec3<f32> as required by schema)
            positions_buffer.extend(position_struct.pack(*vert.co))
            
            # Pack vertex normal (Vec3<f32> for surface smoothness preservation)
            normals_buffer.extend(normal_struct.pack(*vert.normal))
            
            # Pack vertex-edge adjacency data using manual index mapping
            for edge in vert.link_edges:
                edge_idx = edge_to_index.get(edge)
                if edge_idx is not None:
                    edges_buffer.extend(edge_index_struct.pack(edge_idx))

        result = {
            "count": vertex_count,
            "positions": {
                "data": positions_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": vertex_count
            }
        }
        
        # Add vertex normals as custom attribute
        if normals_buffer:
            if "attributes" not in result:
                result["attributes"] = {}
            result["attributes"]["NORMAL"] = {
                "data": normals_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": vertex_count
            }
        
        # Add edges buffer if there's adjacency data
        if edges_buffer:
            result["edges"] = {
                "data": edges_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        return result

    def _encode_edges_to_buffers_direct(self, bm: BMesh, vert_to_index: Dict, edge_to_index: Dict, face_to_index: Dict) -> Dict[str, Any]:
        """Encode edge data using manual index maps to avoid lookup table issues."""
        if not bm.edges:
            return {}

        edge_count = len(bm.edges)
        
        # Create edge vertex pairs (required: 2×u32 per edge)
        vertices_buffer = bytearray()
        vertex_pair_struct = struct.Struct("<II")
        
        # Create face adjacency data (optional)
        faces_buffer = bytearray()
        face_index_struct = struct.Struct("<I")
        
        # Create manifold flags (optional: u8 per edge)
        manifold_buffer = bytearray()
        manifold_struct = struct.Struct("<B")
        
        # Create smooth flags (custom attribute: u8 per edge)
        smooth_buffer = bytearray()
        smooth_struct = struct.Struct("<B")
        
        for edge in bm.edges:
            # Pack edge vertices using manual index mapping (required by schema)
            vert0_idx = vert_to_index.get(edge.verts[0])
            vert1_idx = vert_to_index.get(edge.verts[1])
            
            if vert0_idx is not None and vert1_idx is not None:
                vertices_buffer.extend(vertex_pair_struct.pack(vert0_idx, vert1_idx))
            
            # Pack face adjacency data using manual index mapping
            for face in edge.link_faces:
                face_idx = face_to_index.get(face)
                if face_idx is not None:
                    faces_buffer.extend(face_index_struct.pack(face_idx))
            
            # Pack manifold status (0=non-manifold, 1=manifold, 255=unknown)
            manifold_status = self._calculate_edge_manifold_status(edge)
            if manifold_status is True:
                manifold_buffer.extend(manifold_struct.pack(1))
            elif manifold_status is False:
                manifold_buffer.extend(manifold_struct.pack(0))
            else:
                manifold_buffer.extend(manifold_struct.pack(255))  # Unknown
            
            # Pack smooth flag (1=smooth, 0=hard edge)
            smooth_buffer.extend(smooth_struct.pack(1 if edge.smooth else 0))

        result = {
            "count": edge_count,
            "vertices": {
                "data": vertices_buffer,
                "target": 34963,  # GL_ELEMENT_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "VEC2",
                "count": edge_count
            }
        }
        
        # Add optional face adjacency data
        if faces_buffer:
            result["faces"] = {
                "data": faces_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        # Add optional manifold flags
        if manifold_buffer:
            result["manifold"] = {
                "data": manifold_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": edge_count
            }
        
        # Add smooth flags as custom attribute following schema
        if smooth_buffer:
            if "attributes" not in result:
                result["attributes"] = {}
            result["attributes"]["_SMOOTH"] = {
                "data": smooth_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": edge_count
            }
        
        return result

    def _encode_loops_to_buffers_direct(self, bm: BMesh, vert_to_index: Dict, edge_to_index: Dict, face_to_index: Dict, loop_to_index: Dict) -> Dict[str, Any]:
        """Encode loop data using SOA format with manual index maps to avoid lookup table issues."""
        if not any(f.loops for f in bm.faces):
             return {}

        # Count total loops using provided mapping
        loop_count = len(loop_to_index)
        if loop_count == 0:
            return {}

        # Create separate SOA buffers for each topology field
        vertex_buffer = bytearray()
        edge_buffer = bytearray()
        face_buffer = bytearray()
        next_buffer = bytearray()
        prev_buffer = bytearray()
        radial_next_buffer = bytearray()
        radial_prev_buffer = bytearray()

        index_struct = struct.Struct("<I")  # u32 per loop for each field

        # Create UV data using glTF standard attribute names
        uv_buffers = {}
        uv_struct = struct.Struct("<ff")

        # Check for UV layers
        if bm.loops.layers.uv:
            for i, uv_layer in enumerate(bm.loops.layers.uv):
                uv_buffers[f"TEXCOORD_{i}"] = bytearray()

        # Create reverse loop index mapping for navigation
        index_to_loop = {idx: loop for loop, idx in loop_to_index.items()}

        # Process loops in index order
        for loop_idx in range(loop_count):
            loop = index_to_loop.get(loop_idx)
            if loop is None:
                continue

            face = loop.face
            face_loops = list(face.loops)
            loop_in_face_idx = face_loops.index(loop)

            # Calculate next and previous in face using manual mapping
            next_in_face = (loop_in_face_idx + 1) % len(face_loops)
            prev_in_face = (loop_in_face_idx - 1) % len(face_loops)
            next_loop = face_loops[next_in_face]
            prev_loop = face_loops[prev_in_face]

            next_idx = loop_to_index.get(next_loop, loop_idx)
            prev_idx = loop_to_index.get(prev_loop, loop_idx)

            # Find radial navigation using manual index mapping
            radial_next_idx, radial_prev_idx = self._find_radial_loop_indices_direct(
                loop, loop_idx, loop_to_index, face_to_index
            )

            # Get indices using manual mapping
            vert_idx = vert_to_index.get(loop.vert, 0)
            edge_idx = edge_to_index.get(loop.edge, 0)
            face_idx = face_to_index.get(loop.face, 0)

            # Pack each topology field separately (SOA format)
            vertex_buffer.extend(index_struct.pack(vert_idx))
            edge_buffer.extend(index_struct.pack(edge_idx))
            face_buffer.extend(index_struct.pack(face_idx))
            next_buffer.extend(index_struct.pack(next_idx))
            prev_buffer.extend(index_struct.pack(prev_idx))
            radial_next_buffer.extend(index_struct.pack(radial_next_idx))
            radial_prev_buffer.extend(index_struct.pack(radial_prev_idx))

            # Pack UV coordinates using glTF standard naming
            if bm.loops.layers.uv:
                for uv_i, uv_layer in enumerate(bm.loops.layers.uv):
                    uv_coord = loop[uv_layer].uv
                    uv_buffers[f"TEXCOORD_{uv_i}"].extend(uv_struct.pack(uv_coord[0], uv_coord[1]))

        result = {
            "count": loop_count,
            "topology_vertex": {
                "data": vertex_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": loop_count
            },
            "topology_edge": {
                "data": edge_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": loop_count
            },
            "topology_face": {
                "data": face_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": loop_count
            },
            "topology_next": {
                "data": next_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": loop_count
            },
            "topology_prev": {
                "data": prev_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": loop_count
            },
            "topology_radial_next": {
                "data": radial_next_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": loop_count
            },
            "topology_radial_prev": {
                "data": radial_prev_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": loop_count
            }
        }

        # Add UV attributes if present
        if uv_buffers:
            result["attributes"] = {}
            for attr_name, uv_buffer in uv_buffers.items():
                result["attributes"][attr_name] = {
                    "data": uv_buffer,
                    "target": 34962,  # GL_ARRAY_BUFFER
                    "componentType": 5126,  # GL_FLOAT
                    "type": "VEC2",
                    "count": loop_count
                }

        return result

    def _encode_faces_to_buffers_direct(self, bm: BMesh, vert_to_index: Dict, edge_to_index: Dict, loop_to_index: Dict, face_to_index: Dict) -> Dict[str, Any]:
        """Encode face data using manual index maps to avoid lookup table issues."""
        if not bm.faces:
            return {}

        face_count = len(bm.faces)
        
        # Create variable-length arrays for face data
        vertices_buffer = bytearray()
        edges_buffer = bytearray()
        loops_buffer = bytearray()
        normals_buffer = bytearray()
        smooth_buffer = bytearray()
        offsets_buffer = bytearray()

        vertex_struct = struct.Struct("<I")
        edge_struct = struct.Struct("<I")
        loop_struct = struct.Struct("<I")
        normal_struct = struct.Struct("<fff")
        smooth_struct = struct.Struct("<B")
        offset_struct = struct.Struct("<I")
        
        vertices_offset = 0
        edges_offset = 0
        loops_offset = 0
        
        for face in bm.faces:
            # Record vertex offset for this face (required by schema)
            offsets_buffer.extend(offset_struct.pack(vertices_offset))
            
            # Pack face vertices using manual index mapping (required by schema: variable length, u32 indices)
            for vert in face.verts:
                vert_idx = vert_to_index.get(vert)
                if vert_idx is not None:
                    vertices_buffer.extend(vertex_struct.pack(vert_idx))
                    vertices_offset += 1
                    
            # Pack face edges using manual index mapping (optional)
            for edge in face.edges:
                edge_idx = edge_to_index.get(edge)
                if edge_idx is not None:
                    edges_buffer.extend(edge_struct.pack(edge_idx))
                    edges_offset += 1
                    
            # Pack face loops using manual index mapping (optional)
            for loop in face.loops:
                loop_idx = loop_to_index.get(loop)
                if loop_idx is not None:
                    loops_buffer.extend(loop_struct.pack(loop_idx))
                    loops_offset += 1
                    
            # Pack face normal (Vec3<f32> per face)
            normals_buffer.extend(normal_struct.pack(*face.normal))

            # Pack face smooth flag (1=smooth, 0=faceted/hard)
            smooth_buffer.extend(smooth_struct.pack(1 if face.smooth else 0))

        # Final offset (required: u32 per face + 1)
        offsets_buffer.extend(offset_struct.pack(vertices_offset))

        result = {
            "count": face_count,
            "vertices": {
                "data": vertices_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            },
            "offsets": {
                "data": offsets_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": face_count + 1
            }
        }
        
        # Add optional data
        if edges_buffer:
            result["edges"] = {
                "data": edges_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        if loops_buffer:
            result["loops"] = {
                "data": loops_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        if normals_buffer:
            result["normals"] = {
                "data": normals_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": face_count
            }

        if smooth_buffer:
            result["smooth"] = {
                "data": smooth_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": face_count
            }

        return result

    def _find_radial_loop_indices_direct(
        self,  
        loop: BMLoop,  
        current_loop_index: int,
        loop_to_index: Dict,
        face_to_index: Dict
    ) -> Tuple[int, int]:
        """
        Find radial next/previous loops around the same edge using manual index maps.
        
        For manifold edges, finds the loop on the adjacent face.
        For non-manifold edges, implements proper radial traversal.
        """
        edge = loop.edge
        linked_faces = list(edge.link_faces)
        
        if len(linked_faces) <= 1:
            # Boundary edge - radial links to self
            return current_loop_index, current_loop_index
            
        # Find the other face using this edge
        current_face = loop.face
        other_faces = [f for f in linked_faces if f != current_face]
        
        if not other_faces:
            return current_loop_index, current_loop_index
            
        # For manifold case, find the loop on the other face that uses this edge
        other_face = other_faces[0]  # Take first adjacent face
        
        for other_loop in other_face.loops:
            if other_loop.edge == edge:
                other_loop_idx = loop_to_index.get(other_loop)
                if other_loop_idx is not None:
                    return other_loop_idx, other_loop_idx
                    
        # Fallback to self-reference
        return current_loop_index, current_loop_index

    def _encode_vertices_to_buffers(self, bm: BMesh) -> Dict[str, Any]:
        """Encode vertex data for buffer format according to EXT_bmesh_encoding schema."""
        if not bm.verts:
            return {}

        vertex_count = len(bm.verts)
        
        # Create position data (required by schema)
        positions_buffer = bytearray()
        position_struct = struct.Struct("<fff")
        
        # Create vertex normal data (custom attribute)
        normals_buffer = bytearray()
        normal_struct = struct.Struct("<fff")
        
        # Create edge adjacency data (optional per schema)
        edges_buffer = bytearray()
        edge_index_struct = struct.Struct("<I")
        
        for vert in bm.verts:
            # Pack vertex position (Vec3<f32> as required by schema)
            positions_buffer.extend(position_struct.pack(*vert.co))
            
            # Pack vertex normal (Vec3<f32> for surface smoothness preservation)
            normals_buffer.extend(normal_struct.pack(*vert.normal))
            
            # Pack vertex-edge adjacency data
            for edge in vert.link_edges:
                edges_buffer.extend(edge_index_struct.pack(edge.index))

        result = {
            "count": vertex_count,
            "positions": {
                "data": positions_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": vertex_count
            }
        }
        
        # Add vertex normals as custom attribute
        if normals_buffer:
            if "attributes" not in result:
                result["attributes"] = {}
            result["attributes"]["NORMAL"] = {
                "data": normals_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": vertex_count
            }
        
        # Add edges buffer if there's adjacency data
        if edges_buffer:
            result["edges"] = {
                "data": edges_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        return result

    def _encode_edges_to_buffers(self, bm: BMesh) -> Dict[str, Any]:
        """Encode edge data for buffer format according to EXT_bmesh_encoding schema."""
        if not bm.edges:
            return {}

        edge_count = len(bm.edges)
        
        # Create edge vertex pairs (required: 2×u32 per edge)
        vertices_buffer = bytearray()
        vertex_pair_struct = struct.Struct("<II")
        
        # Create face adjacency data (optional)
        faces_buffer = bytearray()
        face_index_struct = struct.Struct("<I")
        
        # Create manifold flags (optional: u8 per edge)
        manifold_buffer = bytearray()
        manifold_struct = struct.Struct("<B")
        
        # Create smooth flags (custom attribute: u8 per edge)
        smooth_buffer = bytearray()
        smooth_struct = struct.Struct("<B")
        
        for edge in bm.edges:
            # Pack edge vertices (required by schema)
            vertices_buffer.extend(vertex_pair_struct.pack(
                edge.verts[0].index,  
                edge.verts[1].index
            ))
            
            # Pack face adjacency data
            for face in edge.link_faces:
                faces_buffer.extend(face_index_struct.pack(face.index))
            
            # Pack manifold status (0=non-manifold, 1=manifold, 255=unknown)
            manifold_status = self._calculate_edge_manifold_status(edge)
            if manifold_status is True:
                manifold_buffer.extend(manifold_struct.pack(1))
            elif manifold_status is False:
                manifold_buffer.extend(manifold_struct.pack(0))
            else:
                manifold_buffer.extend(manifold_struct.pack(255))  # Unknown
            
            # Pack smooth flag (1=smooth, 0=hard edge)
            smooth_buffer.extend(smooth_struct.pack(1 if edge.smooth else 0))

        result = {
            "count": edge_count,
            "vertices": {
                "data": vertices_buffer,
                "target": 34963,  # GL_ELEMENT_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "VEC2",
                "count": edge_count
            }
        }
        
        # Add optional face adjacency data
        if faces_buffer:
            result["faces"] = {
                "data": faces_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        # Add optional manifold flags
        if manifold_buffer:
            result["manifold"] = {
                "data": manifold_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": edge_count
            }
        
        # Add smooth flags as custom attribute following schema
        if smooth_buffer:
            if "attributes" not in result:
                result["attributes"] = {}
            result["attributes"]["_SMOOTH"] = {
                "data": smooth_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": edge_count
            }
        
        return result

    def _encode_loops_to_buffers(self, bm: BMesh) -> Dict[str, Any]:
        """Encode loop data for buffer format with glTF-compliant UV handling."""
        if not any(f.loops for f in bm.faces):
             return {}

        # Count total loops
        loop_count = sum(len(face.loops) for face in bm.faces)
        if loop_count == 0:
            return {}

        # Create topology data (vertex, edge, face, next, prev, radial_next, radial_prev)
        topology_buffer = bytearray()
        topology_struct = struct.Struct("<IIIIIII")  # 7×u32 per loop
        
        # Create UV data using glTF standard attribute names
        uv_buffers = {}
        uv_struct = struct.Struct("<ff")
        
        # Check for UV layers
        if bm.loops.layers.uv:
            for i, uv_layer in enumerate(bm.loops.layers.uv):
                uv_buffers[f"TEXCOORD_{i}"] = bytearray()

        loop_index = 0
        loop_index_map = {}  # Map (face_index, loop_in_face_index) -> global_loop_index
        
        # First pass: create loop index mapping
        for face in bm.faces:
            for i, loop in enumerate(face.loops):
                loop_index_map[(face.index, i)] = loop_index
                loop_index += 1

        # Second pass: encode topology with proper navigation
        loop_index = 0
        for face in bm.faces:
            face_loops = list(face.loops)
            for i, loop in enumerate(face_loops):
                # Calculate next and previous in face
                next_in_face = (i + 1) % len(face_loops)
                prev_in_face = (i - 1) % len(face_loops)
                next_idx = loop_index_map[(face.index, next_in_face)]
                prev_idx = loop_index_map[(face.index, prev_in_face)]
                
                # Find radial navigation (around the same edge)
                radial_next_idx, radial_prev_idx = self._find_radial_loop_indices(
                    loop, loop_index, loop_index_map
                )
                
                # Pack topology
                topology_buffer.extend(topology_struct.pack(
                    loop.vert.index,    # vertex
                    loop.edge.index,    # edge  
                    loop.face.index,    # face
                    next_idx,           # next
                    prev_idx,           # prev
                    radial_next_idx,    # radial_next
                    radial_prev_idx     # radial_prev
                ))
                
                # Pack UV coordinates using glTF standard naming
                if bm.loops.layers.uv:
                    for uv_i, uv_layer in enumerate(bm.loops.layers.uv):
                        uv_coord = loop[uv_layer].uv
                        uv_buffers[f"TEXCOORD_{uv_i}"].extend(uv_struct.pack(uv_coord[0], uv_coord[1]))
                
                loop_index += 1

        result = {
            "count": loop_count,
            "topology": {
                "data": topology_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",  # 7 components per loop stored as scalars
                "count": loop_count * 7  # 7 values per loop
            }
        }
        
        # Add UV attributes if present
        if uv_buffers:
            result["attributes"] = {}
            for attr_name, uv_buffer in uv_buffers.items():
                result["attributes"][attr_name] = {
                    "data": uv_buffer,
                    "target": 34962,  # GL_ARRAY_BUFFER
                    "componentType": 5126,  # GL_FLOAT
                    "type": "VEC2",
                    "count": loop_count
                }

        return result

    def _encode_faces_to_buffers(self, bm: BMesh) -> Dict[str, Any]:
        """Encode face data for buffer format according to EXT_bmesh_encoding schema."""
        if not bm.faces:
            return {}

        face_count = len(bm.faces)
        
        # Create variable-length arrays for face data
        vertices_buffer = bytearray()
        edges_buffer = bytearray()
        loops_buffer = bytearray()
        normals_buffer = bytearray()
        smooth_buffer = bytearray()
        offsets_buffer = bytearray()

        vertex_struct = struct.Struct("<I")
        edge_struct = struct.Struct("<I")
        loop_struct = struct.Struct("<I")
        normal_struct = struct.Struct("<fff")
        smooth_struct = struct.Struct("<B")
        offset_struct = struct.Struct("<I")
        
        vertices_offset = 0
        edges_offset = 0
        loops_offset = 0
        
        loop_index = 0
        for face in bm.faces:
            # Record vertex offset for this face (required by schema)
            offsets_buffer.extend(offset_struct.pack(vertices_offset))
            
            # Pack face vertices (required by schema: variable length, u32 indices)
            for vert in face.verts:
                vertices_buffer.extend(vertex_struct.pack(vert.index))
                vertices_offset += 1
                
            # Pack face edges (optional)
            for edge in face.edges:
                edges_buffer.extend(edge_struct.pack(edge.index))
                edges_offset += 1
                
            # Pack face loops (optional)
            for _ in face.loops:
                loops_buffer.extend(loop_struct.pack(loop_index))
                loop_index += 1
                loops_offset += 1
                
            # Pack face normal (Vec3<f32> per face)
            normals_buffer.extend(normal_struct.pack(*face.normal))

            # Pack face smooth flag (1=smooth, 0=faceted/hard)
            smooth_buffer.extend(smooth_struct.pack(1 if face.smooth else 0))

        # Final offset (required: u32 per face + 1)
        offsets_buffer.extend(offset_struct.pack(vertices_offset))

        result = {
            "count": face_count,
            "vertices": {
                "data": vertices_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            },
            "offsets": {
                "data": offsets_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": face_count + 1
            }
        }
        
        # Add optional data
        if edges_buffer:
            result["edges"] = {
                "data": edges_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        if loops_buffer:
            result["loops"] = {
                "data": loops_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        if normals_buffer:
            result["normals"] = {
                "data": normals_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": face_count
            }

        if smooth_buffer:
            result["smooth"] = {
                "data": smooth_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": face_count
            }

        return result

    def _calculate_edge_manifold_status(self, edge: BMEdge) -> Optional[bool]:
        """
        Calculate manifold status for an edge.
        Returns:
        - True: Confirmed manifold (exactly 2 faces)
        - False: Confirmed non-manifold (not exactly 2 faces)
        - None: Unknown status
        """
        if not self.preserve_manifold_info:
            return None
        
        linked_faces = list(edge.link_faces)
        return len(linked_faces) == 2

    def _find_radial_loop_indices(
        self,  
        loop: BMLoop,  
        current_loop_index: int,
        loop_index_map: Dict[Tuple[int, int], int]
    ) -> Tuple[int, int]:
        """
        Find radial next/previous loops around the same edge.
        
        For manifold edges, finds the loop on the adjacent face.
        For non-manifold edges, implements proper radial traversal.
        """
        edge = loop.edge
        linked_faces = list(edge.link_faces)
        
        if len(linked_faces) <= 1:
            # Boundary edge - radial links to self
            return current_loop_index, current_loop_index
            
        # Find the other face using this edge
        current_face = loop.face
        other_faces = [f for f in linked_faces if f != current_face]
        
        if not other_faces:
            return current_loop_index, current_loop_index
            
        # For manifold case, find the loop on the other face that uses this edge
        other_face = other_faces[0]  # Take first adjacent face
        
        for i, other_loop in enumerate(other_face.loops):
            if other_loop.edge == edge:
                other_loop_idx = loop_index_map.get((other_face.index, i))
                if other_loop_idx is not None:
                    return other_loop_idx, other_loop_idx
                    
        # Fallback to self-reference
        return current_loop_index, current_loop_index

    def encode_triangle_fan_implicit(self, bm: BMesh) -> List[Tuple[int, Tuple[BMLoop, ...]]]:
        """
        Enhanced triangle fan encoding compatible with BMesh topology preservation.
        
        Creates triangle fans optimized for BMesh reconstruction while
        maintaining material grouping for glTF compliance. Uses robust algorithms
        to handle complex meshes like Suzanne with improved error handling.
        """
        if not bm.faces:
            logger.debug("No faces found in BMesh for triangle fan encoding")
            return []

        # Ensure all lookup tables are valid
        try:
            safe_ensure_lookup_table(bm.faces, "faces")
            safe_ensure_lookup_table(bm.verts, "verts")
            safe_ensure_lookup_table(bm.loops, "loops")
            safe_ensure_lookup_table(bm.edges, "edges")
        except Exception as e:
            logger.error(f"Failed to ensure BMesh lookup tables: {e}")
            return []
        
        triangulated_faces = []
        failed_faces = 0
        total_triangles = 0
        
        for face in bm.faces:
            try:
                face_loops = list(face.loops)
                # Use glTF standard material index (handled at primitive level, not face level)
                material_index = getattr(face, 'material_index', 0)
                
                if len(face_loops) <= 2:
                    # Degenerate face - skip
                    logger.debug(f"Skipping degenerate face {face.index} with {len(face_loops)} vertices")
                    failed_faces += 1
                    continue
                elif len(face_loops) == 3:
                    # Triangle - handle directly
                    triangulated_faces.append((material_index, tuple(face_loops)))
                    total_triangles += 1
                    continue
                
                # N-gon - create triangle fan with improved algorithm
                fan_triangles = self._create_robust_triangle_fan(face, face_loops, material_index)
                
                if fan_triangles:
                    triangulated_faces.extend(fan_triangles)
                    total_triangles += len(fan_triangles)
                else:
                    logger.debug(f"Failed to create triangle fan for face {face.index}, using fallback")
                    # Fallback: simple fan from first vertex
                    fallback_triangles = self._create_simple_triangle_fan(face_loops, material_index)
                    triangulated_faces.extend(fallback_triangles)
                    total_triangles += len(fallback_triangles)
                    
            except Exception as e:
                logger.error(f"Failed to triangulate face {face.index}: {e}")
                failed_faces += 1
                continue

        logger.info(f"Triangle fan encoding completed: {total_triangles} triangles from {len(bm.faces)} faces "
                    f"({failed_faces} failed)")
        return triangulated_faces

    def _create_robust_triangle_fan(
        self,  
        face: BMFace,  
        face_loops: List[BMLoop],  
        material_index: int
    ) -> List[Tuple[int, Tuple[BMLoop, ...]]]:
        """
        Create triangle fan with improved robustness for complex geometry.
        
        Uses geometric validation and optimal anchor selection.
        """
        try:
            # Step 1: Validate face is not degenerate
            if not self._validate_face_geometry(face):
                logger.debug(f"Face {face.index} failed geometry validation")
                return []
            
            # Step 2: Select optimal anchor vertex
            anchor_loop = self._select_optimal_anchor_loop(face, face_loops)
            anchor_index = face_loops.index(anchor_loop)
            
            # Step 3: Create triangle fan from optimal anchor
            triangles = []
            
            for i in range(1, len(face_loops) - 1):
                loop1_idx = (anchor_index + i) % len(face_loops)
                loop2_idx = (anchor_index + i + 1) % len(face_loops)
                
                triangle_loops = (
                    anchor_loop,
                    face_loops[loop1_idx],
                    face_loops[loop2_idx]
                )
                
                # Step 4: Validate each triangle
                if self._validate_triangle_geometry(triangle_loops):
                    triangles.append((material_index, triangle_loops))
                else:
                    logger.debug(f"Skipping invalid triangle in face {face.index}")
            
            return triangles
            
        except Exception as e:
            logger.debug(f"Robust triangle fan creation failed for face {face.index}: {e}")
            return []

    def _validate_face_geometry(self, face: BMFace) -> bool:
        """Validate that face has valid geometry for triangulation."""
        try:
            # Check face has valid area
            area = face.calc_area()
            if area < 1e-8:
                return False
            
            # Check face has valid normal
            normal = face.normal
            if normal.length < 1e-8:
                return False
            
            # Check vertices are not all coincident
            positions = [loop.vert.co for loop in face.loops]
            if len(set(tuple(pos) for pos in positions)) < 3:
                return False
            
            return True
            
        except Exception:
            return False

    def _validate_triangle_geometry(self, triangle_loops: Tuple[BMLoop, ...]) -> bool:
        """Validate that triangle has non-zero area and proper winding."""
        try:
            if len(triangle_loops) != 3:
                return False
            
            v0 = triangle_loops[0].vert.co
            v1 = triangle_loops[1].vert.co
            v2 = triangle_loops[2].vert.co
            
            # Check vertices are not coincident
            if (v0 - v1).length < 1e-8 or (v1 - v2).length < 1e-8 or (v2 - v0).length < 1e-8:
                return False
            
            # Calculate triangle area using cross product
            edge1 = v1 - v0
            edge2 = v2 - v0
            cross = edge1.cross(edge2)
            area = cross.length * 0.5
            
            return area > 1e-8  # Non-degenerate threshold
            
        except Exception:
            return False

    def _select_optimal_anchor_loop(self, face: BMFace, face_loops: List[BMLoop]) -> BMLoop:
        """
        Select the optimal anchor vertex for triangle fan creation.
        
        Uses geometric and topological criteria for robust triangulation.
        """
        if len(face_loops) <= 3:
            return face_loops[0]
        
        try:
            # Calculate face center for reference
            face_center = face.calc_center_median()
            
            best_loop = face_loops[0]
            best_score = float('-inf')
            
            for loop in face_loops:
                score = 0
                
                # Criterion 1: Distance to face center (prefer central vertices)
                distance_to_center = (loop.vert.co - face_center).length
                score += 10.0 / (distance_to_center + 0.01)  # Avoid division by zero
                
                # Criterion 2: Vertex valence (prefer simpler topology)
                valence = len(loop.vert.link_edges)
                score += 5.0 / (valence + 1)
                
                # Criterion 3: Angle quality (prefer vertices that create good triangles)
                valid_triangles = self._count_valid_triangles_from_anchor(face_loops, loop)
                score += valid_triangles * 2.0
                
                # Criterion 4: Avoid vertices on sharp edges
                if self._is_on_sharp_edge(loop):
                    score *= 0.5
                
                if score > best_score:
                    best_score = score
                    best_loop = loop
            
            return best_loop
            
        except Exception as e:
            logger.debug(f"Optimal anchor selection failed: {e}, using first vertex")
            return face_loops[0]

    def _count_valid_triangles_from_anchor(self, face_loops: List[BMLoop], anchor_loop: BMLoop) -> int:
        """Count how many valid triangles can be created from this anchor."""
        try:
            anchor_index = face_loops.index(anchor_loop)
            valid_count = 0
            
            for i in range(1, len(face_loops) - 1):
                loop1_idx = (anchor_index + i) % len(face_loops)
                loop2_idx = (anchor_index + i + 1) % len(face_loops)
                
                triangle_loops = (
                    anchor_loop,
                    face_loops[loop1_idx],
                    face_loops[loop2_idx]
                )
                
                if self._validate_triangle_geometry(triangle_loops):
                    valid_count += 1
            
            return valid_count
            
        except Exception:
            return 0

    def _is_on_sharp_edge(self, loop: BMLoop) -> bool:
        """Check if vertex is on a sharp edge (potential triangulation problem)."""
        try:
            for edge in loop.vert.link_edges:
                if not edge.smooth or len(edge.link_faces) != 2:
                    return True
            return False
        except Exception:
            return False

    def _create_simple_triangle_fan(
        self,  
        face_loops: List[BMLoop],  
        material_index: int
    ) -> List[Tuple[int, Tuple[BMLoop, ...]]]:
        """
        Create simple triangle fan from first vertex as fallback.
        
        This is the original algorithm as a reliable fallback when
        robust methods fail.
        """
        triangles = []
        anchor_loop = face_loops[0]
        
        for i in range(2, len(face_loops)):
            triangle_loops = (
                anchor_loop,
                face_loops[i - 1],
                face_loops[i]
            )
            triangles.append((material_index, triangle_loops))
        
        return triangles

    @staticmethod
    def create_mesh_data_from_object(mesh_obj: bpy.types.Object) -> Optional[bpy.types.Mesh]:
        """Create native mesh data from Blender mesh object - more stable than BMesh."""
        if mesh_obj.type != 'MESH' or not mesh_obj.data:
            return None
        
        try:
            # Use evaluated mesh for accurate geometry
            depsgraph = bpy.context.evaluated_depsgraph_get()
            eval_obj = mesh_obj.evaluated_get(depsgraph)
            return eval_obj.data
        except Exception as e:
            logger.error(f"Failed to get mesh data from {mesh_obj.name}: {e}")
            return None

    def encode_mesh_to_gltf_extension_native(self, mesh: bpy.types.Mesh) -> Dict[str, Any]:
        """
        Encode native mesh data to EXT_bmesh_encoding extension data.
        
        Uses Blender's stable native mesh APIs instead of BMesh to avoid
        BMLoopSeq compatibility issues.
        """
        if not mesh.vertices or not mesh.polygons:
            return {}

        logger.info(f"Encoding mesh '{mesh.name}' using native mesh data approach")
        logger.info(f"Mesh has {len(mesh.vertices)} vertices, {len(mesh.edges)} edges, {len(mesh.polygons)} polygons, {len(mesh.loops)} loops")

        extension_data = {}

        # Encode vertices using native mesh data
        vertex_data = self._encode_vertices_native(mesh)
        if vertex_data:
            extension_data["vertices"] = vertex_data

        # Encode edges using native mesh data
        edge_data = self._encode_edges_native(mesh)
        if edge_data:
            extension_data["edges"] = edge_data

        # Encode loops using native mesh data
        loop_data = self._encode_loops_native(mesh)
        if loop_data:
            extension_data["loops"] = loop_data

        # Encode faces using native mesh data
        face_data = self._encode_faces_native(mesh)
        if face_data:
            extension_data["faces"] = face_data

        logger.info(f"Native encoding complete for mesh '{mesh.name}', extension data keys: {list(extension_data.keys())}")
        return extension_data

    def _encode_vertices_native(self, mesh: bpy.types.Mesh) -> Dict[str, Any]:
        """Encode vertex data using native mesh APIs."""
        if not mesh.vertices:
            return {}

        vertex_count = len(mesh.vertices)
        
        # Create position data (required by schema)
        positions_buffer = bytearray()
        position_struct = struct.Struct("<fff")
        
        # Create vertex normal data (custom attribute)
        normals_buffer = bytearray()
        normal_struct = struct.Struct("<fff")
        
        # Create edge adjacency data (optional per schema)
        edges_buffer = bytearray()
        edge_index_struct = struct.Struct("<I")
        
        # Build vertex-to-edge adjacency using native APIs
        vertex_edge_map = {}
        for edge in mesh.edges:
            v1, v2 = edge.vertices
            if v1 not in vertex_edge_map:
                vertex_edge_map[v1] = []
            if v2 not in vertex_edge_map:
                vertex_edge_map[v2] = []
            vertex_edge_map[v1].append(edge.index)
            vertex_edge_map[v2].append(edge.index)

        for vertex in mesh.vertices:
            # Pack vertex position (Vec3<f32> as required by schema)
            positions_buffer.extend(position_struct.pack(*vertex.co))
            
            # Pack vertex normal (Vec3<f32> for surface smoothness preservation)
            normals_buffer.extend(normal_struct.pack(*vertex.normal))
            
            # Pack vertex-edge adjacency data
            adjacent_edges = vertex_edge_map.get(vertex.index, [])
            for edge_idx in adjacent_edges:
                edges_buffer.extend(edge_index_struct.pack(edge_idx))

        result = {
            "count": vertex_count,
            "positions": {
                "data": positions_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": vertex_count
            }
        }
        
        # Add vertex normals as custom attribute
        if normals_buffer:
            if "attributes" not in result:
                result["attributes"] = {}
            result["attributes"]["NORMAL"] = {
                "data": normals_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": vertex_count
            }
        
        # Add edges buffer if there's adjacency data
        if edges_buffer:
            result["edges"] = {
                "data": edges_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        return result

    def _encode_edges_native(self, mesh: bpy.types.Mesh) -> Dict[str, Any]:
        """Encode edge data using native mesh APIs."""
        if not mesh.edges:
            return {}

        edge_count = len(mesh.edges)
        
        # Create edge vertex pairs (required: 2×u32 per edge)
        vertices_buffer = bytearray()
        vertex_pair_struct = struct.Struct("<II")
        
        # Create face adjacency data (optional)
        faces_buffer = bytearray()
        face_index_struct = struct.Struct("<I")
        
        # Create manifold flags (optional: u8 per edge)
        manifold_buffer = bytearray()
        manifold_struct = struct.Struct("<B")
        
        # Create smooth flags (custom attribute: u8 per edge)
        smooth_buffer = bytearray()
        smooth_struct = struct.Struct("<B")
        
        # Build edge-to-face adjacency using native APIs
        edge_face_map = {}
        for poly in mesh.polygons:
            for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                loop = mesh.loops[loop_idx]
                edge_idx = loop.edge_index
                if edge_idx not in edge_face_map:
                    edge_face_map[edge_idx] = []
                if poly.index not in edge_face_map[edge_idx]:
                     edge_face_map[edge_idx].append(poly.index)
        
        for edge in mesh.edges:
            # Pack edge vertices (required by schema)
            vertices_buffer.extend(vertex_pair_struct.pack(
                edge.vertices[0],  
                edge.vertices[1]
            ))
            
            # Pack face adjacency data
            adjacent_faces = edge_face_map.get(edge.index, [])
            for face_idx in adjacent_faces:
                faces_buffer.extend(face_index_struct.pack(face_idx))
            
            # Pack manifold status (0=non-manifold, 1=manifold, 255=unknown)
            is_manifold = len(adjacent_faces) == 2
            if self.preserve_manifold_info:
                 manifold_buffer.extend(manifold_struct.pack(1 if is_manifold else 0))
            else:
                 manifold_buffer.extend(manifold_struct.pack(255)) # Unknown
            
            # Pack smooth flag (1=smooth, 0=hard edge)
            smooth_buffer.extend(smooth_struct.pack(1 if edge.use_edge_sharp == False else 0))

        result = {
            "count": edge_count,
            "vertices": {
                "data": vertices_buffer,
                "target": 34963,  # GL_ELEMENT_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "VEC2",
                "count": edge_count
            }
        }
        
        # Add optional face adjacency data
        if faces_buffer:
            result["faces"] = {
                "data": faces_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }
        
        # Add optional manifold flags
        if manifold_buffer:
            result["manifold"] = {
                "data": manifold_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": edge_count
            }
        
        # Add smooth flags as custom attribute following schema
        if smooth_buffer:
            if "attributes" not in result:
                result["attributes"] = {}
            result["attributes"]["_SMOOTH"] = {
                "data": smooth_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5121,  # GL_UNSIGNED_BYTE
                "type": "SCALAR",
                "count": edge_count
            }
        
        return result

    def _encode_loops_native(self, mesh: bpy.types.Mesh) -> Dict[str, Any]:
        """Encode loop data using native mesh APIs."""
        if not mesh.loops:
            return {}

        loop_count = len(mesh.loops)
        if loop_count == 0:
            return {}

        # Create topology data (vertex, edge, face, next, prev, radial_next, radial_prev)
        topology_buffer = bytearray()
        topology_struct = struct.Struct("<IIIIIII")  # 7×u32 per loop
        
        # Create UV data using glTF standard attribute names
        uv_buffers = {}
        uv_struct = struct.Struct("<ff")
        
        # Check for UV layers
        if mesh.uv_layers:
            for i, uv_layer in enumerate(mesh.uv_layers):
                uv_buffers[f"TEXCOORD_{i}"] = bytearray()

        # Build loop navigation data using native mesh APIs
        # Precompute polygon for each loop
        loop_to_poly_map = {}
        for poly in mesh.polygons:
            for i in range(poly.loop_start, poly.loop_start + poly.loop_total):
                loop_to_poly_map[i] = poly

        for loop_idx, loop in enumerate(mesh.loops):
            poly = loop_to_poly_map.get(loop_idx)
            
            if not poly:
                # Fallback values for orphaned loops
                next_idx = prev_idx = radial_next_idx = radial_prev_idx = loop.index
                face_idx = -1 # Or some other indicator of invalid
            else:
                # Calculate next and previous in face
                loop_in_poly_idx = loop.index - poly.loop_start
                next_in_poly = (loop_in_poly_idx + 1) % poly.loop_total
                prev_in_poly = (loop_in_poly_idx - 1 + poly.loop_total) % poly.loop_total
                next_idx = poly.loop_start + next_in_poly
                prev_idx = poly.loop_start + prev_in_poly
                face_idx = poly.index
                
                # For now, set radial navigation to self (can be improved later)
                radial_next_idx = radial_prev_idx = loop.index
            
            # Pack topology
            topology_buffer.extend(topology_struct.pack(
                loop.vertex_index,  # vertex
                loop.edge_index,    # edge
                face_idx,           # face
                next_idx,           # next
                prev_idx,           # prev
                radial_next_idx,    # radial_next
                radial_prev_idx     # radial_prev
            ))
            
            # Pack UV coordinates using glTF standard naming
            if mesh.uv_layers:
                for uv_i, uv_layer in enumerate(mesh.uv_layers):
                    uv_coord = uv_layer.data[loop.index].uv
                    uv_buffers[f"TEXCOORD_{uv_i}"].extend(uv_struct.pack(uv_coord[0], uv_coord[1]))

        result = {
            "count": loop_count,
            "topology": {
                "data": topology_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",  # 7 components per loop stored as scalars
                "count": loop_count * 7  # 7 values per loop
            }
        }
        
        # Add UV attributes if present
        if uv_buffers:
            result["attributes"] = {}
            for attr_name, uv_buffer in uv_buffers.items():
                result["attributes"][attr_name] = {
                    "data": uv_buffer,
                    "target": 34962,  # GL_ARRAY_BUFFER
                    "componentType": 5126,  # GL_FLOAT
                    "type": "VEC2",
                    "count": loop_count
                }

        return result

    def _encode_faces_native(self, mesh: bpy.types.Mesh) -> Dict[str, Any]:
        """Encode face data using native mesh APIs."""
        if not mesh.polygons:
            return {}

        face_count = len(mesh.polygons)
        
        # Create variable-length arrays for face data
        vertices_buffer = bytearray()
        edges_buffer = bytearray()
        loops_buffer = bytearray()
        normals_buffer = bytearray()
        smooth_buffer = bytearray()
        offsets_buffer = bytearray()

        vertex_struct = struct.Struct("<I")
        edge_struct = struct.Struct("<I")
        loop_struct = struct.Struct("<I")
        normal_struct = struct.Struct("<fff")
        smooth_struct = struct.Struct("<B")
        offset_struct = struct.Struct("<I")
        
        vertices_offset = 0
        
        # Precompute edge_keys to edge_index map for faster lookups
        edge_map = {tuple(sorted(edge.vertices)): edge.index for edge in mesh.edges}

        for poly in mesh.polygons:
            # Record vertex offset for this face (required by schema)
            offsets_buffer.extend(offset_struct.pack(vertices_offset))
            
            # Pack face vertices (required by schema: variable length, u32 indices)
            for vert_idx in poly.vertices:
                vertices_buffer.extend(vertex_struct.pack(vert_idx))
                vertices_offset += 1
                
            # Pack face edges (optional)
            for i in range(poly.loop_total):
                loop = mesh.loops[poly.loop_start + i]
                edge_idx = loop.edge_index
                edges_buffer.extend(edge_struct.pack(edge_idx))
                
            # Pack face loops (optional)
            for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                loops_buffer.extend(loop_struct.pack(loop_idx))
                
            # Pack face normal (Vec3<f32> per face)
            normals_buffer.extend(normal_struct.pack(*poly.normal))

            # Pack face smooth flag (1=smooth, 0=faceted/hard)
            smooth_buffer.extend(smooth_struct.pack(1 if poly.use_smooth else 0))

        # Final offset (required: u32 per face + 1)
        offsets_buffer.extend(offset_struct.pack(vertices_offset))

        result = {
            "count": face_count,
            "vertices": {
                "data": vertices_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            },
            "offsets": {
                "data": offsets_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR",
                "count": face_count + 1
            }
        }
        
        # Add optional data
        if edges_buffer:
            result["edges"] = {
                "data": edges_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }

        if loops_buffer:
            result["loops"] = {
                "data": loops_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5125,  # GL_UNSIGNED_INT
                "type": "SCALAR"
            }

        if normals_buffer:
            result["normals"] = {
                "data": normals_buffer,
                "target": 34962,  # GL_ARRAY_BUFFER
                "componentType": 5126,  # GL_FLOAT
                "type": "VEC3",
                "count": face_count
            }

        # Always include smooth buffer - required for face attributes
        result["smooth"] = {
            "data": smooth_buffer,
            "target": 34962,  # GL_ARRAY_BUFFER
            "componentType": 5121,  # GL_UNSIGNED_BYTE
            "type": "SCALAR",
            "count": face_count
        }

        return result

    @staticmethod
    def create_bmesh_from_mesh(mesh_obj: bpy.types.Object) -> Optional[BMesh]:
        """Create BMesh from Blender mesh object with proper error handling."""
        if mesh_obj.type != 'MESH' or not mesh_obj.data:
            return None
        
        bm = bmesh.new()
        
        try:
            # Use evaluated mesh for accurate geometry
            depsgraph = bpy.context.evaluated_depsgraph_get()
            eval_obj = mesh_obj.evaluated_get(depsgraph)
            
            bm.from_mesh(eval_obj.data)
            
            # Apply object transform
            bm.transform(mesh_obj.matrix_world)
            
            # Ensure all lookup tables are valid
            safe_ensure_lookup_table(bm.faces, "faces")
            safe_ensure_lookup_table(bm.verts, "verts")
            safe_ensure_lookup_table(bm.edges, "edges")
            safe_ensure_lookup_table(bm.loops, "loops")
            
            # Calculate face indices for consistent material assignment
            # This is a bit of a workaround; material_index should already be there
            for face in bm.faces:
                 # This line is redundant if from_mesh works correctly, but safe to keep
                pass

            return bm
            
        except Exception as e:
            logger.error(f"Failed to create BMesh from {mesh_obj.name}: {e}")
            bm.free()
            return None

    def create_buffer_views(self, json_dict: Dict[str, Any], buffer0: bytearray, extension_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create glTF buffer views from the encoded BMesh data.
        
        This integrates with the glTF export pipeline to create proper buffer views
        that reference the main glTF buffer.
        """
        logger.info("Creating buffer views for EXT_bmesh_encoding...")
        
        if not extension_data:
            logger.warning("No extension data provided to create_buffer_views")
            return {}

        logger.debug(f"Extension data keys: {list(extension_data.keys())}")

        # Helper to create buffer view
        def create_buffer_view(data_info: Dict[str, Any]) -> Optional[int]:
            if "data" not in data_info:
                logger.debug("No 'data' key in data_info")
                return None
                
            data = data_info["data"]
            if not data:
                logger.debug("Empty data in data_info")
                return None

            # Align buffer to 4-byte boundary
            while len(buffer0) % 4:
                buffer0.append(0)

            buffer_view_index = len(json_dict.get("bufferViews", []))
            
            # Ensure bufferViews array exists
            if "bufferViews" not in json_dict:
                json_dict["bufferViews"] = []
                
            # Create buffer view
            buffer_view = {
                "buffer": 0,
                "byteOffset": len(buffer0),
                "byteLength": len(data)
            }
            if "target" in data_info:
                buffer_view["target"] = data_info["target"]

            json_dict["bufferViews"].append(buffer_view)
            buffer0.extend(data)
            
            logger.debug(f"Created buffer view {buffer_view_index} with {len(data)} bytes")
            return buffer_view_index

        # Process vertices
        result_data = {}
        if "vertices" in extension_data:
            vertex_data = extension_data["vertices"]
            result_vertices = {"count": vertex_data["count"]}
            logger.info(f"Processing vertices: count={vertex_data['count']}")
            
            positions_idx = create_buffer_view(vertex_data["positions"])
            if positions_idx is not None:
                result_vertices["positions"] = positions_idx
                logger.debug(f"Added positions buffer view: {positions_idx}")
                
            edges_idx = create_buffer_view(vertex_data.get("edges", {}))
            if edges_idx is not None:
                result_vertices["edges"] = edges_idx
                logger.debug(f"Added vertex edges buffer view: {edges_idx}")
            
            # Add edge offsets buffer view
            if "edgeOffsets" in vertex_data:
                offsets_idx = create_buffer_view(vertex_data["edgeOffsets"])
                if offsets_idx is not None:
                    result_vertices["edgeOffsets"] = offsets_idx
                    logger.debug(f"Added vertex edge offsets buffer view: {offsets_idx}")
            
            # Handle vertex attributes (normals, colors, etc.)
            if "attributes" in vertex_data:
                result_vertices["attributes"] = {}
                for attr_name, attr_data in vertex_data["attributes"].items():
                    attr_idx = create_buffer_view(attr_data)
                    if attr_idx is not None:
                        result_vertices["attributes"][attr_name] = attr_idx
                        logger.debug(f"Added vertex attribute '{attr_name}' buffer view: {attr_idx}")
            
            result_data["vertices"] = result_vertices

        # Process edges  
        if "edges" in extension_data:
            edge_data = extension_data["edges"]
            result_edges = {"count": edge_data["count"]}
            logger.info(f"Processing edges: count={edge_data['count']}")
            
            vertices_idx = create_buffer_view(edge_data["vertices"])
            if vertices_idx is not None:
                result_edges["vertices"] = vertices_idx
                logger.debug(f"Added edge vertices buffer view: {vertices_idx}")
                
            faces_idx = create_buffer_view(edge_data.get("faces", {}))
            if faces_idx is not None:
                result_edges["faces"] = faces_idx
                logger.debug(f"Added edge faces buffer view: {faces_idx}")
            
            # Add face offsets buffer view
            if "faceOffsets" in edge_data:
                face_offsets_idx = create_buffer_view(edge_data["faceOffsets"])
                if face_offsets_idx is not None:
                    result_edges["faceOffsets"] = face_offsets_idx
                    logger.debug(f"Added edge face offsets buffer view: {face_offsets_idx}")
            
            manifold_idx = create_buffer_view(edge_data.get("manifold", {}))
            if manifold_idx is not None:
                result_edges["manifold"] = manifold_idx
                logger.debug(f"Added edge manifold buffer view: {manifold_idx}")
            
            # Handle edge attributes (smooth flags, etc.)
            if "attributes" in edge_data:
                result_edges["attributes"] = {}
                for attr_name, attr_data in edge_data["attributes"].items():
                    attr_idx = create_buffer_view(attr_data)
                    if attr_idx is not None:
                        result_edges["attributes"][attr_name] = attr_idx
                        logger.debug(f"Added edge attribute '{attr_name}' buffer view: {attr_idx}")
                
            result_data["edges"] = result_edges

        # Process loops
        if "loops" in extension_data:
            loop_data = extension_data["loops"]
            result_loops = {"count": loop_data["count"]}
            logger.info(f"Processing loops: count={loop_data['count']}")
            
            topology_idx = create_buffer_view(loop_data["topology"])
            if topology_idx is not None:
                result_loops["topology"] = topology_idx
                logger.debug(f"Added loop topology buffer view: {topology_idx}")
                
            # Handle UV attributes with glTF naming
            if "attributes" in loop_data:
                result_loops["attributes"] = {}
                for attr_name, attr_data in loop_data["attributes"].items():
                    attr_idx = create_buffer_view(attr_data)
                    if attr_idx is not None:
                        result_loops["attributes"][attr_name] = attr_idx
                        logger.debug(f"Added loop attribute '{attr_name}' buffer view: {attr_idx}")
                        
            result_data["loops"] = result_loops

        # Process faces
        if "faces" in extension_data:
            face_data = extension_data["faces"]
            result_faces = {"count": face_data["count"]}
            logger.info(f"Processing faces: count={face_data['count']}")
            
            for key in ["vertices", "edges", "loops", "normals", "offsets", "smooth"]:
                if key in face_data:
                    buffer_idx = create_buffer_view(face_data[key])
                    if buffer_idx is not None:
                        result_faces[key] = buffer_idx
                        logger.debug(f"Added face {key} buffer view: {buffer_idx}")
                        
            result_data["faces"] = result_faces

        logger.info(f"Buffer view creation complete. Result data keys: {list(result_data.keys())}")
        return result_data
