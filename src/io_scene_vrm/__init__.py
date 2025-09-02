# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
# SPDX-FileCopyrightText: 2018 iCyP

from . import registration
from .exporter import gltf2_export_user_extension
from .importer import gltf2_import_user_extension

bl_info = {
    "name": "VRM format",
    "author": "saturday06, iCyP",
    "version": (
        3,  # x-release-please-major
        11,  # x-release-please-minor
        5,  # x-release-please-patch
    ),
    "location": "File > Import-Export",
    "description": "Import-Edit-Export VRM",
    "blender": (2, 93, 0),
    "warning": "",
    "support": "COMMUNITY",
    "wiki_url": "",
    "doc_url": "https://vrm-addon-for-blender.info",
    "tracker_url": "https://github.com/saturday06/VRM-Addon-for-Blender/issues",
    "category": "Import-Export",
}

MINIMUM_UNSUPPORTED_BLENDER_MAJOR_MINOR_VERSION = (4, 6)


def cleanse_modules() -> None:
    """Search for your plugin modules in blender python sys.modules and remove them.

    To support reload properly, try to access a package var, if it's there,
    reload everything
    """
    import sys

    all_modules = sys.modules
    all_modules = dict(sorted(all_modules.items(), key=lambda x: x[0]))  # sort them

    for k in all_modules:
        if k == __name__ or k.startswith(__name__ + "."):
            del sys.modules[k]


def register() -> None:
    registration.register()


def unregister() -> None:
    registration.unregister()


class glTF2ImportUserExtension(gltf2_import_user_extension.glTF2ImportUserExtension):
    pass


class glTF2ExportUserExtension(gltf2_export_user_extension.glTF2ExportUserExtension):
    pass
