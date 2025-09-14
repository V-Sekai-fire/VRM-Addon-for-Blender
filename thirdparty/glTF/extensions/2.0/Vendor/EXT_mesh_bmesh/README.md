# EXT_mesh_bmesh

## Contributors

- K. S. Ernest (iFire) Lee, Individual Contributor / https://github.com/fire
- Based on principles from FB_ngon_encoding by Pär Winzell and Michael Bunnell (Facebook)
- Subdivision surface specification contributions by Nick Porcino, Individual Contributor - https://github.com/meshula

## Status

Active Development

## Dependencies

Written against the glTF 2.0 spec, superseding FB_ngon_encoding.

## References

The BMesh data structure is described in:

- Gueorguieva, Stefka, and David Marcheix. "Non-manifold boundary representation for solid modeling." Proc. of the International Computer Symposium. Hsinchu, Taiwan: National Chiao Tung University, 1994.
- BMeshUnity implementation: https://github.com/eliemichel/BMeshUnity.git

## Overview

While glTF can only deliver a polygon mesh after it's been decomposed into triangles, there are cases where access to the full BMesh topology is still useful. BMesh provides a non-manifold boundary representation with vertices, edges, loops, and faces that enables complex geometric operations.

This extension provides **buffer-based BMesh encoding** that stores complete topology information in glTF buffers for optimal performance while maintaining full glTF 2.0 compatibility.

The `EXT_mesh_bmesh` glTF extension solves the problem of topological data loss when models with quads and n-gons are converted to glTF's triangle-only format. It works by embedding the **BMesh** data structure, allowing for reconstruction of the original model.

What makes BMesh so powerful is its ability to represent complex, **non-manifold** geometry. Unlike mesh formats that limit an edge to connecting only two faces, BMesh uses a system of **radial loops** (`radial_next` and `radial_prev` pointers). This is like a book spine that can connect every single page, not just the two covers.

`EXT_mesh_bmesh` allows for the preservation of models where multiple faces meet at a single edge, ensuring the artist's intent is maintained.

### Subdivision Surface Support

Building on the minimal OpenSubdiv requirements, EXT_mesh_bmesh integrates subdivision surface data directly into the BMesh structure using attributes:

- **Edge Creases**: Stored as `CREASE` attribute on edges (f32 sharpness value per edge)
- **Vertex Creases**: Stored as `CREASE` attribute on vertices (f32 sharpness value per vertex)
- **Holes**: Stored as `HOLES` attribute on faces (u8 flag, 1=holes, 0=regular faces)
- **Face Topology**: Complete face connectivity preserved in BMesh structure

This approach follows BMesh philosophy by storing subdivision data as attributes on topological elements, enabling direct compatibility with OpenSubdiv and other subdivision surface implementations while maintaining clean integration with the mesh topology.

### Sparse Accessors for Coarse Attributes

**Sparse accessors** are strongly recommended for compressing coarse mesh attributes in EXT_mesh_bmesh. Sparse accessors work by storing a base set of values for the full attribute array plus sparse overrides specifying only non-default values at specific indices.

## Key Features

### Buffer-Based Storage

- **glTF 2.0 Compliance**: Follows standard glTF buffer view and accessor patterns
- **Standard Attributes**: Uses glTF 2.0 attribute naming conventions (TEXCOORD_0, etc.)
- **Non-manifold Support**: Complete support for non-manifold edges and vertices

## Extension Structure

The EXT_mesh_bmesh extension integrates seamlessly into glTF 2.0 primitives, storing complete BMesh topology in buffer views for optimal performance. Below is the maximal data structure showing all possible features, including OpenSubdiv subdivision surface attributes.

### glTF Example with EXT_mesh_bmesh

```json
{
  "asset": {
    "version": "2.0",
    "generator": "EXT_mesh_bmesh example"
  },
  "scene": 0,
  "scenes": [
    {
      "nodes": [0]
    }
  ],
  "nodes": [
    {
      "mesh": 0
    }
  ],
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
            "EXT_mesh_bmesh": {
              "vertices": {
                "count": 10000,
                "positions": 4,
                "edges": 5,
                "attributes": {
                  "POSITION": 4,
                  "NORMAL": 6,
                  "TANGENT": 7,
                  "COLOR_0": 8,
                  "TEXCOORD_0": 9,
                  "JOINTS_0": 10,
                  "WEIGHTS_0": 11,
                  "CREASE": 12
                }
              },
              "edges": {
                "count": 15000,
                "vertices": 13,
                "faces": 14,
                "attributes": {
                  "CREASE": 16
                }
              },
              "loops": {
                "count": 20000,
                "topology_vertex": 17,
                "topology_edge": 18,
                "topology_face": 19,
                "topology_next": 20,
                "topology_prev": 21,
                "topology_radial_next": 22,
                "topology_radial_prev": 23,
                "attributes": {
                  "TEXCOORD_0": 24,
                  "COLOR_0": 25
                }
              },
              "faces": {
                "count": 5000,
                "vertices": 26,
                "edges": 27,
                "loops": 28,
                "offsets": 29,
                "normals": 30,
                "attributes": {
                  "HOLES": 31
                }
              }
            }
          }
        }
      ]
    }
  ],
  "materials": [
    {
      "name": "DefaultMaterial"
    }
  ],
  "buffers": [...],
  "bufferViews": [...],
  "extensionsUsed": ["EXT_mesh_bmesh"],
  "extensionsRequired": []
}
```

### Key Features in Maximal Structure

**OpenSubdiv Subdivision Surface Integration:**

- **Vertex CREASE**: f32 sharpness values for subdivision creases
- **Edge CREASE**: f32 sharpness values for edge creases
- **Face HOLES**: u8 flags (1=holes, 0=regular faces)

**Complete BMesh Topology:**

- Full topology storage for vertices, edges, loops, faces
- Variable-length arrays with offset indexing for face connectivity
- Non-manifold support via manifold flags and radial navigation

**Standard glTF Attributes:**

- POSITION, NORMAL, TANGENT for vertices
- TEXCOORD_0, COLOR_0 for loops (per-corner attributes)
- JOINTS_0, WEIGHTS_0 for skinning

## Implicit Triangle Fan Algorithm

Building on FB_ngon_encoding principles with BMesh enhancements:

### Core Principle

Like FB_ngon_encoding, the **order of triangles and per-triangle vertex indices** holds all information needed to reconstruct BMesh topology. The algorithm uses an enhanced triangulation process:

- For each BMesh face `f`, choose one identifying vertex `v(f)`
- Break the face into a triangle fan, all anchored at `v(f)`
- **Ensure `v(f) != v(f')` for consecutive faces** (mandatory requirement for unambiguous reconstruction)

### Encoding Process

#### Implicit Layer

1. Anchor Selection: Select distinct anchor vertices for consecutive faces to ensure unambiguous reconstruction
2. Triangle Fan Creation: Generate triangle fans anchored at selected vertices
3. glTF Triangle Output: Output triangles in fan order for implicit reconstruction

### Reconstruction Process

#### Implicit Layer

1. Triangle Grouping: Identify triangle groups by shared anchor vertex
2. Face Reconstruction: Rebuild original faces from triangle fans
3. Topology Derivation: Derive edge and loop relationships from face data
4. Consistency Check: Verify topological integrity of reconstructed mesh

## Buffer Layouts

All BMesh topology data is stored in glTF buffers using efficient binary layouts:

### Vertex Buffers

- **positions**: `Vec3<f32>` (12 bytes per vertex) - 3D coordinates
- **edges**: Variable-length edge lists with offset indexing
- **attributes**: Standard glTF attributes (POSITION, NORMAL, TEXCOORD_0, etc.)

### Edge Buffers

- **vertices**: `[u32, u32]` (8 bytes per edge) - vertex index pairs
- **faces**: Variable-length face lists with offset indexing

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

### Variable-Length Array Encoding

For arrays with variable length (face vertices, edges, loops), data is stored as:

1. **Packed Data Buffer**: Concatenated array elements
2. **Offset Buffer**: Start indices for each element's data
3. **Access Pattern**: `data[offsets[i]:offsets[i+1]]` gives element i's array

## Implementation Requirements

All EXT_mesh_bmesh implementations must support:

1. **Buffer-Based Storage**: All topology data in glTF buffers for performance
2. **glTF 2.0 Compliance**: Standard buffer views, accessors, and attribute naming
3. **Triangle Fan Compatibility**: Maintains FB_ngon_encoding reconstruction principles
4. **Complete Topology**: Full BMesh reconstruction with vertices, edges, loops, faces
5. **Graceful Degradation**: Automatic fallback to triangle fan reconstruction when extension unsupported

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

  const ext = gltfData.extensions.EXT_mesh_bmesh;
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

  for (let i = 0; i < ext.edges.count; i++) {
    const edge = {
      id: i,
      vertices: [edgeVertices[i * 2], edgeVertices[i * 2 + 1]],
      faces: [],
      attributes: {},
    };
    bmesh.edges.set(i, edge);
  }

  // Reconstruct loops from buffer data
  const loopVertex = readBufferView(
    buffers,
    bufferViews,
    ext.loops.topology_vertex
  );
  const loopEdge = readBufferView(
    buffers,
    bufferViews,
    ext.loops.topology_edge
  );
  const loopFace = readBufferView(
    buffers,
    bufferViews,
    ext.loops.topology_face
  );
  const loopNext = readBufferView(
    buffers,
    bufferViews,
    ext.loops.topology_next
  );
  const loopPrev = readBufferView(
    buffers,
    bufferViews,
    ext.loops.topology_prev
  );
  const loopRadialNext = readBufferView(
    buffers,
    bufferViews,
    ext.loops.topology_radial_next
  );
  const loopRadialPrev = readBufferView(
    buffers,
    bufferViews,
    ext.loops.topology_radial_prev
  );

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

- **JSON schema**: [glTF.EXT_mesh_bmesh.schema.json](schema/glTF.EXT_mesh_bmesh.schema.json)

## Known Implementations

- To be determined

## BMesh Data Structures

The following BMesh structures are preserved through buffer-based encoding:

### Vertex

- **Position**: 3D coordinates (x, y, z) stored in `positions` buffer view
- **Connected Edges**: Edge adjacency data in variable-length format
- **Attributes**: Standard glTF attributes (POSITION, NORMAL, TEXCOORD_0, etc.)
- **Subdivision Attributes**: `CREASE` (f32 sharpness for subdivision creases)

### Edge

- **Vertices**: Two vertex references stored as `[u32, u32]` pairs
- **Adjacent Faces**: Variable-length face lists with offset indexing
- **Subdivision Attributes**: `CREASE` (f32 sharpness for subdivision creases)

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
- **Subdivision Attributes**: `HOLES` (u8 flag, 1=holes, 0=regular faces)

### Topological Relationships

- **Vertex-Edge**: One-to-many (vertex connects to multiple edges)
- **Edge-Face**: One-to-many (edge shared by multiple faces, enables non-manifold)
- **Face-Loop**: One-to-many (face has loops for each corner)
- **Loop Navigation**: Circular lists around faces and radially around edges

## Design Decision: No Per-Face Materials

Per-face materials were considered and intentionally excluded from EXT_mesh_bmesh.

EXT_mesh_bmesh focuses purely on **topology preservation** rather than solving the material assignment problem, which is better handled at the glTF primitive and node levels.
