import bpy

from .export_core import run_export_scene, export_single_prototype_assets, export_all_prototypes_assets_no_scene
from .utils import is_object_visible
from .utils import sanitize_id

# Keys to clear (exporter-created)
OBJECT_EXPORT_KEYS = ("defold_prototype", "defold_collision", "collision_group", "collision_mask")
MATERIAL_EXPORT_KEYS = ("defold_material", "defold_texture")

def _collect_materials_from_objects(objects):
    mats, seen = [], set()
    for obj in objects:
        data = getattr(obj, "data", None)
        if not data or not hasattr(data, "materials"):
            continue
        for m in data.materials:
            if not m:
                continue
            ptr = m.as_pointer()
            if ptr in seen:
                continue
            seen.add(ptr)
            mats.append(m)
    return mats

def safe_clear_for_objects(objects) -> dict:
    mats = _collect_materials_from_objects(objects)
    deleted = 0

    for obj in objects:
        for k in OBJECT_EXPORT_KEYS:
            if k in obj.keys():
                del obj[k]
                deleted += 1

    for m in mats:
        for k in MATERIAL_EXPORT_KEYS:
            if k in m.keys():
                del m[k]
                deleted += 1

    return {"objects": len(objects), "materials": len(mats), "deleted_keys": deleted}

def _set_custom_prop(obj, key, value, overwrite: bool) -> bool:
    if (obj.get(key) is None) or overwrite:
        obj[key] = value
        return True
    return False

def _set_properties_for_objects(context, objects):
    s = context.scene.reforge_settings
    changed = {"proto": 0, "proto_skip": 0, "col": 0, "col_skip": 0, "grp": 0, "grp_skip": 0, "msk": 0, "msk_skip": 0}

    group_value = (s.set_collision_group_value or "").strip() or "default"
    mask_value = (s.set_collision_mask_value or "").strip() or "default"

    for obj in objects:
        proto_value = sanitize_id(obj.name)

        if _set_custom_prop(obj, "defold_prototype", proto_value, s.overwrite_prototype):
            changed["proto"] += 1
        else:
            changed["proto_skip"] += 1

        if _set_custom_prop(obj, "defold_collision", bool(s.set_defold_collision_value), s.overwrite_collision):
            changed["col"] += 1
        else:
            changed["col_skip"] += 1

        if _set_custom_prop(obj, "collision_group", group_value, s.overwrite_collision_group):
            changed["grp"] += 1
        else:
            changed["grp_skip"] += 1

        if _set_custom_prop(obj, "collision_mask", mask_value, s.overwrite_collision_mask):
            changed["msk"] += 1
        else:
            changed["msk_skip"] += 1

    return changed


class REFORGE_OT_generate(bpy.types.Operator):
    """Generate Defold scene (.collection) from the current Blender scene."""
    bl_idname = "reforge.generate"
    bl_label = "Generate Scene (.collection)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            out = run_export_scene(context)
            self.report({'INFO'}, f"Generated: {out}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class REFORGE_OT_export_selected_prototype(bpy.types.Operator):
    """Export only the active object's prototype assets (GLB + .model + optional collision), without regenerating the scene."""
    bl_idname = "reforge.export_selected_prototype"
    bl_label = "Export Selected Prototype (No Scene)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj:
                raise RuntimeError("No active object selected.")
            proto = export_single_prototype_assets(context, obj)
            self.report({'INFO'}, f"Exported prototype: {proto}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class REFORGE_OT_export_all_prototypes(bpy.types.Operator):
    """Export all prototypes' assets in the scene, without regenerating the collection."""
    bl_idname = "reforge.export_all_prototypes"
    bl_label = "Export ALL Prototypes (No Scene)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            n = export_all_prototypes_assets_no_scene(context)
            self.report({'INFO'}, f"Exported prototypes: {n}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class REFORGE_OT_set_selected(bpy.types.Operator):
    """Set exporter properties on selected objects (defold_prototype + collision flags)."""
    bl_idname = "reforge.set_selected"
    bl_label = "1) Set Props (Selected)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objs = list(context.selected_objects) or ([context.active_object] if context.active_object else [])
        if not objs:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        ch = _set_properties_for_objects(context, objs)
        self.report({'INFO'}, f"proto {ch['proto']}/{ch['proto_skip']} | col {ch['col']}/{ch['col_skip']} | group {ch['grp']}/{ch['grp_skip']} | mask {ch['msk']}/{ch['msk_skip']}")
        return {'FINISHED'}


class REFORGE_OT_set_visible(bpy.types.Operator):
    """Set exporter properties on visible objects in the current view layer."""
    bl_idname = "reforge.set_visible"
    bl_label = "2) Set Props (Visible)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objs = [o for o in context.scene.objects if is_object_visible(o, context.view_layer)]
        if not objs:
            self.report({'WARNING'}, "No visible objects found")
            return {'CANCELLED'}

        ch = _set_properties_for_objects(context, objs)
        self.report({'INFO'}, f"proto {ch['proto']}/{ch['proto_skip']} | col {ch['col']}/{ch['col_skip']} | group {ch['grp']}/{ch['grp_skip']} | mask {ch['msk']}/{ch['msk_skip']}")
        return {'FINISHED'}


class REFORGE_OT_set_all(bpy.types.Operator):
    """Set exporter properties on all objects in the scene."""
    bl_idname = "reforge.set_all"
    bl_label = "3) Set Props (All)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objs = list(context.scene.objects)
        if not objs:
            self.report({'WARNING'}, "No objects in scene")
            return {'CANCELLED'}

        ch = _set_properties_for_objects(context, objs)
        self.report({'INFO'}, f"proto {ch['proto']}/{ch['proto_skip']} | col {ch['col']}/{ch['col_skip']} | group {ch['grp']}/{ch['grp_skip']} | mask {ch['msk']}/{ch['msk_skip']}")
        return {'FINISHED'}


class REFORGE_OT_clear_selected(bpy.types.Operator):
    """Remove exporter-created custom properties from selected objects and their used materials."""
    bl_idname = "reforge.clear_selected"
    bl_label = "Clear Export Props (Selected)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        objs = list(context.selected_objects) or ([context.active_object] if context.active_object else [])
        if not objs:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        st = safe_clear_for_objects(objs)
        self.report({'INFO'}, f"Cleared: obj {st['objects']}, mat {st['materials']}, keys {st['deleted_keys']}")
        return {'FINISHED'}


class REFORGE_OT_clear_visible(bpy.types.Operator):
    """Remove exporter-created custom properties from visible objects and their used materials."""
    bl_idname = "reforge.clear_visible"
    bl_label = "Clear Export Props (Visible)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        objs = [o for o in context.scene.objects if is_object_visible(o, context.view_layer)]
        if not objs:
            self.report({'WARNING'}, "No visible objects found")
            return {'CANCELLED'}

        st = safe_clear_for_objects(objs)
        self.report({'INFO'}, f"Cleared: obj {st['objects']}, mat {st['materials']}, keys {st['deleted_keys']}")
        return {'FINISHED'}


class REFORGE_OT_clear_all(bpy.types.Operator):
    """Remove exporter-created custom properties from all objects and their used materials."""
    bl_idname = "reforge.clear_all"
    bl_label = "Clear Export Props (All)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        objs = list(context.scene.objects)
        if not objs:
            self.report({'WARNING'}, "No objects in scene")
            return {'CANCELLED'}

        st = safe_clear_for_objects(objs)
        self.report({'INFO'}, f"Cleared: obj {st['objects']}, mat {st['materials']}, keys {st['deleted_keys']}")
        return {'FINISHED'}


_CLASSES = (
    REFORGE_OT_generate,
    REFORGE_OT_export_selected_prototype,
    REFORGE_OT_export_all_prototypes,
    REFORGE_OT_set_selected,
    REFORGE_OT_set_visible,
    REFORGE_OT_set_all,
    REFORGE_OT_clear_selected,
    REFORGE_OT_clear_visible,
    REFORGE_OT_clear_all,
)

def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)