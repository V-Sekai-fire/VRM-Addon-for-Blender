# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
import bpy
from typing import Dict, Any, Optional

from .abstract_base_vrm_exporter import AbstractBaseVrmExporter
from .ext_mesh_bmesh_exporter import ExtMeshBmeshExporter


class glTF2ExportUserExtension:
    def __init__(self) -> None:
        context = bpy.context

        self.object_name_to_modifier_names = (
            AbstractBaseVrmExporter.enter_hide_mtoon1_outline_geometry_nodes(context)
        )

        # Initialize EXT_mesh_bmesh exporter
        self.bmesh_exporter = ExtMeshBmeshExporter()

    # EXT_mesh_bmesh extension methods
    def gather_mesh_hook(self, gltf2_mesh: Dict[str, Any], blender_mesh: bpy.types.Mesh,
                        blender_object: bpy.types.Object) -> None:
        """Gather EXT_mesh_bmesh data from mesh"""
        # Update exporter with current glTF data
        self.bmesh_exporter.gltf_data = gltf2_mesh.gltf_data
        self.bmesh_exporter.buffers = gltf2_mesh.buffers
        self.bmesh_exporter.buffer_views = gltf2_mesh.buffer_views
        self.bmesh_exporter.accessors = gltf2_mesh.accessors

        # Export BMesh topology
        extension_data = self.bmesh_exporter.export_mesh(blender_mesh, blender_mesh.name)

        if extension_data:
            # Add extension to mesh
            extensions = gltf2_mesh.get('extensions', {})
            extensions['EXT_mesh_bmesh'] = extension_data
            gltf2_mesh['extensions'] = extensions

            # Mark extension as used in document root
            if hasattr(gltf2_mesh, 'gltf_data') and hasattr(gltf2_mesh.gltf_data, 'extensionsUsed'):
                if 'EXT_mesh_bmesh' not in gltf2_mesh.gltf_data.extensionsUsed:
                    gltf2_mesh.gltf_data.extensionsUsed.append('EXT_mesh_bmesh')

    def gather_gltf_extensions_hook(self, gltf_plan: Dict[str, Any], export_settings) -> Optional[Dict[str, Any]]:
        """Declare the EXT_mesh_bmesh extension"""
        return {
            'EXT_mesh_bmesh': {
                'required': False,  # Extension is optional
                'properties': {
                    'vertices': {},
                    'edges': {},
                    'loops': {},
                    'faces': {}
                }
            }
        }

    def gather_primitive_hook(self, gltf2_primitive: Dict[str, Any], blender_primitive, blender_mesh, blender_object) -> None:
        """Add EXT_mesh_bmesh to primitive if available"""
        # Check if mesh already has EXT_mesh_bmesh extension
        extensions = gltf2_primitive.get('extensions', {})
        if 'EXT_mesh_bmesh' in extensions:
            # Validate the extension data structure
            ext_data = extensions['EXT_mesh_bmesh']
            required_sections = ['vertices', 'edges', 'loops', 'faces']
            for section in required_sections:
                if section not in ext_data:
                    print(f"Warning: EXT_mesh_bmesh missing required section: {section}")

    # Original hook methods
    def gather_gltf_hook(
        self,
        # The number of arguments and specifications vary widely from version to version
        # of the glTF 2.0 add-on.
        _arg1: object,
        _arg2: object,
        _arg3: object = None,
        _arg4: object = None,
    ) -> None:
        context = bpy.context

        AbstractBaseVrmExporter.exit_hide_mtoon1_outline_geometry_nodes(
            context, self.object_name_to_modifier_names
        )
        self.object_name_to_modifier_names.clear()
