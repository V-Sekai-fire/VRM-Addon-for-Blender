# EXT_bmesh_encoding

## Contributors

- K. S. Ernest (iFire) Lee, Individual Contributor / https://github.com/fire
- Based on principles from FB_ngon_encoding by Pär Winzell and Michael Bunnell (Facebook)

## Status

Active Development

## Dependencies

Written against the glTF 2.0 spec, superseding FB_ngon_encoding.
Compatible with EXT_mesh_manifold for manifold topology validation.

## References

The BMesh data structure is described in:

- Gueorguieva, Stefka and Marcheix, Davi. 1994. "Non-manifold boundary representation for solid modeling."
- BMeshUnity implementation: https://github.com/eliemichel/BMeshUnity.git

## Overview

While glTF can only deliver a polygon mesh after it's been decomposed into triangles, there are cases where access to the full BMesh topology is still useful. BMesh provides a non-manifold boundary representation with vertices, edges, loops, and faces that enables complex geometric operations.

This extension provides **buffer-based BMesh encoding** that stores complete topology information in glTF buffers for optimal performance while maintaining full glTF 2.0 compatibility.

The `EXT_bmesh_encoding` glTF extension solves the problem of topological data loss when models with quads and n-gons are converted to glTF's triangle-only format. It works by embedding the **BMesh** data structure, allowing for reconstruction of the original model.

What makes BMesh so powerful is its ability to represent complex, **non-manifold** geometry. Unlike mesh formats that limit an edge to connecting only two faces, BMesh uses a system of **radial loops** (`radial_next` and `radial_prev` pointers). This is like a book spine that can connect every single page, not just the two covers.

`EXT_bmesh_encoding` allows for the preservation of models where multiple faces meet at a single edge, ensuring the artist's intent is maintained.

## Key Features

### Buffer-Based Storage

- **High Performance**: All BMesh data stored in binary buffers for optimal memory usage
- **glTF 2.0 Compliance**: Follows standard glTF buffer view and accessor patterns
- **Scalable**: Efficient for meshes of any size
- **Standard Attributes**: Uses glTF 2.0 attribute naming conventions (TEXCOORD_0, etc.)
- **Non-manifold Support**: Complete support for non-manifold edges and vertices

## Extension Structure

glTF buffer format (all data stored in buffer views):

```json
{
  "meshes": [
    {
      "name": "BMeshModel",
      "primitives": [
        {
          "indices": 0,
          "attributes": {
            "POSITION": 1,
            "NORMAL": 2,
            "TEXCOORD_0": 3
          },
          "material": 0,
          "mode": 4,
          "extensions": {
            "EXT_bmesh_encoding": {
              "vertices": {
                "count": 10000,
                "positions": 10,
                "edges": 11
              },
              "edges": {
                "count": 15000,
                "vertices": 13,
                "faces": 14,
                "manifold": 15
              },
              "loops": {
                "count": 20000,
                "topology": 16,
                "attributes": {
                  "TEXCOORD_0": 17
                }
              },
              "faces": {
                "count": 5000,
                "vertices": 18,
                "edges": 19,
                "loops": 20,
                "offsets": 21,
                "normals": 22
              }
            }
          }
        }
      ]
    }
  ]
}
```

## Implicit Triangle Fan Algorithm

Building on FB_ngon_encoding principles with BMesh enhancements:

### Core Principle

Like FB_ngon_encoding, the **order of triangles and per-triangle vertex indices** holds all information needed to reconstruct BMesh topology. The algorithm uses an enhanced triangulation process:

- For each BMesh face `f`, choose one identifying vertex `v(f)`
- Break the face into a triangle fan, all anchored at `v(f)`
- **Ensure `v(f) != v(f')` for consecutive faces** (mandatory requirement for unambiguous reconstruction)
- Use enhanced vertex selection for optimal BMesh reconstruction

### Encoding Process (Implicit Layer)

1. **BMesh Face Analysis**: Analyze BMesh faces for optimal triangulation
2. **Enhanced Anchor Selection**: Choose anchor vertex to minimize reconstruction ambiguity
3. **Triangle Fan Generation**: Create triangle fans with optimal vertex ordering
4. **Standard glTF Output**: Produce standard glTF triangles following triangle fan pattern

### Buffer-Based Encoding Process (SOA)

1. **BMesh Analysis**: Extract vertices, edges, loops, and faces from BMesh
2. **SOA Buffer Creation**: Create 7 separate topology buffers for loops
3. **Variable-Length Encoding**: Encode face vertex/edge/loop arrays with offsets
4. **Buffer View Assignment**: Assign all data to glTF buffer views

### Reconstruction Process

1. **Triangle Grouping**: Group consecutive triangles sharing the same `triangle.vertices[0]`
2. **BMesh Face Rebuilding**: Reconstruct BMesh faces from triangle fans
3. **Topology Inference**: Infer BMesh edge and loop structure from face connectivity
4. **Validation**: Validate reconstructed BMesh for topological consistency

### Buffer-Based Reconstruction Process (SOA)

1. **Buffer Reading**: Read SOA topology buffers from glTF buffer views
2. **BMesh Construction**: Reconstruct vertices, edges, loops, faces from buffers
3. **Topology Linking**: Restore all navigation pointers and relationships
4. **Attribute Assignment**: Apply stored attributes to all topology elements

## Buffer Layouts

All BMesh topology data is stored in glTF buffers using efficient binary layouts:

### Vertex Buffers

- **positions**: `Vec3<f32>` (12 bytes per vertex) - 3D coordinates
- **edges**: Variable-length edge lists with offset indexing
- **attributes**: Standard glTF attributes (POSITION, NORMAL, TEXCOORD_0, etc.)

### Edge Buffers

- **vertices**: `[u32, u32]` (8 bytes per edge) - vertex index pairs
- **faces**: Variable-length face lists with offset indexing
- **manifold**: `u8` (1 byte per edge) - manifold status flag
  - `0`: Confirmed non-manifold
  - `1`: Confirmed manifold
  - `255`: Unknown status
- **attributes**: Custom edge data with `_` prefix naming

### Loop Buffers

- **topology_vertex**: `u32` (4 bytes per loop) - vertex indices
- **topology_edge**: `u32` (4 bytes per loop) - edge indices
- **topology_face**: `u32` (4 bytes per loop) - face indices
- **topology_next**: `u32` (4 bytes per loop) - next loop indices
- **topology_prev**: `u32` (4 bytes per loop) - prev loop indices
- **topology_radial_next**: `u32` (4 bytes per loop) - radial_next loop indices
- **topology_radial_prev**: `u32` (4 bytes per loop) - radial_prev loop indices
- **attributes**: glTF 2.0 compliant attributes (TEXCOORD_0, COLOR_0, etc.)

### Face Buffers

- **vertices**: Variable-length vertex index lists
- **edges**: Variable-length edge index lists
- **loops**: Variable-length loop index lists
- **offsets**: `[u32; 3]` (12 bytes per face) - start offsets for vertices, edges, loops arrays
- **normals**: `Vec3<f32>` (12 bytes per face) - face normal vectors
- **attributes**: Custom face data with `_` prefix naming

### Variable-Length Array Encoding

For arrays with variable length (face vertices, edges, loops), data is stored as:

1. **Packed Data Buffer**: Concatenated array elements
2. **Offset Buffer**: Start indices for each element's data
3. **Access Pattern**: `data[offsets[i]:offsets[i+1]]` gives element i's array

## Implementation Requirements

All EXT_bmesh_encoding implementations must support:

1. **Buffer-Based Storage**: All topology data in glTF buffers for performance
2. **glTF 2.0 Compliance**: Standard buffer views, accessors, and attribute naming
3. **Triangle Fan Compatibility**: Maintains FB_ngon_encoding reconstruction principles
4. **Complete Topology**: Full BMesh reconstruction with vertices, edges, loops, faces
5. **Graceful Degradation**: Automatic fallback to triangle fan reconstruction when extension unsupported

### Implementation Guidance

**Simple Writers** (minimal implementation):

- Use `manifold: 255` for all edges (no manifold checking required)
- Store basic BMesh topology without complex validation
- Focus on core buffer encoding functionality

**Advanced Writers** (full implementation):

- Perform manifold checking and set appropriate manifold values (0, 1, 255)
- Validate topology during encoding
- Optimize buffer layouts for specific use cases

**Readers** (all implementations):

- Handle all three manifold states gracefully
- Provide fallback behavior for unknown manifold status
- Support reconstruction from either implicit triangles or explicit buffers

## Advantages over FB_ngon_encoding

1. **Complete Topology**: Full BMesh structure with edges and loops, not just faces
2. **Performance Optimized**: Binary buffer storage instead of JSON arrays
3. **Non-manifold Support**: Explicit handling of non-manifold geometry
4. **Attribute Rich**: Comprehensive attribute support at all topology levels
5. **glTF 2.0 Native**: Follows glTF buffer patterns and naming conventions
6. **Backward Compatible**: Falls back gracefully to triangle fan reconstruction

## Algorithm Details

### Enhanced Triangle Fan Encoding

```javascript
// Implicit encoding - maintains triangle fan pattern for compatibility
function encodeBmeshImplicit(bmeshFaces) {
  const triangles = [];
  let prevAnchor = -1;

  for (const face of bmeshFaces) {
    const vertices = face.vertices;
    // MANDATORY: Select anchor different from previous face
    const candidates = vertices.filter((v) => v !== prevAnchor);
    const anchor =
      candidates.length > 0 ? Math.min(...candidates) : vertices[0];

    // This MUST be different from prevAnchor for correct reconstruction
    if (anchor === prevAnchor && vertices.length > 1) {
      throw new Error(
        "Cannot ensure v(f) != v(f') - algorithm requirement violated"
      );
    }

    prevAnchor = anchor;

    const n = vertices.length;
    const anchorIdx = vertices.indexOf(anchor);

    // Create triangle fan from anchor
    for (let i = 2; i < n; i++) {
      const v1Idx = (anchorIdx + i - 1) % n;
      const v2Idx = (anchorIdx + i) % n;
      const triangle = [anchor, vertices[v1Idx], vertices[v2Idx]];
      triangles.push(triangle);
    }
  }

  return triangles;
}

// The encoding is the function inverse of decodeBmeshFromBuffers.

// Buffer-based BMesh reconstruction
function decodeBmeshFromBuffers(gltfData) {
  const bmesh = {
    vertices: new Map(),
    edges: new Map(),
    loops: new Map(),
    faces: new Map(),
  };

  const ext = gltfData.extensions.EXT_bmesh_encoding;
  const buffers = gltfData.buffers;
  const bufferViews = gltfData.bufferViews;

  // Reconstruct vertices from buffer data
  const vertexPositions = readBufferView(
    buffers,
    bufferViews,
    ext.vertices.positions
  );
  for (let i = 0; i < ext.vertices.count; i++) {
    bmesh.vertices.set(i, {
      id: i,
      position: [
        vertexPositions[i * 3],
        vertexPositions[i * 3 + 1],
        vertexPositions[i * 3 + 2],
      ],
      edges: [],
      attributes: {},
    });
  }

  // Reconstruct edges from buffer data
  const edgeVertices = readBufferView(buffers, bufferViews, ext.edges.vertices);
  const manifoldFlags = readBufferView(
    buffers,
    bufferViews,
    ext.edges.manifold
  );

  for (let i = 0; i < ext.edges.count; i++) {
    const edge = {
      id: i,
      vertices: [edgeVertices[i * 2], edgeVertices[i * 2 + 1]],
      faces: [],
      manifold:
        manifoldFlags[i] === 1 ? true : manifoldFlags[i] === 0 ? false : null,
      attributes: {},
    };
    bmesh.edges.set(i, edge);
  }

  // Reconstruct loops from SOA buffer data
  const loopVertex = readBufferView(buffers, bufferViews, ext.loops.topology_vertex);
  const loopEdge = readBufferView(buffers, bufferViews, ext.loops.topology_edge);
  const loopFace = readBufferView(buffers, bufferViews, ext.loops.topology_face);
  const loopNext = readBufferView(buffers, bufferViews, ext.loops.topology_next);
  const loopPrev = readBufferView(buffers, bufferViews, ext.loops.topology_prev);
  const loopRadialNext = readBufferView(buffers, bufferViews, ext.loops.topology_radial_next);
  const loopRadialPrev = readBufferView(buffers, bufferViews, ext.loops.topology_radial_prev);

  for (let i = 0; i < ext.loops.count; i++) {
    bmesh.loops.set(i, {
      id: i,
      vertex: loopVertex[i],
      edge: loopEdge[i],
      face: loopFace[i],
      next: loopNext[i],
      prev: loopPrev[i],
      radial_next: loopRadialNext[i],
      radial_prev: loopRadialPrev[i],
      attributes: {},
    });
  }

  // Reconstruct faces from buffer data
  const faceVertices = readBufferView(buffers, bufferViews, ext.faces.vertices);
  const faceOffsets = readBufferView(buffers, bufferViews, ext.faces.offsets);
  const faceNormals = readBufferView(buffers, bufferViews, ext.faces.normals);

  for (let i = 0; i < ext.faces.count; i++) {
    const vertexStart = faceOffsets[i * 3];
    const vertexEnd = faceOffsets[i * 3 + 1];

    const face = {
      id: i,
      vertices: faceVertices.slice(vertexStart, vertexEnd),
      edges: [],
      loops: [],
      normal: [
        faceNormals[i * 3],
        faceNormals[i * 3 + 1],
        faceNormals[i * 3 + 2],
      ],
      attributes: {},
    };
    bmesh.faces.set(i, face);
  }

  return bmesh;
}

function readBufferView(buffers, bufferViews, bufferViewIndex) {
  const bufferView = bufferViews[bufferViewIndex];
  const buffer = buffers[bufferView.buffer];
  return new Uint32Array(
    buffer,
    bufferView.byteOffset,
    bufferView.byteLength / 4
  );
}
```

## glTF Schema

- **JSON schema**: [glTF.EXT_bmesh_encoding.schema.json](schema/glTF.EXT_bmesh_encoding.schema.json)

## Known Implementations

- Aria BMesh Domain (Elixir) - In Development
- VRM Add-on for Blender (Python) - Active Development

## BMesh Data Structures

The following BMesh structures are preserved through buffer-based encoding:

### Vertex

- **Position**: 3D coordinates (x, y, z) stored in `positions` buffer view
- **Connected Edges**: Edge adjacency data in variable-length format
- **Attributes**: Standard glTF attributes (POSITION, NORMAL, TEXCOORD_0, etc.)

### Edge

- **Vertices**: Two vertex references stored as `[u32, u32]` pairs
- **Adjacent Faces**: Variable-length face lists with offset indexing
- **Manifold Status**: Single byte flag compatible with EXT_mesh_manifold
  - `0`: Confirmed non-manifold
  - `1`: Confirmed manifold (oriented 2-manifold)
  - `255`: Unknown status (no manifold checking performed)
- **Attributes**: Custom edge data with `_` prefix naming

### Loop

- **Vertex**: Corner vertex reference
- **Edge**: Outgoing edge from vertex
- **Face**: Containing face reference
- **Navigation**: Next/previous loop in face, radial next/previous around edge
- **Topology**: All navigation stored as 7×u32 array per loop
- **Attributes**: Per-corner data using glTF naming (TEXCOORD_0, COLOR_0, etc.)

### Face

- **Vertices**: Variable-length vertex index lists with offset indexing
- **Edges**: Variable-length edge index lists with offset indexing
- **Loops**: Variable-length loop index lists with offset indexing
- **Normal**: Face normal vector stored as Vec3<f32>
- **Attributes**: Custom face data with `_` prefix naming

### Topological Relationships

- **Vertex-Edge**: One-to-many (vertex connects to multiple edges)
- **Edge-Face**: One-to-many (edge shared by multiple faces, enables non-manifold)
- **Face-Loop**: One-to-many (face has loops for each corner)
- **Loop Navigation**: Circular lists around faces and radially around edges

## Design Decision: No Per-Face Materials

Per-face materials were considered and intentionally excluded from EXT_bmesh_encoding.

BMesh natively supports per-face material assignment. Some 3D modeling workflows assign materials at the face level. Would enable perfect round-trip preservation of BMesh material data

glTF is fundamentally built around primitive-per-material for rendering efficiency.

Per-face materials would require massive primitive explosion or complex material switching.

Modern graphics APIs expect material grouping for optimal performance.

Per-face materials interfere with clean triangle fan reconstruction.

Material boundaries would complicate optimal anchor vertex selection.

Adds significant complexity to both encoding and decoding logic.

Multi-material objects can be split into single-material meshes during export.

Aligns with established glTF workflows and tool expectations.

Prioritizes rendering efficiency over edge case flexibility.

During Export separate multi-material BMesh into single-material submeshes.

EXT_bmesh_encoding focuses purely on **topology preservation** rather than solving the material assignment problem, which is better handled at the glTF primitive and node levels.
