bl_info = {
    "name": "Reforge",
    "author": "Alexander Bulatov",
    "version": (0, 5, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Reforge",
    "description": "Reforge Blender scenes into Defold assets and collections.",
    "category": "Import-Export",
}

from . import settings
from . import operators
from . import ui

def register():
    settings.register()
    operators.register()
    ui.register()

def unregister():
    ui.unregister()
    operators.unregister()
    settings.unregister()