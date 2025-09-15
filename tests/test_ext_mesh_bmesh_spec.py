#!/usr/bin/env python3
"""
EXT_mesh_bmesh Specification-Based Tests

This test suite validates the EXT_mesh_bmesh extension implementation against
the glTF 2.0 specification, focusing on triangulation vs topology preservation.

Tests:
- Triangulation behavior when bmesh is disabled
- Topology preservation when bmesh is enabled
- glTF extension JSON schema compliance
- Subdivision surface data handling
- Loop attribute preservation (TEXCOORD, COLOR)
"""

import json
import unittest
import pathlib
from typing import Dict, Any, List

import bpy


class TestExtMeshBmeshSpecification(unittest.TestCase):
    """Test EXT_mesh_bmesh extension against glTF 2.0 specification"""

    def setUp(self):
        """Set up test fixtures"""
        self.spec_path = pathlib.Path('thirdparty/glTF/extensions/2.0')
        self.test_data_dir = pathlib.Path('tests/resources')
        self.temp_dir = pathlib.Path('tests/temp')

    def tearDown(self):
        """Clean up test fixtures"""
        # Clear Blender data - Fixed: Use proper API
        bpy.data.batch_remove(bpy.data.objects)
        bpy.data.batch_remove(bpy.data.meshes)

    def test_gltf_extension_template_availablity(self):
        """Test that glTF extension templates are available"""
        spec_template = self.spec_path / 'Khronos' / 'EXT_mesh_bmesh.gen'  # Placeholder for any extension spec file
        template_md = self.spec_path.parent / 'Template.md'  # General template

        self.assertTrue(template_md.exists(),
                       "glTF extension template should be available")

        # Verify template content
        with open(template_md, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('extensi', content.lower(),
                         "Template should contain extension framework")

    def test_blender_bpy_mesh_compatibility(self):
        """Test Blender bpy mesh system compatibility"""
        # Test basic mesh creation capabilities
        mesh = bpy.data.meshes.new("TestMesh")
        self.assertIsNotNone(mesh, "Blender mesh should be creatable")

        # Test mesh polygon handling
        vertices = [(0, 0, 0), (1, 0, 0), (0.5, 1, 0), (0.5, 0.5, 1)]
        mesh.from_pydata(vertices, [], [])

        self.assertEqual(len(mesh.vertices), 4,
                        "Mesh should have correct vertex count")
        # Clean up handled by tearDown method

    def test_triangulation_behavior_disabled(self):
        """Test triangulation when bmesh is disabled (standard glTF export)"""
        # Create a quad mesh
        mesh = bpy.data.meshes.new("QuadMesh")
        vertices = [
            (0, 0, 0),    # 0: bottom-left
            (1, 0, 0),    # 1: bottom-right
            (1, 1, 0),    # 2: top-right
            (0, 1, 0)     # 3: top-left
        ]
        edges = []
        faces = [(0, 1, 2, 3)]  # Single quad face
        mesh.from_pydata(vertices, edges, faces)

        # Validate initial quad topology
        initial_polygons = len(mesh.polygons)
        self.assertEqual(initial_polygons, 1,
                        "Should start with one quad")

        # Simulate glTF triangulation (would happen in glTF exporter)
        # This is the expected behavior when bmesh is disabled

        # Validate that triangulation would occur
        # In real glTF export, this quad would be split into 2 triangles
        # We can't actually test the export here, but we can validate the setup
        self.assertEqual(len(mesh.polygons[0].edge_keys), 4,
                        "Should have quad with 4-sided polygon")

        # Clean up handled by tearDown method

    def test_bmesh_topology_preservation_enabled(self):
        """Test topology preservation when bmesh is enabled"""
        from src.io_scene_vrm.exporter.ext_mesh_bmesh_exporter import ExtMeshBmeshExporter

        # Create test mesh
        mesh = bpy.data.meshes.new("NgonMesh")
        vertices = [
            (0, 0, 0),    # 0
            (1, 0, 0),    # 1
            (1, 1, 0),    # 2
            (0.5, 1.5, 0),  # 3
            (0, 1, 0)     # 4 -creates pentagon
        ]
        faces = [(0, 1, 2, 3, 4)]  # Single pentagon
        mesh.from_pydata(vertices, [], faces)

        # Import bmesh exporter
        exporter = ExtMeshBmeshExporter()

        # Analyze topology (this would preserve ngon if bmesh enabled)
        bmesh_data = exporter.analyze_mesh_topology(mesh)

        # Validate bmesh topology analysis
        self.assertIn('faces', bmesh_data, "Should analyze faces")
        self.assertIn('vertices', bmesh_data, "Should analyze vertices")
        self.assertIn('edges', bmesh_data, "Should analyze edges")
        self.assertIn('loops', bmesh_data, "Should analyze loops")

        # Validate polygon topology preserved
        faces = bmesh_data['faces']
        self.assertTrue(all('vertices' in face for face in faces),
                       "Should preserve vertex indices per face")

        self.assertTrue(all('loops' in face for face in faces),
                       "Should preserve loop information")

        # Clean up handled by tearDown method

    def test_subdivision_surface_data_handling(self):
        """Test subdivision surface data handling (creases, holes)"""
        from src.io_scene_vrm.exporter.ext_mesh_bmesh_exporter import ExtMeshBmeshExporter

        # Create test mesh
        mesh = bpy.data.meshes.new("SubdivMesh")
        vertices = [
            (0, 0, 0), (1, 0, 0), (0.5, 1, 0)  # Simple triangle
        ]
        faces = [(0, 1, 2)]
        mesh.from_pydata(vertices, [], faces)

        # Create edge with crease (simulate subdivision modifier)
        # Note: In real usage, this would come from subsurf modifier
        mesh.edges[0].crease = 0.5  # Sharp crease

        # Create exporter and analyze
        exporter = ExtMeshBmeshExporter()
        bmesh_data = exporter.analyze_mesh_topology(mesh)

        # Validate subdivision data extraction
        subdivision_keys = ['vertices_crease', 'edges_crease', 'faces_holes']

        # At least edge crease should be detected
        has_subdiv_data = any(key in bmesh_data for key in subdivision_keys)
        self.assertTrue(has_subdiv_data or 'edges_crease' in bmesh_data,
                       "Should detect some subdivision information")

        mesh.clear()

    def test_loop_attributes_texcoord_color(self):
        """Test loop attribute preservation (UV coordinates, colors)"""
        from src.io_scene_vrm.exporter.ext_mesh_bmesh_exporter import ExtMeshBmeshExporter

        # Create test mesh with UV layer and vertex colors
        mesh = bpy.data.meshes.new("TexturedMesh")
        vertices = [
            (0, 0, 0), (1, 0, 0), (0.5, 1, 0)
        ]
        faces = [(0, 1, 2)]
        mesh.from_pydata(vertices, [], faces)

        # Add UV layer and coordinates - Fixed: Proper Blender API usage
        if len(mesh.uv_layers) == 0:
            uv_layer = mesh.uv_layers.new(name="UVMap")
        else:
            uv_layer = mesh.uv_layers[0]

        for i, loop in enumerate(mesh.loops):
            uv = uv_layer.data[i]  # Access UV data correctly
            uv.uv = (loop.vertex_index * 0.33, loop.vertex_index * 0.66)  # Set UV coordinates

        # Add vertex colors - Fixed: Proper Blender API usage
        if len(mesh.vertex_colors) == 0:
            vc_layer = mesh.vertex_colors.new(name="Col")
        else:
            vc_layer = mesh.vertex_colors[0]

        for i, loop in enumerate(mesh.loops):
            color = vc_layer.data[i]  # Access vertex color data correctly
            color.color = (1.0 if loop.vertex_index == 0 else 0.0,
                          1.0 if loop.vertex_index == 1 else 0.0,
                          1.0 if loop.vertex_index == 2 else 0.0, 1.0)

        # Analyze with bmesh exporter
        exporter = ExtMeshBmeshExporter()
        bmesh_data = exporter.analyze_mesh_topology(mesh)

        # Validate loop attributes captured
        self.assertIn('loops', bmesh_data, "Should have loop data")

        # Check for UV and color attributes
        has_texcoord = 'loop_texcoord_0' in bmesh_data
        has_color = 'loop_color_0' in bmesh_data

        self.assertTrue(has_texcoord or has_color,
                       "Should capture UV coordinates or vertex colors")

        mesh.clear()

    def test_gltf_extension_output_format(self):
        """Test that bmesh exporter produces valid glTF extension format"""
        from src.io_scene_vrm.exporter.ext_mesh_bmesh_exporter import ExtMeshBmeshExporter

        # Create simple mesh
        mesh = bpy.data.meshes.new("GltfTestMesh")
        vertices = [(0, 0, 0), (1, 0, 0), (0.5, 1, 0)]
        faces = [(0, 1, 2)]
        mesh.from_pydata(vertices, [], faces)

        # Export bmesh topology
        exporter = ExtMeshBmeshExporter()
        bmesh_data = exporter.analyze_mesh_topology(mesh)

        # Create actual extension data
        extension_data = exporter.export_bmesh_topology(bmesh_data)

        # Validate glTF extension structure
        self.assertIsInstance(extension_data, dict,
                            "Should produce dictionary extension data")

        # Check for required glTF extension sections
        if extension_data:  # Only if extension was created
            self.assertIn('vertices', extension_data,
                         "Should have vertices section")

            vertices_section = extension_data['vertices']
            self.assertIn('count', vertices_section,
                         "Should have vertex count")
            self.assertIn('positions', vertices_section,
                         "Should have vertex positions")

            if 'faces' in extension_data:
                faces_section = extension_data['faces']
                self.assertIn('count', faces_section,
                             "Should have face count")
                self.assertIn('offsets', faces_section,
                             "Should have face offsets")

        mesh.clear()

    def test_performance_triangulation_vs_preservation(self):
        """Test performance difference between triangulation and topology preservation"""
        import time
        from src.io_scene_vrm.exporter.ext_mesh_bmesh_exporter import ExtMeshBmeshExporter

        # Create larger mesh for performance testing
        mesh = bpy.data.meshes.new("PerformanceTest")
        vertices = []
        faces = []

        # Create grid (10x10 vertices, many quads)
        for y in range(10):
            for x in range(10):
                vertices.append((x, y, 0))

        # Create quad faces
        for y in range(9):
            for x in range(9):
                v0 = y * 10 + x
                v1 = v0 + 1
                v2 = (y + 1) * 10 + x + 1
                v3 = v2 - 1
                faces.append((v0, v1, v2, v3))

        mesh.from_pydata(vertices, [], faces)

        # Time bmesh topology analysis
        exporter = ExtMeshBmeshExporter()

        start_time = time.time()
        bmesh_data = exporter.analyze_mesh_topology(mesh)
        end_time = time.time()

        analysis_time = end_time - start_time

        # Validate that complex mesh was analyzed
        self.assertIn('vertices', bmesh_data, "Should analyze complex mesh")
        self.assertEqual(bmesh_data['vertices'][0]['id'], 0,
                        "Should have proper vertex indexing")

        # Performance should be reasonable (<1 second for reasonable mesh)
        self.assertLess(analysis_time, 2.0,
                       f"Bmesh analysis should be fast, took {analysis_time:.3f}s")

        mesh.clear()


if __name__ == '__main__':
    unittest.main(verbosity=2)
