import bpy

def draw_foldout_header(layout, prop_owner, prop_name: str):
    is_open = bool(getattr(prop_owner, prop_name))
    icon = "TRIA_DOWN" if is_open else "TRIA_RIGHT"
    row = layout.row()
    row.prop(prop_owner, prop_name, icon=icon, emboss=False)
    return is_open

class REFORGE_PT_panel(bpy.types.Panel):
    bl_label = "Reforge"
    bl_idname = "REFORGE_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Reforge"

    def draw(self, context):
        layout = self.layout
        s = context.scene.reforge_settings

        box = layout.box()
        if draw_foldout_header(box, s, "show_export"):
            col = box.column(align=True)
            col.prop(s, "project_root")
            col.prop(s, "collection_name")
            col.separator()
            col.prop(s, "export_visible_only")
            col.prop(s, "export_textures")
            col.prop(s, "default_material")
            col.separator()
            col.operator("reforge.generate", icon="EXPORT")

        box = layout.box()
        if draw_foldout_header(box, s, "show_quick_export"):
            col = box.column(align=True)
            col.label(text="Update assets without regenerating scene:")
            col.separator()
            col.operator("reforge.export_selected_prototype", icon="EXPORT")
            col.operator("reforge.export_all_prototypes", icon="EXPORT")

        box = layout.box()
        if draw_foldout_header(box, s, "show_textures"):
            col = box.column(align=True)
            col.prop(s, "export_textures")
            col.separator()
            col.label(text="Material Custom Properties:")
            col.label(text='- defold_material (string) -> Defold .material path')
            col.label(text='- defold_texture  (string) -> Defold texture path (optional)')
            col.separator()
            col.label(text="If defold_texture is missing:")
            col.label(text="Principled BSDF -> Base Color -> Image Texture is used.")

        box = layout.box()
        if draw_foldout_header(box, s, "show_folders"):
            col = box.column(align=True)
            col.prop(s, "models_dir")
            col.prop(s, "prefabs_dir")
            col.prop(s, "scenes_dir")
            col.prop(s, "textures_dir")
            col.prop(s, "collisions_dir")

        box = layout.box()
        if draw_foldout_header(box, s, "show_tools"):
            col = box.column(align=True)
            col.label(text="Write OBJECT custom properties:")
            col.prop(s, "set_defold_collision_value")
            col.prop(s, "set_collision_group_value")
            col.prop(s, "set_collision_mask_value")

            col.separator()
            col.label(text="Overwrite:")
            row = col.row()
            row.prop(s, "overwrite_prototype")
            row.prop(s, "overwrite_collision")
            row = col.row()
            row.prop(s, "overwrite_collision_group")
            row.prop(s, "overwrite_collision_mask")

            col.separator()
            col.operator("reforge.set_selected", icon="RESTRICT_SELECT_OFF")
            col.operator("reforge.set_visible", icon="HIDE_OFF")
            col.operator("reforge.set_all", icon="SCENE_DATA")

        box = layout.box()
        if draw_foldout_header(box, s, "show_clear"):
            col = box.column(align=True)
            col.label(text="Removes ONLY exporter-created properties.")
            col.label(text="Affects Objects + used Materials.")
            col.separator()
            col.operator("reforge.clear_selected", icon="TRASH")
            col.operator("reforge.clear_visible", icon="TRASH")
            col.operator("reforge.clear_all", icon="TRASH")


_CLASSES = (REFORGE_PT_panel,)

def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)