# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
"""BMesh encoding preprocessor to prevent glTF2 import errors."""

from typing import Optional, Any, Dict
import copy

from ...common.logger import get_logger

logger = get_logger(__name__)


class BmeshEncodingPreprocessor:
    """Preprocesses glTF JSON to extract and temporarily store BMesh encoding data.
    
    This prevents the 'Error setting property vrm_addon_extension to value of type <class 'dict'>'
    error by removing problematic dictionary data before the glTF2 addon processes it.
    """
    
    # Class-level storage for extracted BMesh encoding data
    _extracted_data: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def clear_extracted_data(cls) -> None:
        """Clear all extracted BMesh encoding data."""
        cls._extracted_data.clear()
        
    @classmethod
    def get_extracted_data(cls, armature_name: str) -> Optional[Dict[str, Any]]:
        """Get extracted BMesh encoding data for a specific armature."""
        return cls._extracted_data.get(armature_name)
        
    @classmethod
    def preprocess_gltf_json(cls, json_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Preprocess glTF JSON to extract BMesh encoding data.
        
        Args:
            json_dict: The glTF JSON dictionary
            
        Returns:
            Cleaned JSON dictionary with BMesh encoding data removed
        """
        # Create a deep copy to avoid modifying the original
        cleaned_json = copy.deepcopy(json_dict)
        
        # Clear any previous extracted data
        cls._extracted_data.clear()
        
        # Process extensions
        extensions_dict = cleaned_json.get("extensions")
        if not isinstance(extensions_dict, dict):
            return cleaned_json
            
        # Process VRM 1.x extensions  
        vrm1_dict = extensions_dict.get("VRMC_vrm")
        if isinstance(vrm1_dict, dict):
            cls._extract_vrm1_bmesh_encoding(vrm1_dict, cleaned_json)
            
        return cleaned_json
        
    @classmethod
    def _extract_vrm1_bmesh_encoding(cls, vrm1_dict: Dict[str, Any], json_dict: Dict[str, Any]) -> None:
        """Extract BMesh encoding data from VRM 1.x extensions."""
        vrm_addon_extension = vrm1_dict.get("vrm_addon_extension")
        if not isinstance(vrm_addon_extension, dict):
            return
            
        bmesh_encoding_data = vrm_addon_extension.get("bmesh_encoding")
        if bmesh_encoding_data is not None:
            # Find armature name from humanoid data
            armature_name = cls._find_armature_name_vrm1(vrm1_dict, json_dict)
            if armature_name:
                logger.info(f"Extracting VRM 1.x BMesh encoding data for armature: {armature_name}")
                cls._extracted_data[armature_name] = bmesh_encoding_data
                
    @classmethod
    def _find_armature_name_vrm0(cls, vrm0_dict: Dict[str, Any], json_dict: Dict[str, Any]) -> Optional[str]:
        """Find armature name from VRM 0.x humanoid data."""
        humanoid_dict = vrm0_dict.get("humanoid")
        if not isinstance(humanoid_dict, dict):
            return None
            
        human_bones = humanoid_dict.get("humanBones")
        if not isinstance(human_bones, list):
            return None
            
        # Look for hips bone to identify the armature
        for bone_dict in human_bones:
            if not isinstance(bone_dict, dict):
                continue
            if bone_dict.get("bone") == "hips":
                node_index = bone_dict.get("node")
                if isinstance(node_index, int):
                    return cls._get_node_name(json_dict, node_index)
                    
        return None
        
    @classmethod
    def _find_armature_name_vrm1(cls, vrm1_dict: Dict[str, Any], json_dict: Dict[str, Any]) -> Optional[str]:
        """Find armature name from VRM 1.x humanoid data."""
        humanoid_dict = vrm1_dict.get("humanoid")
        if not isinstance(humanoid_dict, dict):
            return None
            
        human_bones_dict = humanoid_dict.get("humanBones")
        if not isinstance(human_bones_dict, dict):
            return None
            
        # Look for hips bone to identify the armature
        hips_dict = human_bones_dict.get("hips")
        if isinstance(hips_dict, dict):
            node_index = hips_dict.get("node")
            if isinstance(node_index, int):
                return cls._get_node_name(json_dict, node_index)
                
        return None
        
    @classmethod
    def _get_node_name(cls, json_dict: Dict[str, Any], node_index: int) -> Optional[str]:
        """Get node name from node index."""
        nodes = json_dict.get("nodes")
        if not isinstance(nodes, list) or node_index < 0 or node_index >= len(nodes):
            return None
            
        node = nodes[node_index]
        if not isinstance(node, dict):
            return None
            
        node_name = node.get("name")
        if isinstance(node_name, str):
            return node_name
            
        # Fall back to default naming convention
        return f"Armature_{node_index}"
