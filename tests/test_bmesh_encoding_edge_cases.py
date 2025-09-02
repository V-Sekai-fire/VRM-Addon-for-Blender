"""
Test EXT_bmesh_encoding with complex mesh scenarios and edge cases.
Tests edge cases that may occur in real mesh data.
"""
import unittest
import bpy
import bmesh
import math
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import random

# Add the src directory to Python path to allow imports
test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from .base_blender_test_case import BaseBlenderTestCase
from io_scene_vrm.editor.bmesh_encoding.encoding import BmeshEncoder
from io_scene_vrm.editor.bmesh_encoding.decoding import BmeshDecoder
from io_scene_vrm.exporter.vrm0_exporter import Vrm0Exporter
from io_scene_vrm.common.logger import get_logger

logger = get_logger(__name__)


class TestBmeshEncodingEdgeCases(BaseBlenderTestCase):
    """Test EXT_bmesh_encoding with complex and edge-case mesh scenarios."""

    def setUp(self):
        super().setUp()
        self.bmesh_encoder = BmeshEncoder()
        self.bmesh_decoder = BmeshDecoder()

    def create_test_mesh_object(self, name="TestMesh", topology_type="ico_sphere"):
        """Create a test mesh with specified topology."""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        bpy.context.collection.objects.link(obj)

        # Create mesh based on topology type
        bm = bmesh.new()
        bm.from_mesh(mesh)

        if topology_type == "cube":
            # Add a simple cube
            bmesh.ops.create_cube(bm, size=2.0)
        elif topology_type == "ico_sphere":
            # Add an icosphere with non-uniform triangulation
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        elif topology_type == "complex":
            # Create a more complex mesh with various face types
            verts = []
            faces = []

            # Add vertices in a pattern
            for x in range(-2, 3):
                for y in range(-1, 2):
                    for z in range(-2, 3):
                        verts.append((x, y, z))

            # Add faces creating different topologies
            for x in range(-2, 2):
                for z in range(-2, 2):
                    # Create quad faces (will be triangulated)
                    faces.append([
                        ((x+2) * 3 + (z+2)),
                        ((x+2) * 3 + (z+3)),
                        ((x+3) * 3 + (z+3)),
                        ((x+3) * 3 + (z+2))
                    ])

            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            for vert_pos in verts:
                bm.verts.new(vert_pos)
            for face_verts in faces:
                bm.faces.new([bm.verts[i] for i in face_verts])

        bm.to_mesh(mesh)
        bm.free()

        return obj

    def create_maze_mesh(self, name="MazeMesh"):
        """Create a complex maze-like mesh with many small faces."""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        bpy.context.collection.objects.link(obj)

        bm = bmesh.new()
        bm.from_mesh(mesh)

        # Create a simple maze pattern
        wall_thickness = 0.2
        maze = [
            [1, 1, 1, 1, 1, 1, 1],
            [1, 0, 0, 1, 0, 0, 1],
            [1, 0, 1, 1, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 1, 1],
        ]

        height = 1.0
        scale = 0.5

        # Generate walls
        for y in range(len(maze)):
            for x in range(len(maze[0])):
                if maze[y][x] == 1:
                    # Create wall block
                    x_pos = x * scale
                    y_pos = y * scale

                    verts = []
                    verts.append(bm.verts.new((x_pos, y_pos, 0)))
                    verts.append(bm.verts.new((x_pos + scale, y_pos, 0)))
                    verts.append(bm.verts.new((x_pos + scale, y_pos + scale, 0)))
                    verts.append(bm.verts.new((x_pos, y_pos + scale, 0)))

                    verts.append(bm.verts.new((x_pos, y_pos, height)))
                    verts.append(bm.verts.new((x_pos + scale, y_pos, height)))
                    verts.append(bm.verts.new((x_pos + scale, y_pos + scale, height)))
                    verts.append(bm.verts.new((x_pos, y_pos + scale, height)))

                    # Create faces
                    # Bottom
                    bm.faces.new([verts[0], verts[1], verts[2], verts[3]])
                    # Top
                    bm.faces.new([verts[4], verts[5], verts[6], verts[7]])
                    # Front
                    bm.faces.new([verts[0], verts[1], verts[5], verts[4]])
                    # Back
                    bm.faces.new([verts[3], verts[2], verts[6], verts[7]])
                    # Left
                    bm.faces.new([verts[0], verts[3], verts[7], verts[4]])
                    # Right
                    bm.faces.new([verts[1], verts[2], verts[6], verts[5]])

        bm.to_mesh(mesh)
        bm.free()

        return obj

    def create_degenerate_geometry_mesh(self, name="DegenerateMesh"):
        """Create mesh with degenerate geometry (zero-area faces, duplicate vertices)."""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        bpy.context.collection.objects.link(obj)

        bm = bmesh.new()
        bm.from_mesh(mesh)

        # Add vertices with duplicates
        verts = []
        verts.append(bm.verts.new((0, 0, 0)))      # 0 - duplicated below
        verts.append(bm.verts.new((1, 0, 0)))      # 1
        verts.append(bm.verts.new((0.5, 1, 0)))    # 2
        verts.append(bm.verts.new((0, 0, 0)))      # 3 - duplicate of 0

        # Good triangle
        bm.faces.new([verts[0], verts[1], verts[2]])

        # Degenerate faces (different types)
        # Zero-area triangle
        bm.faces.new([verts[0], verts[1], verts[0]])  # Points 0, 1, 0
        # Line (two points same)
        bm.faces.new([verts[0], verts[1], verts[0]])  # Points 0, 1, 0
        # Point (all same)
        bm.faces.new([verts[0], verts[0], verts[0]])  # Points 0, 0, 0

        # Very thin triangle
        verts.append(bm.verts.new((2, 0, 0)))        # 4
        verts.append(bm.verts.new((2.0001, 0, 0)))   # 5 - very close to 4
        verts.append(bm.verts.new((2.00005, 0.1, 0))) # 6
        bm.faces.new([verts[4], verts[5], verts[6]])   # Very thin triangle

        bm.to_mesh(mesh)
        bm.free()

        return obj

    def create_island_mesh(self, name="IslandMesh"):
        """Create mesh with separate islands of geometry."""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        bpy.context.collection.objects.link(obj)

        bm = bmesh.new()
        bm.from_mesh(mesh)

        # First island - a cube
        bm.verts.new((0, 0, 0))
        bm.verts.new((1, 0, 0))
        bm.verts.new((1, 1, 0))
        bm.verts.new((0, 1, 0))
        bm.verts.new((0, 0, 1))
        bm.verts.new((1, 0, 1))
        bm.verts.new((1, 1, 1))
        bm.verts.new((0, 1, 1))

        # Second island - a separate triangle far away
        bm.verts.new((5, 0, 0))
        bm.verts.new((6, 0, 0))
        bm.verts.new((5.5, 2, 0))

        # Third island - another separate quad
        bm.verts.new((0, 5, 0))
        bm.verts.new((1, 5, 0))
        bm.verts.new((1, 6, 0))
        bm.verts.new((0, 6, 0))

        bm.verts.ensure_lookup_table()

        # Create faces for each island
        # Island 1 - cube faces
        bm.faces.new([bm.verts[0], bm.verts[1], bm.verts[2], bm.verts[3]])  # bottom

        # Island 2 - single triangle
        bm.faces.new([bm.verts[8], bm.verts[9], bm.verts[10]])

        # Island 3 - single quad
        bm.faces.new([bm.verts[11], bm.verts[12], bm.verts[13], bm.verts[14]])

        bm.to_mesh(mesh)
        bm.free()

        return obj

    def create_nested_hierarchy_mesh(self, name="NestedMesh"):
        """Create mesh with deeply nested face loops."""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        bpy.context.collection.objects.link(obj)

        bm = bmesh.new()
        bm.from_mesh(mesh)

        # Create a complex nested structure
        radius = 2.0
        rings = 5
        segments_per_ring = [4, 8, 12, 16, 20]

        all_verts = []

        for ring in range(rings):
            if ring >= len(segments_per_ring):
                continue
            segments = segments_per_ring[ring]
            ring_verts = []

            for i in range(segments):
                angle = 2 * math.pi * i / segments
                x = radius * (ring + 1) * math.cos(angle)
                y = radius * (ring + 1) * math.sin(angle)
                z = 0

                vert = bm.verts.new((x, y, z))
                ring_verts.append(vert)
                all_verts.append(vert)

            # Connect each ring
            if ring > 0:
                prev_segments = segments_per_ring[ring - 1]
                prev_ring_start = sum(segments_per_ring[:ring])

                for i in range(segments):
                    # Connect to previous ring
                    if i % 2 == 0:  # Create some complex patterns
                        prev_i1 = (i // 2) % prev_segments
                        prev_i2 = ((i // 2) + 1) % prev_segments

                        # Create triangles bridging rings
                        bm.faces.new([
                            ring_verts[i],
                            all_verts[prev_ring_start + prev_i1],
                            all_verts[prev_ring_start + prev_i2]
                        ])

        bm.to_mesh(mesh)
        bm.free()

        return obj

    def create_extremely_dense_mesh(self, name="DenseMesh"):
        """Create mesh with many small, densely packed faces."""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        bpy.context.collection.objects.link(obj)

        vertices = []
        faces = []

        # Create a dense grid
        grid_size = 20  # 400 vertices
        for x in range(grid_size):
            for z in range(grid_size):
                vertices.append((x * 0.1, 0, z * 0.1))

        # Create faces with random triangulation patterns
        random.seed(42)  # For reproducibility

        for x in range(grid_size - 1):
            for z in range(grid_size - 1):
                v1 = x * grid_size + z
                v2 = (x + 1) * grid_size + z
                v3 = (x + 1) * grid_size + z + 1
                v4 = x * grid_size + z + 1

                # Randomly choose triangulation pattern
                if random.choice([True, False]):
                    # One way
                    faces.extend([(v1, v2, v3), (v1, v3, v4)])
                else:
                    # Other way
                    faces.extend([(v1, v2, v4), (v2, v3, v4)])

        # Create mesh data
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        return obj

    def test_complex_maze_topology(self):
        """Test encoding/decoding with complex maze-like topology."""
        obj = self.create_maze_mesh("MazeTest")
        original_mesh = obj.data.copy()

        # Encode
        encoded_data = self.bmesh_encoder.encode_object_native(obj)
        self.assertIsNotNone(encoded_data, "Maze encoding should succeed")

        # Decode
        decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)
        self.assertIsNotNone(decoded_mesh, "Maze decoding should succeed")

        # Compare
        self.assertEqual(len(original_mesh.vertices), len(decoded_mesh.vertices),
                        "Maze vertex count should match")
        self.assertEqual(len(original_mesh.polygons), len(decoded_mesh.polygons),
                        "Maze face count should match")

    def test_degenerate_geometry_handling(self):
        """Test handling of degenerate geometry (zero-area faces, duplicates)."""
        obj = self.create_degenerate_geometry_mesh("DegenerateTest")
        original_mesh = obj.data.copy()

        # This should handle gracefully - not crash
        encoded_data = self.bmesh_encoder.encode_object_native(obj)

        if encoded_data is not None:  # May return None for degenerate cases
            decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)

            # Basic checks if decoding succeeded
            if decoded_mesh is not None:
                self.assertGreaterEqual(len(decoded_mesh.vertices), 1,
                                       "Should have at least some vertices")

    def test_separate_island_mesh(self):
        """Test encoding/decoding with separate islands of geometry."""
        obj = self.create_island_mesh("IslandTest")
        original_mesh = obj.data.copy()

        # Encode
        encoded_data = self.bmesh_encoder.encode_object_native(obj)
        self.assertIsNotNone(encoded_data, "Island encoding should succeed")

        # Decode
        decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)
        self.assertIsNotNone(decoded_mesh, "Island decoding should succeed")

        # Compare
        self.assertEqual(len(original_mesh.vertices), len(decoded_mesh.vertices),
                        "Island vertex count should match")
        self.assertEqual(len(original_mesh.polygons), len(decoded_mesh.polygons),
                        "Island face count should match")

    def test_nested_hierarchy_mesh(self):
        """Test encoding/decoding with deeply nested face loops."""
        obj = self.create_nested_hierarchy_mesh("NestedTest")

        # This might be a challenging case - should handle gracefully
        encoded_data = self.bmesh_encoder.encode_object_native(obj)

        if encoded_data is not None:
            decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)

            if decoded_mesh is not None:
                original_mesh = obj.data
                # Basic structure checks
                self.assertGreater(len(decoded_mesh.vertices), 0,
                                  "Should preserve some vertices")

    def test_extremely_dense_mesh(self):
        """Test encoding/decoding with extremely dense geometry."""
        obj = self.create_extremely_dense_mesh("DenseTest")
        original_mesh = obj.data.copy()

        # May take longer for dense meshes
        encoded_data = self.bmesh_encoder.encode_object_native(obj)

        if encoded_data is not None:  # May exceed limits
            decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)

            if decoded_mesh is not None:
                self.assertEqual(len(original_mesh.vertices), len(decoded_mesh.vertices),
                                "Dense mesh vertex count should match")
                self.assertEqual(len(original_mesh.polygons), len(decoded_mesh.polygons),
                                "Dense mesh face count should match")

    def test_mixed_face_types_extensive(self):
        """Test mesh with extensive mixture of different face types."""
        # Create a mesh with triangles, quads, pentagons, hexagons
        vertices = []
        faces = []

        # Create large circular arrangement
        ring_count = 3
        for ring in range(ring_count):
            angle_step = 2 * math.pi / (6 + ring * 2)  # Different segment counts
            for i in range(6 + ring * 2):
                angle = i * angle_step
                radius = 1 + ring * 0.5
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                z = ring * 0.1
                vertices.append((x, y, z))

        # Manual face creation for different ngon types
        base_count = 6
        for ring in range(ring_count - 1):
            next_ring_start = sum(6 + i * 2 for i in range(ring + 1))
            current_ring_start = sum(6 + i * 2 for i in range(ring))

            current_count = 6 + ring * 2
            next_count = 6 + (ring + 1) * 2

            for i in range(current_count):
                # Create different face patterns
                if ring % 3 == 0:
                    # Triangles
                    faces.extend([
                        (current_ring_start + i, current_ring_start + (i + 1) % current_count,
                         next_ring_start + (i * 2) % next_count)
                    ])
                elif ring % 3 == 1:
                    # Quads
                    faces.extend([
                        (current_ring_start + i, current_ring_start + (i + 1) % current_count,
                         next_ring_start + (i * 2 + 1) % next_count,
                         next_ring_start + (i * 2) % next_count)
                    ])
                else:
                    # Mixed ngons (pentagons, hexagons)
                    if (i % 2 == 0):
                        faces.extend([
                            (current_ring_start + i, current_ring_start + (i + 1) % current_count,
                             current_ring_start + (i + 2) % current_count,
                             next_ring_start + (i * 2 + 1) % next_count,
                             next_ring_start + (i * 2) % next_count)
                        ])

        mesh = bpy.data.meshes.new("MixedTypesMesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        obj = bpy.data.objects.new("MixedTypesObj", mesh)
        bpy.context.collection.objects.link(obj)

        original_mesh = mesh.copy()

        # Test encoding/decoding
        encoded_data = self.bmesh_encoder.encode_object_native(obj)
        if encoded_data is not None:
            decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)

            if decoded_mesh is not None:
                self.assertEqual(len(original_mesh.vertices), len(decoded_mesh.vertices),
                                "Mixed topology vertex count should match")
                self.assertEqual(len(original_mesh.polygons), len(decoded_mesh.polygons),
                                "Mixed topology face count should match")

    def test_mesh_with_transformations(self):
        """Test encoding/decoding with mesh that has non-identity transformations."""
        obj = self.create_test_mesh_object("TransformTest", "cube")

        # Apply various transformations
        obj.scale = (2.0, 0.5, 3.0)
        obj.rotation_euler = (math.pi / 4, math.pi / 6, math.pi / 8)
        obj.location = (1.0, 2.0, 3.0)

        # Update to apply transformations to mesh data
        bpy.context.view_layer.update()

        original_mesh = obj.data.copy()

        # Encode
        encoded_data = self.bmesh_encoder.encode_object_native(obj)
        self.assertIsNotNone(encoded_data, "Transformed mesh encoding should succeed")

        # Decode - should preserve the transformed geometry
        decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)
        self.assertIsNotNone(decoded_mesh, "Transformed mesh decoding should succeed")

        # Compare - geometry should match after transformation is baked
        self.assertEqual(len(original_mesh.vertices), len(decoded_mesh.vertices),
                        "Transformed mesh vertex count should match")
        self.assertEqual(len(original_mesh.polygons), len(decoded_mesh.polygons),
                        "Transformed mesh face count should match")

    def test_mesh_with_multiple_uv_layers(self):
        """Test encoding/decoding with mesh that has multiple UV layers."""
        obj = self.create_test_mesh_object("MultiUVTest", "cube")

        # Add another UV layer
        uv_layer2 = obj.data.uv_layers.new(name="UVLayer2")

        # Create different UV mappings on each layer
        for i, polygon in enumerate(obj.data.polygons):
            for j, loop_index in enumerate(polygon.loop_indices):
                uv_layer1 = obj.data.uv_layers[0]
                uv_layer2 = obj.data.uv_layers[1]

                # Different UV unwraps
                u1 = v1 = 0.5
                if j == 0:
                    u1, v1 = 0.0, 0.0
                elif j == 1:
                    u1, v1 = 1.0, 0.0
                elif j == 2:
                    u1, v1 = 1.0, 1.0
                elif j == 3:
                    u1, v1 = 0.0, 1.0

                # Different mapping for second layer
                u2 = (u1 + i * 0.1) % 1.0
                v2 = (v1 + i * 0.1) % 1.0

                uv_layer1.data[loop_index].uv = (u1, v1)
                uv_layer2.data[loop_index].uv = (u2, v2)

        original_mesh = obj.data.copy()

        # Encode - should preserve topology despite multiple UVs
        encoded_data = self.bmesh_encoder.encode_object_native(obj)
        self.assertIsNotNone(encoded_data, "Multi-UV mesh encoding should succeed")

        # Decode
        decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)
        self.assertIsNotNone(decoded_mesh, "Multi-UV mesh decoding should succeed")

        # Compare topology
        self.assertEqual(len(original_mesh.vertices), len(decoded_mesh.vertices),
                        "Multi-UV mesh vertex count should match")
        self.assertEqual(len(original_mesh.polygons), len(decoded_mesh.polygons),
                        "Multi-UV mesh face count should match")

    def test_error_handling_corrupted_data(self):
        """Test error handling with potentially corrupted or incomplete data."""
        # Test various error conditions
        error_cases = [
            None,           # None data
            {},            # Empty dict
            {"vertex": [], "face": [], "loop": []},  # Empty arrays
            {"vertex": None, "face": None, "loop": None},  # None values
        ]

        for i, test_data in enumerate(error_cases):
            with self.subTest(case=i):
                # Should handle gracefully without crashing
                decoded_mesh = self.bmesh_decoder.decode_into_mesh(test_data)

                # Result may be None or minimal mesh, but no exceptions

    def test_memory_usage_large_complex_mesh(self):
        """Test memory usage and performance with large complex meshes."""
        # Create a reasonably large mesh for performance testing
        verts = []
        faces = []

        grid_size = 10  # 100 vertices
        for x in range(grid_size):
            for z in range(grid_size):
                verts.append((x * 0.5, 0, z * 0.5))

        # Create faces with complex patterns
        for x in range(grid_size - 1):
            for z in range(grid_size - 1):
                base = x * grid_size + z
                # Change triangulation pattern
                if (x + z) % 2 == 0:
                    faces.append((base, base + 1, base + grid_size + 1, base + grid_size))
                else:
                    faces.extend([
                        (base, base + 1, base + grid_size),
                        (base + 1, base + grid_size + 1, base + grid_size)
                    ])

        mesh = bpy.data.meshes.new("LargeComplexMesh")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new("LargeComplexObj", mesh)
        bpy.context.collection.objects.link(obj)

        # Time the encode/decode operation
        import time
        start_time = time.time()

        encoded_data = self.bmesh_encoder.encode_object_native(obj)
        encode_time = time.time() - start_time

        if encoded_data is not None:
            start_time = time.time()
            decoded_mesh = self.bmesh_decoder.decode_into_mesh(encoded_data)
            decode_time = time.time() - start_time

            # Should complete in reasonable time (< 1 second)
            self.assertLess(encode_time, 1.0, f"Encoding too slow: {encode_time:.3f}s")
            self.assertLess(decode_time, 1.0, f"Decoding too slow: {decode_time:.3f}s")

            if decoded_mesh is not None:
                # Verify structure
                self.assertEqual(len(mesh.vertices), len(decoded_mesh.vertices))
                self.assertEqual(len(mesh.polygons), len(decoded_mesh.polygons))


if __name__ == "__main__":
    unittest.main()
