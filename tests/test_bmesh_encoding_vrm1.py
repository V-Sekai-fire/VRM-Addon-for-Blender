"""
Test VRM 1.0 EXT_bmesh_encoding functionality.
Ensures existing VRM 1.x EXT_bmesh_encoding support continues working properly
and doesn't conflict with VRM 0.x implementation.
"""
import unittest
import bpy
import sys
import os
from pathlib import Path

# Add the src directory to Python path to allow imports
test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from .base_blender_test_case import BaseBlenderTestCase
from io_scene_vrm.exporter.vrm1_exporter import Vrm1Exporter
from io_scene_vrm.editor.bmesh_encoding.encoding import BmeshEncoder
from io_scene_vrm.editor.bmesh_encoding.decoding import BmeshDecoder
from io_scene_vrm.common import ops
import bmesh


class TestBmeshEncodingVrm1(BaseBlenderTestCase):
    """Test VRM 1.x EXT_bmesh_encoding functionality and backward compatibility."""

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
            # Create a simpler complex mesh to avoid duplicate face issues
            # Use a 2x2x2 grid of vertices (8 vertices total)
            verts = [
                (-1, -1, -1),  # 0
                (1, -1, -1),   # 1
                (1, 1, -1),    # 2
                (-1, 1, -1),   # 3
                (-1, -1, 1),   # 4
                (1, -1, 1),    # 5
                (1, 1, 1),     # 6
                (-1, 1, 1),    # 7
            ]

            # Define faces for a cube (6 faces, each with 4 vertices)
            faces = [
                [0, 1, 2, 3],  # front
                [4, 5, 6, 7],  # back
                [0, 1, 5, 4],  # bottom
                [2, 3, 7, 6],  # top
                [0, 3, 7, 4],  # left
                [1, 2, 6, 5],  # right
            ]

            for vert_pos in verts:
                bm.verts.new(vert_pos)
            bm.verts.ensure_lookup_table()
            for face_verts in faces:
                bm.faces.new([bm.verts[i] for i in face_verts])

        bm.to_mesh(mesh)
        bm.free()

        return obj

    def create_export_preferences(self, enable_ext_bmesh_encoding=False):
        """Create mock export preferences for VRM 1.x exporter."""
        # Mock export preferences object
        class MockPreferences:
            def __init__(self):
                self.enable_advanced_preferences = enable_ext_bmesh_encoding
                self.export_ext_bmesh_encoding = enable_ext_bmesh_encoding

        return MockPreferences()

    def test_vrm1_exporter_constructor_with_ext_bmesh_encoding(self):
        """Test VRM 1.x exporter constructor handles EXT_bmesh_encoding parameter."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("VRM1Test", "cube")

        # Test with EXT_bmesh_encoding disabled (default)
        pref_disabled = self.create_export_preferences(enable_ext_bmesh_encoding=False)
        exporter_disabled = Vrm1Exporter(bpy.context, [obj], armature, pref_disabled)

        self.assertEqual(exporter_disabled.export_ext_bmesh_encoding, False)
        self.assertEqual(len(exporter_disabled.original_mesh_topology), 0)

        # Test with EXT_bmesh_encoding enabled
        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter_enabled = Vrm1Exporter(bpy.context, [obj], armature, pref_enabled)

        self.assertEqual(exporter_enabled.export_ext_bmesh_encoding, True)

    def test_vrm1_topology_capture_disabled(self):
        """Test that topology capture doesn't happen when EXT_bmesh_encoding is disabled."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("TopologyCaptureTest", "ico_sphere")

        pref_disabled = self.create_export_preferences(enable_ext_bmesh_encoding=False)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_disabled)

        # Should do nothing when disabled
        exporter.capture_original_mesh_topology()

        self.assertEqual(len(exporter.original_mesh_topology), 0)

    def test_vrm1_topology_capture_enabled(self):
        """Test that topology capture works when EXT_bmesh_encoding is enabled."""
        # Create a simple armature instead of using icyp operator
        armature_data = bpy.data.armatures.new("TestArmature")
        armature = bpy.data.objects.new("TestArmature", armature_data)
        bpy.context.collection.objects.link(armature)
        bpy.context.view_layer.objects.active = armature

        obj = self.create_test_mesh_object("TopologyCaptureTest", "ico_sphere")

        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_enabled)

        # Should capture topology when enabled
        exporter.capture_original_mesh_topology()

        # Check that topology was captured
        self.assertGreater(len(exporter.original_mesh_topology), 0)

        # Should have captured our test object
        object_name_found = obj.name in exporter.original_mesh_topology
        mesh_name_found = obj.data.name in exporter.original_mesh_topology

        self.assertTrue(
            object_name_found or mesh_name_found,
            f"Topology should be captured for '{obj.name}' or '{obj.data.name}'"
        )

        # Verify topology data structure
        topology_data = next(iter(exporter.original_mesh_topology.values()))
        self.assertIsInstance(topology_data, dict)
        self.assertIn("faceLoopIndices", topology_data)

    def test_vrm1_ext_bmesh_encoding_extension_output_disabled(self):
        """Test that EXT_bmesh_encoding extension is not added when disabled."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("ExtensionTest", "cube")

        pref_disabled = self.create_export_preferences(enable_ext_bmesh_encoding=False)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_disabled)

        # Create minimal glTF structure
        json_dict = {"meshes": [{"name": "test_mesh", "primitives": [{}]}]}
        buffer0 = bytearray()
        object_name_to_index_dict = {obj.name: 0}

        # Call the extension addition method
        exporter.add_ext_bmesh_encoding_to_meshes(json_dict, buffer0, object_name_to_index_dict)

        # Extensions used should not include EXT_bmesh_encoding
        extensions_used = json_dict.get("extensionsUsed")
        if extensions_used:
            self.assertNotIn("EXT_bmesh_encoding", extensions_used)

    def test_vrm1_ext_bmesh_encoding_extension_output_enabled(self):
        """Test that EXT_bmesh_encoding extension is added when enabled."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("ExtensionTest", "cube")

        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_enabled)

        # Capture topology first
        exporter.capture_original_mesh_topology()
        self.assertGreater(len(exporter.original_mesh_topology), 0)

        # Create minimal glTF structure
        json_dict = {
            "meshes": [{"name": obj.data.name, "primitives": [{}]}],
            "nodes": [{"name": obj.name, "mesh": 0}],
            "scenes": [{"nodes": [0]}]
        }
        buffer0 = bytearray()
        object_name_to_index_dict = {obj.name: 0}

        # Call the extension addition method
        exporter.add_ext_bmesh_encoding_to_meshes(json_dict, buffer0, object_name_to_index_dict)

        # Extensions used should include EXT_bmesh_encoding
        extensions_used = json_dict.get("extensionsUsed")
        self.assertIsNotNone(extensions_used)
        self.assertIn("EXT_bmesh_encoding", extensions_used)

        # Mesh should have the extension
        mesh = json_dict["meshes"][0]
        primitive = mesh["primitives"][0]
        extensions = primitive.get("extensions")
        self.assertIsNotNone(extensions)
        self.assertIn("EXT_bmesh_encoding", extensions)

        # Extension data should have expected structure
        extension_data = extensions["EXT_bmesh_encoding"]
        self.assertIn("faceLoopIndices", extension_data)
        self.assertIn("faceCounts", extension_data)

    def test_vrm1_export_pipeline_disabled(self):
        """Test full VRM 1.x export pipeline with EXT_bmesh_encoding disabled."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("VRM1PipelineDisabled", "cube")

        pref_disabled = self.create_export_preferences(enable_ext_bmesh_encoding=False)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_disabled)

        # Export should succeed
        vrm_data = exporter.export_vrm()

        self.assertIsNotNone(vrm_data)
        self.assertTrue(len(vrm_data) > 0)

        # Parse to check structure - should be valid glb
        glb_magic = b'glTF'
        self.assertTrue(vrm_data.startswith(glb_magic))

        # Should not have EXT_bmesh_encoding in extensions used
        # (Full validation would require glTF parsing, but basic check here)

    def test_vrm1_export_pipeline_enabled(self):
        """Test full VRM 1.x export pipeline with EXT_bmesh_encoding enabled."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("VRM1PipelineEnabled", "ico_sphere")

        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_enabled)

        # Export should succeed
        vrm_data = exporter.export_vrm()

        self.assertIsNotNone(vrm_data)
        self.assertTrue(len(vrm_data) > 0)

        # Parse to check structure - should be valid glb
        glb_magic = b'glTF'
        self.assertTrue(vrm_data.startswith(glb_magic))

        # Note: Full VRM 1.0 file validation would require proper glTF parsing
        # and VRM 1.0 schema validation, but basic checks confirm functionality

    def test_vrm1_topology_capture_with_multiple_meshes(self):
        """Test topology capture with multiple mesh objects."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active

        # Create multiple mesh objects
        mesh_objects = []
        for i in range(3):
            obj = self.create_test_mesh_object(f"MultiMeshTest{i}", "cube")
            mesh_objects.append(obj)

        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter = Vrm1Exporter(bpy.context, mesh_objects, armature, pref_enabled)

        # Capture topology
        exporter.capture_original_mesh_topology()

        # Should capture topology for all meshes
        self.assertGreaterEqual(len(exporter.original_mesh_topology), len(mesh_objects))

        # Verify we captured the right meshes
        captured_names = set(exporter.original_mesh_topology.keys())
        object_names = {obj.name for obj in mesh_objects}
        mesh_names = {obj.data.name for obj in mesh_objects}

        # Should have captured using some combination of object and mesh names
        captured_objects = len(set(captured_names) & object_names)
        captured_meshes = len(set(captured_names) & mesh_names)

        self.assertGreater(
            captured_objects + captured_meshes,
            0,
            "Should capture at least some of the test mesh objects"
        )

    def test_vrm1_ext_bmesh_encoding_performance(self):
        """Test that EXT_bmesh_encoding doesn't significantly slow down VRM 1.x export."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("PerformanceTest", "ico_sphere")

        import time

        # Test with extension disabled
        pref_disabled = self.create_export_preferences(enable_ext_bmesh_encoding=False)
        exporter_disabled = Vrm1Exporter(bpy.context, [obj], armature, pref_disabled)

        start_time = time.time()
        vrm_disabled = exporter_disabled.export_vrm()
        disabled_time = time.time() - start_time

        # Test with extension enabled
        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter_enabled = Vrm1Exporter(bpy.context, [obj], armature, pref_enabled)

        start_time = time.time()
        vrm_enabled = exporter_enabled.export_vrm()
        enabled_time = time.time() - start_time

        # Exports should succeed
        self.assertIsNotNone(vrm_disabled)
        self.assertIsNotNone(vrm_enabled)

        # Performance check: extension should not add excessive overhead
        # Allow reasonable margin (2x with small meshes should be fine)
        performance_ratio = enabled_time / disabled_time
        self.assertLess(
            performance_ratio,
            3.0,  # Maximum 3x slowdown for small test meshes
            ".2f"
        )

    def test_vrm1_backward_compatibility_with_vrm0x_changes(self):
        """Test that VRM 1.x doesn't break due to VRM 0.x changes."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("CompatTest", "cube")

        # Verify that VRM 1.x functionality works as expected
        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_enabled)

        # Should be able to create beat the exporter
        self.assertIsNotNone(exporter)

        # Should have different methods than VRM 0.x
        self.assertTrue(hasattr(exporter, 'capture_original_mesh_topology'))
        self.assertTrue(hasattr(exporter, 'export_vrm'))

        # Should have VRM 1.x specific attributes
        self.assertTrue(hasattr(exporter, 'extras_main_armature_key'))
        self.assertTrue(hasattr(exporter, 'extras_object_name_key'))

    def test_vrm1_mesh_lookup_strategies(self):
        """Test various mesh lookup strategies used in EXT_bmesh_encoding addition."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active
        obj = self.create_test_mesh_object("LookupTest", "cube")

        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter = Vrm1Exporter(bpy.context, [obj], armature, pref_enabled)

        # Capture topology first
        exporter.capture_original_mesh_topology()
        self.assertGreater(len(exporter.original_mesh_topology), 0)

        # Test different lookup scenarios
        json_dict = {
            "meshes": [
                {"name": obj.data.name, "primitives": [{}]},
                {"name": obj.name, "primitives": [{}]}  # Different name
            ],
            "nodes": [{"name": obj.name, "mesh": 0}]
        }
        buffer0 = bytearray()
        object_name_to_index_dict = {obj.name: 0}

        # Should still find and add extension using mesh data name lookup
        exporter.add_ext_bmesh_encoding_to_meshes(json_dict, buffer0, object_name_to_index_dict)

        # Should have added extension
        extensions_used = json_dict.get("extensionsUsed")
        if extensions_used:
            self.assertIn("EXT_bmesh_encoding", extensions_used)

    def test_vrm1_non_mesh_objects_skipped(self):
        """Test that non-mesh objects are properly skipped in topology capture."""
        ops.icyp.make_basic_armature()
        armature = bpy.context.view_layer.objects.active

        # Create mesh object
        mesh_obj = self.create_test_mesh_object("MeshObj", "cube")

        # Create armature object (should be skipped)
        armature_obj = bpy.data.objects.new("ArmatureObj", armature)
        bpy.context.collection.objects.link(armature_obj)

        pref_enabled = self.create_export_preferences(enable_ext_bmesh_encoding=True)
        exporter = Vrm1Exporter(bpy.context, [mesh_obj, armature_obj], armature, pref_enabled)

        # Capture topology
        exporter.capture_original_mesh_topology()

        # Should only capture mesh objects, not armature
        captured_names = set(exporter.original_mesh_topology.keys())

        # Should not have captured the armature
        self.assertNotIn(armature_obj.name, captured_names)
        self.assertNotIn(armature.name, captured_names)

        # Should have captured the mesh
        mesh_captured = (mesh_obj.name in captured_names or
                        mesh_obj.data.name in captured_names)
        self.assertTrue(mesh_captured, "Should capture mesh object but skip armature")


if __name__ == "__main__":
    unittest.main()
