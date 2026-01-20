import os
import bpy

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def safe_remove_file(path: str):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception as e:
        print(f"[Reforge][WARN] Can't remove file: {path} ({e})")

def write_text_file(abs_path: str, text: str):
    with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def sanitize_id(s: str) -> str:
    s = str(s).strip().replace(" ", "_")
    s = "".join(ch for ch in s if ch.isalnum() or ch in "_-")
    return s or "prototype"

def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def export_glb_selected(abs_path: str):
    bpy.ops.export_scene.gltf(
        filepath=abs_path,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials='EXPORT',
        export_animations=False,
    )

def get_prop(obj, key):
    v = obj.get(key)
    if v is None and getattr(obj, "data", None) is not None:
        v = obj.data.get(key)
    return v

def is_object_visible(obj, view_layer) -> bool:
    if obj.hide_get():
        return False
    try:
        return obj.visible_get(view_layer=view_layer)
    except TypeError:
        return obj.visible_get()