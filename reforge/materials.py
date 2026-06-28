import os
import shutil
import bpy
from typing import Optional, List, Tuple

from .utils import ensure_dir, sanitize_id

DEFAULT_DEFOLD_TEXTURE = "/builtins/assets/images/logo/logo_256.png"
DEFAULT_BAKE_RESOLUTION = 1024
DEFAULT_BAKE_PADDING = 8

def ensure_material_props(mat: Optional[bpy.types.Material]):
    if not mat:
        return
    if "defold_material" not in mat:
        mat["defold_material"] = ""
    if "defold_texture" not in mat:
        mat["defold_texture"] = ""
    if "bake_color_texture" not in mat:
        mat["bake_color_texture"] = False
    if "bake_resolution" not in mat:
        mat["bake_resolution"] = DEFAULT_BAKE_RESOLUTION
    if "bake_padding" not in mat:
        mat["bake_padding"] = DEFAULT_BAKE_PADDING

def iter_unique_materials_in_order(obj: bpy.types.Object) -> List[bpy.types.Material]:
    result, seen = [], set()
    mats = []
    try:
        mats = list(obj.data.materials) if obj and obj.data else []
    except Exception:
        mats = []
    for m in mats:
        if not m:
            continue
        ptr = m.as_pointer()
        if ptr in seen:
            continue
        seen.add(ptr)
        result.append(m)
    return result

def find_image_for_principled_input(mat: bpy.types.Material, input_names: List[str]) -> Optional[bpy.types.Image]:
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None

    nodes = mat.node_tree.nodes
    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not principled:
        return None

    target_input = None
    for name in input_names:
        target_input = principled.inputs.get(name)
        if target_input and target_input.is_linked:
            break
        target_input = None

    if not target_input:
        return None

    start_node = target_input.links[0].from_socket.node

    visited, stack = set(), [start_node]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)

        if node.type == "TEX_IMAGE" and getattr(node, "image", None):
            return node.image

        if node.type == "NORMAL_MAP":
            color_input = node.inputs.get("Color")
            if color_input and color_input.is_linked:
                stack.append(color_input.links[0].from_socket.node)
            continue

        for inp in getattr(node, "inputs", []):
            if inp.is_linked:
                try:
                    stack.append(inp.links[0].from_socket.node)
                except Exception:
                    pass
    return None

def find_basecolor_image_from_material(mat: bpy.types.Material):
    return find_image_for_principled_input(mat, ["Base Color", "Color"])

def find_emission_image_from_material(mat: bpy.types.Material):
    return find_image_for_principled_input(mat, ["Emission", "Emission Color"])

def find_specular_image_from_material(mat: bpy.types.Material):
    return find_image_for_principled_input(mat, ["Specular", "Specular IOR Level", "Roughness"])

def find_normal_image_from_material(mat: bpy.types.Material):
    return find_image_for_principled_input(mat, ["Normal"])

def export_image_to_defold_project(image: bpy.types.Image, textures_abs_dir: str) -> Optional[str]:
    if not image:
        return None
    ensure_dir(textures_abs_dir)

    src_abs = None
    if image.filepath:
        src_abs = bpy.path.abspath(image.filepath)
        if not os.path.isfile(src_abs):
            src_abs = None

    if src_abs:
        filename = os.path.basename(src_abs)
    else:
        filename = sanitize_id(image.name) + ".png"

    dst_abs = os.path.join(textures_abs_dir, filename)

    try:
        if src_abs:
            shutil.copy2(src_abs, dst_abs)
        else:
            image.save_render(dst_abs)
    except Exception as e:
        print(f"[Reforge][WARN] Failed to export texture '{image.name}' -> {dst_abs}: {e}")
        return None

    return os.path.basename(dst_abs)

def resolve_defold_material_and_texture_for_material(
    settings,
    mat: Optional[bpy.types.Material],
    abs_textures_dir: str,
    textures_dir_project: str,
    obj: Optional[bpy.types.Object] = None,
) -> Tuple[str, str, dict]:
    # material name in .model must match glTF material name
    mat_name = mat.name if (mat and mat.name) else "default"

    def _get_custom_prop_str(idblock, key: str) -> str:
        if not idblock:
            return ""
        v = idblock.get(key)
        return str(v).strip() if v is not None else ""

    defold_mat_path = ""
    if mat:
        defold_mat_path = _get_custom_prop_str(mat, "defold_material")
    if not defold_mat_path and obj:
        defold_mat_path = _get_custom_prop_str(obj, "defold_material")
    if not defold_mat_path:
        defold_mat_path = (settings.default_material or "").strip() or "/builtins/materials/model.material"

    def _export_or_get_texture(img: Optional[bpy.types.Image]) -> str:
        if img:
            if settings.export_textures:
                saved_name = export_image_to_defold_project(img, abs_textures_dir)
                if saved_name:
                    return f"/{textures_dir_project}/{saved_name}".replace("\\", "/")
            else:
                if img.filepath:
                    return f"/{textures_dir_project}/{os.path.basename(bpy.path.abspath(img.filepath))}".replace("\\", "/")
        return ""

    is_illumination = "illumination/materials/model.material" in defold_mat_path

    samplers_dict = {}

    if is_illumination:
        diffuse_tex = _export_or_get_texture(find_basecolor_image_from_material(mat) if mat else None)
        emission_tex = _export_or_get_texture(find_emission_image_from_material(mat) if mat else None)
        specular_tex = _export_or_get_texture(find_specular_image_from_material(mat) if mat else None)
        normal_tex = _export_or_get_texture(find_normal_image_from_material(mat) if mat else None)

        empty_tex = "/illumination/textures/empty.png"
        
        samplers_dict["DIFFUSE_TEXTURE"] = diffuse_tex or DEFAULT_DEFOLD_TEXTURE
        samplers_dict["DATA_TEXTURE"] = "/illumination/textures/data.png"
        samplers_dict["LIGHT_TEXTURE"] = emission_tex or empty_tex
        samplers_dict["SPECULAR_TEXTURE"] = specular_tex or empty_tex
        samplers_dict["NORMAL_TEXTURE"] = normal_tex or empty_tex
    else:
        defold_tex_path = ""
        if mat:
            defold_tex_path = _get_custom_prop_str(mat, "defold_texture")
        if not defold_tex_path and obj:
            defold_tex_path = _get_custom_prop_str(obj, "defold_texture")
            
        if not defold_tex_path:
            defold_tex_path = _export_or_get_texture(find_basecolor_image_from_material(mat) if mat else None)

        if not defold_tex_path:
            defold_tex_path = DEFAULT_DEFOLD_TEXTURE
            
        samplers_dict["tex0"] = defold_tex_path

    return mat_name, defold_mat_path, samplers_dict
