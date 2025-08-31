# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
"""Property groups for EXT_bmesh_encoding extension."""

from typing import TYPE_CHECKING

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
)
from bpy.types import PropertyGroup

if TYPE_CHECKING:
    from ..property_group import CollectionPropertyProtocol


class BmeshEncodingVertexPropertyGroup(PropertyGroup):
    """BMesh vertex data for EXT_bmesh_encoding."""
    
    id: IntProperty(  # type: ignore[valid-type]
        name="ID",
        description="Unique vertex identifier",
        min=0,
    )
    
    position: FloatVectorProperty(  # type: ignore[valid-type]
        name="Position",
        description="3D vertex position",
        size=3,
        subtype="XYZ",
    )
    
    # Note: edges will be stored as indices to edge array
    # attributes will be handled separately for extensibility
    
    if TYPE_CHECKING:
        id: int  # type: ignore[no-redef]
        position: tuple[float, float, float]  # type: ignore[no-redef]


class BmeshEncodingEdgePropertyGroup(PropertyGroup):
    """BMesh edge data for EXT_bmesh_encoding."""
    
    id: IntProperty(  # type: ignore[valid-type]
        name="ID", 
        description="Unique edge identifier",
        min=0,
    )
    
    vertex_a: IntProperty(  # type: ignore[valid-type]
        name="Vertex A",
        description="First vertex index",
        min=0,
    )
    
    vertex_b: IntProperty(  # type: ignore[valid-type]
        name="Vertex B", 
        description="Second vertex index",
        min=0,
    )
    
    manifold: BoolProperty(  # type: ignore[valid-type]
        name="Manifold",
        description="Manifold status: True (manifold), False (non-manifold). None means unknown",
        default=True,
    )
    
    manifold_unknown: BoolProperty(  # type: ignore[valid-type]
        name="Manifold Status Unknown",
        description="Whether manifold status is unknown (null in JSON)",
        default=False,
    )
    
    if TYPE_CHECKING:
        id: int  # type: ignore[no-redef]
        vertex_a: int  # type: ignore[no-redef]
        vertex_b: int  # type: ignore[no-redef]
        manifold: bool  # type: ignore[no-redef]
        manifold_unknown: bool  # type: ignore[no-redef]


class BmeshEncodingLoopPropertyGroup(PropertyGroup):
    """BMesh loop data for EXT_bmesh_encoding."""
    
    id: IntProperty(  # type: ignore[valid-type]
        name="ID",
        description="Unique loop identifier", 
        min=0,
    )
    
    vertex: IntProperty(  # type: ignore[valid-type]
        name="Vertex",
        description="Corner vertex index",
        min=0,
    )
    
    edge: IntProperty(  # type: ignore[valid-type]
        name="Edge",
        description="Outgoing edge index",
        min=0,
    )
    
    face: IntProperty(  # type: ignore[valid-type]
        name="Face",
        description="Containing face index",
        min=0,
    )
    
    next_loop: IntProperty(  # type: ignore[valid-type]
        name="Next",
        description="Next loop in face",
        min=0,
    )
    
    prev_loop: IntProperty(  # type: ignore[valid-type]
        name="Previous", 
        description="Previous loop in face",
        min=0,
    )
    
    radial_next: IntProperty(  # type: ignore[valid-type]
        name="Radial Next",
        description="Next loop around edge",
        min=0,
    )
    
    radial_prev: IntProperty(  # type: ignore[valid-type]
        name="Radial Previous",
        description="Previous loop around edge", 
        min=0,
    )
    
    # UV coordinates as loop attribute
    uv: FloatVectorProperty(  # type: ignore[valid-type]
        name="UV",
        description="UV coordinates",
        size=2,
    )
    
    if TYPE_CHECKING:
        id: int  # type: ignore[no-redef]
        vertex: int  # type: ignore[no-redef]
        edge: int  # type: ignore[no-redef]
        face: int  # type: ignore[no-redef]
        next_loop: int  # type: ignore[no-redef]
        prev_loop: int  # type: ignore[no-redef]
        radial_next: int  # type: ignore[no-redef]
        radial_prev: int  # type: ignore[no-redef]
        uv: tuple[float, float]  # type: ignore[no-redef]


class BmeshEncodingFacePropertyGroup(PropertyGroup):
    """BMesh face data for EXT_bmesh_encoding."""
    
    id: IntProperty(  # type: ignore[valid-type]
        name="ID",
        description="Unique face identifier",
        min=0,
    )
    
    normal: FloatVectorProperty(  # type: ignore[valid-type]
        name="Normal",
        description="Face normal vector",
        size=3,
        subtype="XYZ",
    )
    
    material_index: IntProperty(  # type: ignore[valid-type]
        name="Material Index",
        description="Material slot index",
        min=0,
    )
    
    # Note: vertices, edges, loops will be stored as indices
    # For now, we'll use simple counters - actual indices stored separately
    vertex_count: IntProperty(  # type: ignore[valid-type]
        name="Vertex Count",
        description="Number of vertices in face",
        min=3,
    )
    
    if TYPE_CHECKING:
        id: int  # type: ignore[no-redef]
        normal: tuple[float, float, float]  # type: ignore[no-redef]
        material_index: int  # type: ignore[no-redef]
        vertex_count: int  # type: ignore[no-redef]


class BmeshEncodingPropertyGroup(PropertyGroup):
    """Main EXT_bmesh_encoding extension data."""
    
    enabled: BoolProperty(  # type: ignore[valid-type]
        name="Enable EXT_bmesh_encoding",
        description="Enable BMesh topology preservation in glTF export",
        default=False,
    )
    
    use_buffer_format: BoolProperty(  # type: ignore[valid-type]
        name="Use Buffer Format",
        description="Use binary buffer format for large meshes instead of JSON",
        default=True,
    )
    
    buffer_threshold: IntProperty(  # type: ignore[valid-type]
        name="Buffer Threshold",
        description="Vertex count threshold for switching to buffer format",
        default=1000,
        min=100,
    )
    
    preserve_manifold_info: BoolProperty(  # type: ignore[valid-type]
        name="Preserve Manifold Info", 
        description="Calculate and preserve manifold status for edges",
        default=True,
    )
    
    vertices: CollectionProperty(  # type: ignore[valid-type]
        name="Vertices",
        type=BmeshEncodingVertexPropertyGroup,
    )
    
    edges: CollectionProperty(  # type: ignore[valid-type]
        name="Edges",
        type=BmeshEncodingEdgePropertyGroup,
    )
    
    loops: CollectionProperty(  # type: ignore[valid-type]
        name="Loops", 
        type=BmeshEncodingLoopPropertyGroup,
    )
    
    faces: CollectionProperty(  # type: ignore[valid-type]
        name="Faces",
        type=BmeshEncodingFacePropertyGroup,
    )
    
    if TYPE_CHECKING:
        enabled: bool  # type: ignore[no-redef]
        use_buffer_format: bool  # type: ignore[no-redef]
        buffer_threshold: int  # type: ignore[no-redef]
        preserve_manifold_info: bool  # type: ignore[no-redef]
        vertices: "CollectionPropertyProtocol[BmeshEncodingVertexPropertyGroup]"  # type: ignore[no-redef]
        edges: "CollectionPropertyProtocol[BmeshEncodingEdgePropertyGroup]"  # type: ignore[no-redef]
        loops: "CollectionPropertyProtocol[BmeshEncodingLoopPropertyGroup]"  # type: ignore[no-redef]
        faces: "CollectionPropertyProtocol[BmeshEncodingFacePropertyGroup]"  # type: ignore[no-redef]
