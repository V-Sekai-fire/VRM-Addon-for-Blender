# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
"""Migration for EXT_bmesh_encoding extension data."""

from typing import Optional

import bpy
from bpy.types import Armature, Context, Object
from idprop.types import IDPropertyGroup

from ...common.logger import get_logger
from ..extension import get_armature_extension

logger = get_logger(__name__)


def migrate(context: Context, armature: Object) -> None:
    """Migrate bmesh_encoding extension data from preprocessor storage, user extension storage, or IDPropertyGroup to proper property groups."""
    if not armature or armature.type != "ARMATURE":
        return
    
    armature_data = armature.data
    if not isinstance(armature_data, Armature):
        return
    
    bmesh_encoding_data = None
    migration_source = None
    
    # First priority: Check preprocessor extracted data
    from .preprocessor import BmeshEncodingPreprocessor
    preprocessor_data = BmeshEncodingPreprocessor.get_extracted_data(armature_data.name)
    
    if preprocessor_data:
        # Use data from preprocessor extraction
        bmesh_encoding_data = preprocessor_data
        migration_source = "preprocessor_extraction"
        logger.info(f"Found EXT_bmesh_encoding data in preprocessor storage for armature: {armature.name}")

    if not bmesh_encoding_data:
        return
    
    logger.info(f"Migrating EXT_bmesh_encoding data for armature: {armature.name} (source: {migration_source})")
    
    # Get the typed property group
    ext = get_armature_extension(armature_data)
    bmesh_encoding_props = ext.bmesh_encoding
    
    # Migrate basic properties
    enabled = bmesh_encoding_data.get("enabled")
    if isinstance(enabled, bool):
        bmesh_encoding_props.enabled = enabled
    
    use_buffer_format = bmesh_encoding_data.get("use_buffer_format")  
    if isinstance(use_buffer_format, bool):
        bmesh_encoding_props.use_buffer_format = use_buffer_format
        
    buffer_threshold = bmesh_encoding_data.get("buffer_threshold")
    if isinstance(buffer_threshold, int):
        bmesh_encoding_props.buffer_threshold = buffer_threshold
        
    preserve_manifold_info = bmesh_encoding_data.get("preserve_manifold_info")
    if isinstance(preserve_manifold_info, bool):
        bmesh_encoding_props.preserve_manifold_info = preserve_manifold_info
    
    # Migrate vertex data
    vertices_data = bmesh_encoding_data.get("vertices")
    if isinstance(vertices_data, list):
        bmesh_encoding_props.vertices.clear()
        for vertex_data in vertices_data:
            # Handle both IDPropertyGroup (legacy) and dict (from preprocessor)
            if not isinstance(vertex_data, (IDPropertyGroup, dict)):
                continue
            vertex_prop = bmesh_encoding_props.vertices.add()
            migrate_vertex_properties(vertex_data, vertex_prop)
    
    # Migrate edge data  
    edges_data = bmesh_encoding_data.get("edges")
    if isinstance(edges_data, list):
        bmesh_encoding_props.edges.clear()
        for edge_data in edges_data:
            # Handle both IDPropertyGroup (legacy) and dict (from preprocessor)
            if not isinstance(edge_data, (IDPropertyGroup, dict)):
                continue
            edge_prop = bmesh_encoding_props.edges.add()
            migrate_edge_properties(edge_data, edge_prop)
    
    # Migrate loop data
    loops_data = bmesh_encoding_data.get("loops")
    if isinstance(loops_data, list):
        bmesh_encoding_props.loops.clear()
        for loop_data in loops_data:
            # Handle both IDPropertyGroup (legacy) and dict (from preprocessor)
            if not isinstance(loop_data, (IDPropertyGroup, dict)):
                continue
            loop_prop = bmesh_encoding_props.loops.add()
            migrate_loop_properties(loop_data, loop_prop)
    
    # Migrate face data
    faces_data = bmesh_encoding_data.get("faces")
    if isinstance(faces_data, list):
        bmesh_encoding_props.faces.clear()
        for face_data in faces_data:
            # Handle both IDPropertyGroup (legacy) and dict (from preprocessor)
            if not isinstance(face_data, (IDPropertyGroup, dict)):
                continue
            face_prop = bmesh_encoding_props.faces.add()
            migrate_face_properties(face_data, face_prop)
    
    logger.info(f"EXT_bmesh_encoding migration completed for armature: {armature.name}")


def migrate_vertex_properties(vertex_data, vertex_prop) -> None:
    """Migrate vertex property data from dict or IDPropertyGroup."""
    vertex_id = vertex_data.get("id")
    if isinstance(vertex_id, int):
        vertex_prop.id = vertex_id
        
    position = vertex_data.get("position")
    if isinstance(position, (list, tuple)) and len(position) >= 3:
        vertex_prop.position = (float(position[0]), float(position[1]), float(position[2]))


def migrate_edge_properties(edge_data, edge_prop) -> None:
    """Migrate edge property data from dict or IDPropertyGroup."""
    edge_id = edge_data.get("id")
    if isinstance(edge_id, int):
        edge_prop.id = edge_id
        
    vertex_a = edge_data.get("vertex_a")
    if isinstance(vertex_a, int):
        edge_prop.vertex_a = vertex_a
        
    vertex_b = edge_data.get("vertex_b")
    if isinstance(vertex_b, int):
        edge_prop.vertex_b = vertex_b
        
    manifold = edge_data.get("manifold")
    if isinstance(manifold, bool):
        edge_prop.manifold = manifold
        
    manifold_unknown = edge_data.get("manifold_unknown")
    if isinstance(manifold_unknown, bool):
        edge_prop.manifold_unknown = manifold_unknown


def migrate_loop_properties(loop_data, loop_prop) -> None:
    """Migrate loop property data from dict or IDPropertyGroup."""
    loop_id = loop_data.get("id")
    if isinstance(loop_id, int):
        loop_prop.id = loop_id
        
    vertex = loop_data.get("vertex")
    if isinstance(vertex, int):
        loop_prop.vertex = vertex
        
    edge = loop_data.get("edge")
    if isinstance(edge, int):
        loop_prop.edge = edge
        
    face = loop_data.get("face")
    if isinstance(face, int):
        loop_prop.face = face
        
    next_loop = loop_data.get("next_loop")
    if isinstance(next_loop, int):
        loop_prop.next_loop = next_loop
        
    prev_loop = loop_data.get("prev_loop")
    if isinstance(prev_loop, int):
        loop_prop.prev_loop = prev_loop
        
    radial_next = loop_data.get("radial_next")
    if isinstance(radial_next, int):
        loop_prop.radial_next = radial_next
        
    radial_prev = loop_data.get("radial_prev")
    if isinstance(radial_prev, int):
        loop_prop.radial_prev = radial_prev
        
    uv = loop_data.get("uv")
    if isinstance(uv, (list, tuple)) and len(uv) >= 2:
        loop_prop.uv = (float(uv[0]), float(uv[1]))


def migrate_face_properties(face_data, face_prop) -> None:
    """Migrate face property data from dict or IDPropertyGroup."""
    face_id = face_data.get("id")
    if isinstance(face_id, int):
        face_prop.id = face_id
        
    normal = face_data.get("normal")
    if isinstance(normal, (list, tuple)) and len(normal) >= 3:
        face_prop.normal = (float(normal[0]), float(normal[1]), float(normal[2]))
        
    material_index = face_data.get("material_index")
    if isinstance(material_index, int):
        face_prop.material_index = material_index
        
    vertex_count = face_data.get("vertex_count")
    if isinstance(vertex_count, int):
        face_prop.vertex_count = vertex_count
