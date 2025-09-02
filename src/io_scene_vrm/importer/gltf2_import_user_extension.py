# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
import secrets
import string
from typing import Optional

from bpy.types import Image, Armature

from ..common.convert import sequence_or_none
from ..common.logger import get_logger
from ..editor.bmesh_encoding.decoding import BmeshDecoder

logger = get_logger(__name__)


class glTF2ImportUserExtension:
    current_import_id: Optional[str] = None
    # Store EXT_bmesh_encoding data safely during import
    _bmesh_encoding_data: dict[str, dict] = {}

    @classmethod
    def update_current_import_id(cls) -> str:
        import_id = "BlenderVrmAddonImport" + (
            "".join(secrets.choice(string.digits) for _ in range(10))
        )
        cls.current_import_id = import_id
        cls._bmesh_encoding_data.clear()  # Clear previous data
        return import_id

    @classmethod
    def clear_current_import_id(cls) -> None:
        cls.current_import_id = None
        cls._bmesh_encoding_data.clear()

    @classmethod
    def get_stored_bmesh_encoding_data(cls, armature_name: str) -> Optional[dict]:
        """Get stored EXT_bmesh_encoding data for an armature."""
        return cls._bmesh_encoding_data.get(armature_name)

    # https://github.com/KhronosGroup/glTF-Blender-IO/blob/6f9d0d9fc1bb30e2b0bb019342ffe86bd67358fc/addons/io_scene_gltf2/blender/imp/gltf2_blender_image.py#L51
    def gather_import_image_after_hook(
        self, image: object, bpy_image: object, gltf_importer: object
    ) -> None:
        if self.current_import_id is None:
            return

        if not isinstance(bpy_image, Image):
            logger.warning(
                "gather_import_image_after_hook: bpy_image is not a Image but %s",
                type(bpy_image),
            )
            return

        images = sequence_or_none(
            getattr(getattr(gltf_importer, "data", None), "images", None)
        )
        if images is None:
            logger.warning(
                "gather_import_image_after_hook:"
                " gltf_importer is unexpected structure: %s",
                gltf_importer,
            )
            return

        if image not in images:
            logger.warning(
                "gather_import_image_after_hook: %s not in %s", image, images
            )
            return

        index = images.index(image)

        bpy_image[self.current_import_id] = index

    def gather_import_armature_bone_after_hook(
        self, gltf_node: object, blender_object: object, blender_bone: object, gltf_importer: object
    ) -> None:
        """Hook to intercept and safely store EXT_bmesh_encoding data from armature extensions."""
        try:
            if not hasattr(blender_object, 'data') or not isinstance(blender_object.data, Armature):
                return
                
            # Check if the armature has extension data that would cause the property error
            armature_data = blender_object.data
            
            # Look for any extension data in the armature's custom properties
            vrm_extension_data = None
            if hasattr(armature_data, 'get'):
                vrm_extension_data = armature_data.get('vrm_addon_extension')
            
            if vrm_extension_data and isinstance(vrm_extension_data, dict):
                bmesh_encoding_data = vrm_extension_data.get('bmesh_encoding')
                if bmesh_encoding_data:
                    logger.info(f"Intercepting EXT_bmesh_encoding data for armature: {armature_data.name}")
                    
                    # Store the data safely using our class storage
                    self._bmesh_encoding_data[armature_data.name] = bmesh_encoding_data
                    
                    # Remove the problematic data from the original location to prevent the error
                    if 'bmesh_encoding' in vrm_extension_data:
                        del vrm_extension_data['bmesh_encoding']
                        logger.info(f"Safely stored and removed bmesh_encoding data from armature {armature_data.name}")
                        
        except Exception as e:
            logger.error(f"Error intercepting EXT_bmesh_encoding data: {e}")

    def gather_import_mesh_before_hook(
        self, gltf_mesh: object, blender_mesh: object, gltf_importer: object
    ) -> None:
        """Hook to process EXT_bmesh_encoding during mesh import."""
        try:
            # Check if any primitives have EXT_bmesh_encoding extension
            if hasattr(gltf_mesh, 'primitives'):
                bmesh_decoder = BmeshDecoder()
                
                for primitive in gltf_mesh.primitives:
                    if hasattr(primitive, 'extensions') and primitive.extensions:
                        ext_bmesh_data = getattr(primitive.extensions, 'EXT_bmesh_encoding', None)
                        if ext_bmesh_data:
                            logger.info(f"Processing EXT_bmesh_encoding for mesh: {getattr(gltf_mesh, 'name', 'unnamed')}")
                            
                            # Convert extension data to dict format
                            extension_dict = self._convert_extension_to_dict(ext_bmesh_data)
                            logger.info(f"Extension data keys: {list(extension_dict.keys())}")
                            
                            # Debug: Log edge data structure
                            if "edges" in extension_dict:
                                edge_data = extension_dict["edges"]
                                logger.info(f"Edge data keys: {list(edge_data.keys())}")
                                if "attributes" in edge_data:
                                    logger.info(f"Edge attributes: {list(edge_data['attributes'].keys())}")
                                else:
                                    logger.warning("No 'attributes' found in edge data")
                            else:
                                logger.warning("No 'edges' found in extension data")
                            
                            # Reconstruct BMesh from extension data
                            reconstructed_bmesh = bmesh_decoder.decode_gltf_extension_to_bmesh(extension_dict, gltf_importer)
                            
                            if reconstructed_bmesh and blender_mesh:
                                # Apply reconstructed BMesh to Blender mesh
                                success = bmesh_decoder.apply_bmesh_to_blender_mesh(
                                    reconstructed_bmesh, blender_mesh
                                )
                                if success:
                                    logger.info("Successfully applied EXT_bmesh_encoding topology")
                                else:
                                    logger.warning("Failed to apply EXT_bmesh_encoding topology")
                                
                                reconstructed_bmesh.free()
                            
        except Exception as e:
            logger.error(f"Error processing EXT_bmesh_encoding during import: {e}")

    def _convert_extension_to_dict(self, ext_data: object) -> dict:
        """Convert glTF extension object to dictionary format."""
        try:
            logger.info(f"Converting extension data of type: {type(ext_data)}")
            
            # Handle direct dictionary
            if isinstance(ext_data, dict):
                logger.info(f"Extension data is already dict with keys: {list(ext_data.keys())}")
                return ext_data
            
            # Handle object with __dict__
            if hasattr(ext_data, '__dict__'):
                result = vars(ext_data)
                logger.info(f"Converted object to dict with keys: {list(result.keys())}")
                return result
            
            # Fallback: try to extract known attributes recursively
            result = {}
            for attr in ['vertices', 'edges', 'loops', 'faces']:
                value = getattr(ext_data, attr, None)
                if value is not None:
                    logger.info(f"Found {attr} attribute of type: {type(value)}")
                    
                    # Recursively convert nested objects
                    if hasattr(value, '__dict__'):
                        converted_value = vars(value)
                        logger.info(f"Converted {attr} object to dict with keys: {list(converted_value.keys())}")
                        
                        # Special handling for attributes nested objects
                        if 'attributes' in converted_value:
                            attrs = converted_value['attributes']
                            if hasattr(attrs, '__dict__'):
                                converted_value['attributes'] = vars(attrs)
                                logger.info(f"Converted {attr}.attributes to dict with keys: {list(converted_value['attributes'].keys())}")
                            elif isinstance(attrs, dict):
                                logger.info(f"{attr}.attributes is already dict with keys: {list(attrs.keys())}")
                        
                        result[attr] = converted_value
                    elif isinstance(value, (list, dict)):
                        result[attr] = value
                        logger.info(f"Used {attr} as-is (list/dict)")
                    else:
                        logger.warning(f"Unknown type for {attr}: {type(value)}")
                        
            logger.info(f"Final converted extension data keys: {list(result.keys())}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to convert extension data: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {}
