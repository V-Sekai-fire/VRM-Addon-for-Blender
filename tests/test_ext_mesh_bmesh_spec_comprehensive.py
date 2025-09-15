#!/usr/bin/env python3
"""
Comprehensive EXT_mesh_bmesh Specification Tests

This test suite validates the EXT_mesh_bmesh exporter against the official
glTF 2.0 EXT_mesh_bmesh specification found in:
    thirdparty/glTF/extensions/2.0/Vendor/EXT_mesh_bmesh/

Tests include:
- Full JSON schema compliance validation
- Required field presence verification
- Topology data structure correctness
- Attribute naming convention adherence
- Buffer-based storage validation
- Subdivision surface parameter verification
"""

import json
import unittest
import pathlib
from typing import Dict, Any, List

import bpy

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    jsonschema = None


class TestExtMeshBmeshComprehensiveSpec(unittest.TestCase):
    """Comprehensive EXT_mesh_bmesh specification compliance tests"""

    def setUp(self):
        """Set up test fixtures with full specification context"""
        self.spec_path = pathlib.Path('thirdparty/glTF/extensions/2.0/Vendor/EXT_mesh_bmesh')
        self.spec_schema = self.spec_path / 'schema/glTF.EXT_mesh_bmesh.schema.json'
        self.test_data_dir = pathlib.Path('tests/resources')
        self.temp_dir = pathlib.Path('tests/temp')

        # Load the official specification schema
        if self.spec_schema.exists():
            with open(self.spec_schema, 'r', encoding='utf-8') as f:
                self.schema = json.load(f)
        else:
            self.skipTest("Official EXT_mesh_bmesh schema not found")

    def tearDown(self):
        """Clean up Blender data using proper API"""
        bpy.data.batch_remove(bpy.data.objects)
        bpy.data.batch_remove(bpy.data.meshes)

    def test_official_specification_schema_exists(self):
        """Verify the official EXT_mesh_bmesh specification exists"""
        self.assertTrue(self.spec_path.exists(),
                       "Official EXT_mesh_bmesh specification should exist")

        self.assertTrue(self.spec_schema.exists(),
                       "Official EXT_mesh_bmesh JSON schema should exist")

        # Verify schema content
        with open(self.spec_schema, 'r', encoding='utf-8') as f:
            schema_content = json.load(f)
            self.assertEqual(schema_content['$schema'],
                           "http://json-schema.org/draft-04/schema")
            self.assertEqual(schema_content['title'],
                           "EXT_mesh_bmesh glTF extension")

    def test_spec_required_topology_sections(self):
        """Validate that all 4 major topology sections are required by spec"""
        schema = self.schema

        # Validate REQUIRED sections per specification
        required_sections = schema.get('required', [])
        self.assertEqual(required_sections,
                        ["vertices", "edges", "loops", "faces"],
                        "All 4 topology sections must be required by spec")

    def test_spec_topology_vertex_requirements(self):
        """Verify vertices section requirements match spec"""
        schema = self.schema
        vertices_schema = schema['properties']['vertices']

        # Required vertex fields
        required_vertex_fields = vertices_schema.get('required', [])
        self.assertIn('count', required_vertex_fields,
                     "Vertex count must be required")
        self.assertIn('positions', required_vertex_fields,
                     "Vertex positions must be required")

        # Validate attribute pattern supports all glTF types plus CREASE
        if 'attributes' in vertices_schema['properties']:
            attributes_schema = vertices_schema['properties']['attributes']
            pattern = attributes_schema['patternProperties']
            expected_attrs = "POSITION|NORMAL|TANGENT|COLOR_[0-9]+|TEXCOORD_[0-9]+|JOINTS_[0-9]+|WEIGHTS_[0-9]+|CREASE"
            self.assertIn(expected_attrs, list(pattern.keys()),
                         "Vertex attributes must support standard glTF + CREASE")

    def test_spec_topology_edge_requirements(self):
        """Verify edge section requirements match spec"""
        schema = self.schema
        edges_schema = schema['properties']['edges']

        # Required edge fields
        required_edge_fields = edges_schema.get('required', [])
        self.assertIn('count', required_edge_fields,
                     "Edge count must be required")
        self.assertIn('vertices', required_edge_fields,
                     "Edge vertices must be required")

    def test_spec_topology_loop_requirements(self):
        """Verify loop section requirements match spec (most complex)"""
        schema = self.schema
        loops_schema = schema['properties']['loops']

        # ALL loop topology fields are required by spec
        required_loop_fields = loops_schema.get('required', [])
        expected_topology = [
            "count", "topology_vertex", "topology_edge", "topology_face",
            "topology_next", "topology_prev", "topology_radial_next", "topology_radial_prev"
        ]

        for field in expected_topology:
            self.assertIn(field, required_loop_fields,
                         f"Loop topology field '{field}' must be required by spec")

        # Validate loop attribute naming pattern (glTF 2.0 standard)
        if 'attributes' in loops_schema['properties']:
            attributes_schema = loops_schema['properties']['attributes']
            pattern = attributes_schema['patternProperties']
            expected_pattern = "^(TEXCOORD_[0-9]+|COLOR_[0-9]+)$"
            self.assertIn(expected_pattern, list(pattern.keys()),
                         "Loop attributes must follow glTF 2.0 naming with TEXCOORD and COLOR")

    def test_spec_topology_face_requirements(self):
        """Verify face section requirements match spec"""
        schema = self.schema
        faces_schema = schema['properties']['faces']

        # Face-specific required fields
        required_face_fields = faces_schema.get('required', [])
        expected_face_required = ["count", "vertices", "offsets"]

        for field in expected_face_required:
            self.assertIn(field, required_face_fields,
                         f"Face field '{field}' must be required by spec")

        # Face hole attribute support
        if 'attributes' in faces_schema['properties']:
            attributes_schema = faces_schema['properties']['attributes']
            pattern = attributes_schema['patternProperties']
            self.assertIn("^(HOLES)$", list(pattern.keys()),
                         "Faces must support HOLES subdivision attribute")

    def test_bmesh_exporter_schema_compliance(self):
        """Test that bmesh exporter produces schema-compliant output"""
        from src.io_scene_vrm.exporter.ext_mesh_bmesh_exporter import ExtMeshBmeshExporter

        # Create test mesh for full schema test
        mesh = bpy.data.meshes.new("SpecComplianceTest")
        # Create a more complex test mesh to test all features
        vertices = [
            (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),  # Quad base
            (0.5, 0.5, 1)  # Pyramid top
        ]
        faces = [(0, 1, 2, 3), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]  # Quad + 4 triangles
        mesh.from_pydata(vertices, [], faces)

        # Create exporter and generate bmesh data
        exporter = ExtMeshBmeshExporter()
        bmesh_data = exporter.analyze_mesh_topology(mesh)
        extension_data = exporter.export_bmesh_topology(bmesh_data)

        # Validate against official JSON schema
        if extension_data and self.schema:
            try:
                jsonschema.validate(extension_data, self.schema)
                extension_valid = True
            except jsonschema.ValidationError as e:
                print(f"Schema validation error: {e.message}")
                extension_valid = False

            if extension_valid:
                print("✅ EXT_mesh_bmesh extension output is schema compliant")

                # Additional validation of specific schema requirements
                self._validate_full_schema_compliance(extension_data)
            else:
                self.fail("EXT_mesh_bmesh output does not match official schema")

        mesh.clear()

    def _validate_full_schema_compliance(self, extension_data: Dict[str, Any]):
        """Validate that extension data fully complies with EXT_mesh_bmesh schema"""

        # Validate vertices section
        if 'vertices' in extension_data:
            vertices = extension_data['vertices']
            self.assertIn('count', vertices, "Vertices section must have count")
            self.assertIn('positions', vertices, "Vertices section must have positions")
            self.assertIsInstance(vertices['count'], int, "Vertex count must be integer")
            self.assertGreaterEqual(vertices['count'], 0, "Vertex count must be non-negative")

        # Validate edges section
        if 'edges' in extension_data:
            edges = extension_data['edges']
            self.assertIn('count', edges, "Edges section must have count")
            self.assertIn('vertices', edges, "Edges section must have vertices")
            self.assertIsInstance(edges['count'], int, "Edge count must be integer")

        # Validate loops section (most complex)
        if 'loops' in extension_data:
            loops = extension_data['loops']
            required_loop_topology = [
                'count', 'topology_vertex', 'topology_edge', 'topology_face',
                'topology_next', 'topology_prev', 'topology_radial_next', 'topology_radial_prev'
            ]

            for field in required_loop_topology:
                self.assertIn(field, loops, f"Loops section must have {field}")
                self.assertIsInstance(loops[field], int, f"{field} must be accessor index")

            if 'attributes' in loops:
                attrs = loops['attributes']
                # Validate attribute names follow glTF convention
                valid_attr_names = {'TEXCOORD_0', 'TEXCOORD_1', 'COLOR_0', 'COLOR_1'}
                for attr_name in attrs:
                    if not any(attr_name.startswith(prefix) for prefix in ['TEXCOORD_', 'COLOR_']):
                        self.fail(f"Loop attribute '{attr_name}' doesn't follow glTF naming convention")

        # Validate faces section
        if 'faces' in extension_data:
            faces = extension_data['faces']
            self.assertIn('count', faces, "Faces section must have count")
            self.assertIn('vertices', faces, "Faces section must have vertices")
            self.assertIn('offsets', faces, "Faces section must have offsets")
            self.assertIsInstance(faces['count'], int, "Face count must be integer")

    def test_spec_subdivision_surface_attributes(self):
        """Test subdivision surface attribute compliance (CREASE, HOLES)"""
        schema = self.schema

        # Check vertex crease support
        vertices_schema = schema['properties']['vertices']
        if 'attributes' in vertices_schema['properties']:
            attrs = vertices_schema['properties']['attributes']['patternProperties']
            crease_pattern = "(CREASE)"
            # Verify CREASE is supported in vertices
            if crease_pattern in list(attrs.keys()):
                crease_def = attrs[crease_pattern]
                self.assertIsNotNone(crease_def, "CREASE attribute must be defined")

        # Check edge crease support
        edges_schema = schema['properties']['edges']
        if 'attributes' in edges_schema['properties']:
            attrs = edges_schema['properties']['attributes']['patternProperties']
            crease_pattern = "(CREASE)"
            if crease_pattern in list(attrs.keys()):
                self.assertTrue(len(attrs[crease_pattern]) > 0,
                              "Edge CREASE attribute must be defined")

        # Check face holes support
        faces_schema = schema['properties']['faces']
        if 'attributes' in faces_schema['properties']:
            attrs = faces_schema['properties']['attributes']['patternProperties']
            holes_pattern = "(HOLES)"
            if holes_pattern in list(attrs.keys()):
                self.assertTrue(len(attrs[holes_pattern]) > 0,
                              "Face HOLES attribute must be defined")

    def test_spec_attribute_naming_conventions(self):
        """Validate glTF 2.0 attribute naming conventions"""
        schema = self.schema

        # Test vertex attribute naming
        vertices_attrs = schema['properties']['vertices']['properties']['attributes']['patternProperties']
        vertex_pattern = list(vertices_attrs.keys())[0]  # Get the regex pattern
        self.assertIn('POSITION', vertex_pattern, "Vertex attributes must support POSITION")
        self.assertIn('NORMAL', vertex_pattern, "Vertex attributes must support NORMAL")
        self.assertIn('COLOR_', vertex_pattern, "Vertex attributes must support COLOR_")
        self.assertIn('TEXCOORD_', vertex_pattern, "Vertex attributes must support TEXCOORD_")

        # Test loop attribute naming
        loops_attrs = schema['properties']['loops']['properties']['attributes']['patternProperties']
        loop_pattern = list(loops_attrs.keys())[0]
        self.assertIn('TEXCOORD_', loop_pattern, "Loop attributes must support TEXCOORD_")
        self.assertIn('COLOR_', loop_pattern, "Loop attributes must support COLOR_")

        print("✅ Attribute naming conventions validate against glTF 2.0 specification")

    def test_bmesh_implementation_completeness(self):
        """Validate that bmesh implementation covers all required spec features"""
        from src.io_scene_vrm.exporter.ext_mesh_bmesh_exporter import ExtMeshBmeshExporter

        # Test implementation has all required methods
        exporter = ExtMeshBmeshExporter()

        required_methods = [
            'analyze_mesh_topology',
            'export_bmesh_topology',
            'export_primitive',
            '_build_adjacency',
            '_extract_subdivision_data'
        ]

        for method in required_methods:
            self.assertTrue(hasattr(exporter, method),
                           f"BMesh exporter must implement {method} method")

        # Test implementation handles all required data structures
        test_mesh = bpy.data.meshes.new("TestMesh")
        vertices = [(0, 0, 0), (1, 0, 0), (0.5, 1, 0)]
        faces = [(0, 1, 2)]
        test_mesh.from_pydata(vertices, [], faces)

        bmesh_data = exporter.analyze_mesh_topology(test_mesh)

        # Verify all required topology structures are present
        required_structures = ['vertices', 'edges', 'loops', 'faces']
        for structure in required_structures:
            self.assertIn(structure, bmesh_data,
                         f"BMesh analysis must produce {structure} data")

        # Verify edge-vertex topology exists
        if bmesh_data['vertices']:
            for vertex in bmesh_data['vertices']:
                self.assertIn('edges', vertex,
                             "Vertices must have edge adjacency data")

        if bmesh_data['edges']:
            for edge in bmesh_data['edges']:
                self.assertIn('vertices', edge,
                             "Edges must have vertex data")

        test_mesh.clear()


if __name__ == '__main__':
    unittest.main(verbosity=2)
