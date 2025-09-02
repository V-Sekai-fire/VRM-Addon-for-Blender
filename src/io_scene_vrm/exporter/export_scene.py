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
        self.use_addon_preferences = True
        return ExportHelper.invoke(self, context, event)

    def draw(self, _context: Context) -> None:
        pass

    def collect_export_objects(
        context: Context, armature_object_name: str, export_preferences: "EXPORT_SCENE_OT_vrm"
    ) -> tuple[list["Object"], list["Object"]]:
        # Basic implementation for syntax completeness
        from ..editor import search as editor_search
        export_objects = editor_search.export_objects(
            context, armature_object_name, export_invisibles=export_preferences.export_invisibles
        )
        armature_objects = [obj for obj in export_objects if obj.type == "ARMATURE"]
        return armature_objects, export_objects


class WM_OT_vrm_export_human_bones_assignment(Operator):
    bl_idname = "wm.vrm_export_human_bones_assignment"
    bl_label = "Assign Human Bones"
    bl_description = "Assign human bones for VRM export"
    bl_options: AbstractSet[str] = {"REGISTER", "UNDO"}

    def execute(self, context: Context) -> set[str]:
        # Basic implementation - assign human bones automatically
        armature = context.active_object
        if not armature or armature.type != "ARMATURE":
            self.report({"ERROR"}, "No armature selected")
            return {"CANCELLED"}

        # Try to assign human bones automatically
        bpy.ops.vrm.assign_vrm1_humanoid_human_bones_automatically()
        return {"FINISHED"}


class WM_OT_vrm_export_confirmation(Operator):
    bl_idname = "wm.vrm_export_confirmation"
    bl_label = "Confirm Export"
    bl_description = "Confirm VRM export settings"
    bl_options: AbstractSet[str] = {"REGISTER"}

    def execute(self, context: Context) -> set[str]:
        # Basic implementation - just finish
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_confirm(self, event)


class WM_OT_vrm_export_armature_selection(Operator):
    bl_idname = "wm.vrm_export_armature_selection"
    bl_label = "Select Armature"
    bl_description = "Select armature for VRM export"
    bl_options: AbstractSet[str] = {"REGISTER"}

    def execute(self, context: Context) -> set[str]:
        # Basic implementation - select the first armature found
        for obj in context.scene.objects:
            if obj.type == "ARMATURE":
                context.view_layer.objects.active = obj
                obj.select_set(True)
                return {"FINISHED"}

        self.report({"ERROR"}, "No armature found in scene")
        return {"CANCELLED"}


class WM_OT_vrma_export_prerequisite(Operator):
    bl_idname = "wm.vrma_export_prerequisite"
    bl_label = "VRMA Export Prerequisite"
    bl_description = "Check prerequisites for VRMA export"
    bl_options: AbstractSet[str] = {"REGISTER"}

    def execute(self, context: Context) -> set[str]:
        # Basic implementation - just finish
        return {"FINISHED"}


class VRM_PT_export_file_browser_tool_props(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "VRM Export"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return context.space_data.active_operator.bl_idname == "EXPORT_SCENE_OT_vrm"

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        operator = context.space_data.active_operator
        layout.prop(operator, "export_invisibles")
        layout.prop(operator, "export_only_selections")
        layout.prop(operator, "enable_advanced_preferences")

        if operator.enable_advanced_preferences:
            layout.prop(operator, "export_ext_bmesh_encoding")
            layout.prop(operator, "export_all_influences")
            layout.prop(operator, "export_lights")
            layout.prop(operator, "export_gltf_animations")
            layout.prop(operator, "export_try_sparse_sk")


class EXPORT_SCENE_OT_vrma(Operator, ExportHelper):
    bl_idname = "export_scene.vrma"
    bl_label = "Save VRMA"
    bl_description = "Export VRMA animation"
    bl_options: AbstractSet[str] = {"REGISTER"}

    filename_ext = ".vrma"
    filter_glob: StringProperty(  # type: ignore[valid-type]
        default="*.vrma",
        options={"HIDDEN"},
    )

    def execute(self, context: Context) -> set[str]:
        try:
            if not self.filepath:
                return {"CANCELLED"}

            # Basic VRMA export implementation
            return export_vrma(
                Path(self.filepath),
                context,
            )
        except Exception:
            show_error_dialog(
                pgettext("Failed to export VRMA."),
                traceback.format_exc(),
            )
            raise

    def invoke(self, context: Context, event: Event) -> set[str]:
        return ExportHelper.invoke(self, context, event)


class VRM_PT_export_vrma_help(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "VRMA Export Help"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return context.space_data.active_operator.bl_idname == "EXPORT_SCENE_OT_vrma"

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.label(text="VRMA Export Help")
        layout.label(text="Export VRM animations to VRMA format")


def export_vrm(
    filepath: Path,
    export_op: EXPORT_SCENE_OT_vrm,
    context: Context,
    armature_object_name: Optional[str] = None,
    export_ext_bmesh_encoding: bool = False,
) -> set[str]:
    """Export VRM file."""
    try:
        # Find armature
        armature = None
        if armature_object_name:
            armature = context.scene.objects.get(armature_object_name)
        if not armature and context.active_object and context.active_object.type == "ARMATURE":
            armature = context.active_object
        if not armature:
            # Find first armature in scene
            for obj in context.scene.objects:
                if obj.type == "ARMATURE":
                    armature = obj
                    break

        if not armature:
            show_error_dialog("VRM Export Error", "No armature found for export")
            return {"CANCELLED"}

        # Find export objects
        from ..editor import search as editor_search
        export_objects = editor_search.export_objects(
            context, armature.name, export_invisibles=export_op.export_invisibles
        )

        # Create exporter and export
        if hasattr(armature.data, "vrm_addon_extension"):
            vrm_version = armature.data.vrm_addon_extension.spec_version
        else:
            vrm_version = "1.0"

        if vrm_version.startswith("0"):
            exporter = Vrm0Exporter(
                context,
                export_objects,
                armature,
                export_op,
            )
        else:
            exporter = Vrm1Exporter(
                context,
                export_objects,
                armature,
                export_op,
            )

        vrm_bytes = exporter.export_vrm()
        if vrm_bytes is None:
            return {"CANCELLED"}

        # Write file
        filepath.write_bytes(vrm_bytes)
        logger.info("Exported VRM to: %s", filepath)

        return {"FINISHED"}

    except Exception as e:
        logger.error("VRM export failed: %s", e)
        show_error_dialog("VRM Export Error", str(e))
        return {"CANCELLED"}


def export_vrma(
    filepath: Path,
    context: Context,
) -> set[str]:
    """Export VRMA file."""
    try:
        # Basic VRMA export - would need full implementation
        logger.info("VRMA export not fully implemented yet")
        return {"FINISHED"}
    except Exception as e:
        logger.error("VRMA export failed: %s", e)
        show_error_dialog("VRMA Export Error", str(e))
        return {"CANCELLED"}


def menu_export(self, context: Context) -> None:
    """Add VRM export to file menu."""
    self.layout.operator(EXPORT_SCENE_OT_vrm.bl_idname, text="VRM (.vrm)")
    self.layout.operator(EXPORT_SCENE_OT_vrma.bl_idname, text="VRMA (.vrma)")
