# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
import traceback
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import bpy
from bpy.app.translations import pgettext
from bpy.props import BoolProperty, CollectionProperty, StringProperty
from bpy.types import (
    Armature,
    Context,
    Event,
    Object,
    Operator,
    Panel,
    SpaceFileBrowser,
    UILayout,
)
from bpy_extras.io_utils import ExportHelper

from ..common import ops, safe_removal, version
from ..common.error_dialog import show_error_dialog
from ..common.logger import get_logger
from ..common.preferences import (
    ExportPreferencesProtocol,
    copy_export_preferences,
    draw_export_preferences_layout,
    get_preferences,
)
from ..common.workspace import save_workspace
from ..editor import migration, search, validation
from ..editor.extension import get_armature_extension
from ..editor.ops import VRM_OT_open_url_in_web_browser, layout_operator
from ..editor.property_group import CollectionPropertyProtocol, StringPropertyGroup
from ..editor.validation import VrmValidationError
from ..editor.vrm0.panel import (
    draw_vrm0_humanoid_operators_layout,
    draw_vrm0_humanoid_optional_bones_layout,
    draw_vrm0_humanoid_required_bones_layout,
)
from ..editor.vrm0.property_group import Vrm0HumanoidPropertyGroup
from ..editor.vrm1.ops import VRM_OT_assign_vrm1_humanoid_human_bones_automatically
from ..editor.vrm1.panel import (
    draw_vrm1_humanoid_optional_bones_layout,
    draw_vrm1_humanoid_required_bones_layout,
)
from ..editor.vrm1.property_group import Vrm1HumanBonesPropertyGroup
from .abstract_base_vrm_exporter import AbstractBaseVrmExporter
from .uni_vrm_vrm_animation_exporter import UniVrmVrmAnimationExporter
from .vrm0_exporter import Vrm0Exporter
from .vrm1_exporter import Vrm1Exporter

logger = get_logger(__name__)


def export_vrm_update_addon_preferences(
    export_op: "EXPORT_SCENE_OT_vrm", context: Context
) -> None:
    if export_op.use_addon_preferences:
        copy_export_preferences(source=export_op, destination=get_preferences(context))

    validation.WM_OT_vrm_validator.detect_errors(
        context,
        export_op.errors,
        export_op.armature_object_name,
    )


class EXPORT_SCENE_OT_vrm(Operator, ExportHelper):
    bl_idname = "export_scene.vrm"
    bl_label = "Save"
    bl_description = "export VRM"
    bl_options: AbstractSet[str] = {"REGISTER"}

    filename_ext = ".vrm"
    filter_glob: StringProperty(  # type: ignore[valid-type]
        default="*.vrm",
        options={"HIDDEN"},
    )

    use_addon_preferences: BoolProperty(  # type: ignore[valid-type]
        name="Export using add-on preferences",
        description="Export using add-on preferences instead of operator arguments",
    )
    export_invisibles: BoolProperty(  # type: ignore[valid-type]
        name="Export Invisible Objects",
        update=export_vrm_update_addon_preferences,
    )
    export_only_selections: BoolProperty(  # type: ignore[valid-type]
        name="Export Only Selections",
        update=export_vrm_update_addon_preferences,
    )
    enable_advanced_preferences: BoolProperty(  # type: ignore[valid-type]
        name="Enable Advanced Options",
        update=export_vrm_update_addon_preferences,
    )
    export_ext_bmesh_encoding: BoolProperty(  # type: ignore[valid-type]
        name="Export EXT_bmesh_encoding",
        description="Enable BMesh topology preservation using EXT_bmesh_encoding extension",
        update=export_vrm_update_addon_preferences,
    )
    export_all_influences: BoolProperty(  # type: ignore[valid-type]
        name="Export All Bone Influences",
        update=export_vrm_update_addon_preferences,
    )
    export_lights: BoolProperty(  # type: ignore[valid-type]
        name="Export Lights",
        update=export_vrm_update_addon_preferences,
    )
    export_gltf_animations: BoolProperty(  # type: ignore[valid-type]
        name="Export glTF Animations",
        update=export_vrm_update_addon_preferences,
    )
    export_try_sparse_sk: BoolProperty(  # type: ignore[valid-type]
        name="Use Sparse Accessors",
        update=export_vrm_update_addon_preferences,
    )
    export_try_sparse_sk: BoolProperty(  # type: ignore[valid-type]
        name="Export Sparse Shape Keys",
        description="Try to use sparse accessor for shape keys",
        update=export_vrm_update_addon_preferences,
    )

    errors: CollectionProperty(  # type: ignore[valid-type]
        type=validation.VrmValidationError,
        options={"HIDDEN"},
    )
    armature_object_name: StringProperty(  # type: ignore[valid-type]
        options={"HIDDEN"},
    )
    ignore_warning: BoolProperty(  # type: ignore[valid-type]
        options={"HIDDEN"},
    )

    def execute(self, context: Context) -> set[str]:
        try:
            if not self.filepath:
                return {"CANCELLED"}

            if self.use_addon_preferences:
                copy_export_preferences(
                    source=get_preferences(context), destination=self
                )

            return export_vrm(
                Path(self.filepath),
                self,
                context,
                armature_object_name=self.armature_object_name,
                export_ext_bmesh_encoding=self.export_ext_bmesh_encoding,
            )
        except Exception:
            show_error_dialog(
                pgettext("Failed to export VRM."),
                traceback.format_exc(),
            )
            raise

    def invoke(self, context: Context, event: Event) -> set[str]:
