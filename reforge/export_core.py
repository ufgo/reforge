import os
from mathutils import Matrix

from .utils import ensure_dir, safe_remove_file, write_text_file, sanitize_id, select_only, export_glb_selected, get_prop, is_object_visible
from .materials import iter_unique_materials_in_order, resolve_defold_material_and_texture_for_material
from .collision import export_convex_hull_points, make_collisionobject_text
from .defold_formats import make_model_text_multi, make_go_ref_model_text, make_collection_text_grouped_embedded

AXIS_CONVERT = Matrix((
    (1, 0, 0, 0),
    (0, 0, 1, 0),
    (0, -1, 0, 0),
    (0, 0, 0, 1),
))

def has_defold_collision(obj) -> bool:
    return bool(get_prop(obj, "defold_collision"))

def get_collision_group(obj) -> str:
    v = get_prop(obj, "collision_group")
    v = (str(v).strip() if v is not None else "")
    return v if v else "default"

def get_collision_mask(obj) -> str:
    v = get_prop(obj, "collision_mask")
    v = (str(v).strip() if v is not None else "")
    return v if v else "default"

def to_defold_trs(obj):
    mw = obj.matrix_world.copy()
    c = AXIS_CONVERT
    mw_def = c @ mw @ c.inverted()
    loc = mw_def.to_translation()
    rot = mw_def.to_quaternion()
    scl = mw_def.to_scale()
    return (loc.x, loc.y, loc.z), (rot.x, rot.y, rot.z, rot.w), (scl.x, scl.y, scl.z)

def export_single_prototype_assets(context, obj) -> str:
    s = context.scene.reforge_settings
    project_root = s.project_root
    if not project_root or not os.path.isdir(project_root):
        raise RuntimeError("Project Root is empty or not found.")

    if obj.type != "MESH":
        raise RuntimeError("Active object is not a MESH.")

    proto_raw = get_prop(obj, "defold_prototype")
    if not proto_raw:
        raise RuntimeError("Active object has no 'defold_prototype' custom property.")
    proto = sanitize_id(proto_raw)

    abs_models = os.path.join(project_root, s.models_dir)
    abs_prefabs = os.path.join(project_root, s.prefabs_dir)
    abs_textures = os.path.join(project_root, s.textures_dir)
    abs_collisions = os.path.join(project_root, s.collisions_dir)

    ensure_dir(abs_models)
    ensure_dir(abs_prefabs)
    ensure_dir(abs_collisions)
    if s.export_textures:
        ensure_dir(abs_textures)

    glb_filename = f"{proto}.glb"
    model_filename = f"{proto}.model"
    go_filename = f"{proto}.go"

    abs_glb = os.path.join(abs_models, glb_filename)
    abs_model = os.path.join(abs_models, model_filename)
    abs_go = os.path.join(abs_prefabs, go_filename)

    glb_project_path = f"/{s.models_dir}/{glb_filename}".replace("\\", "/")
    model_project_path = f"/{s.models_dir}/{model_filename}".replace("\\", "/")

    # clean generated files (never delete .go)
    safe_remove_file(abs_glb)
    safe_remove_file(abs_model)
    safe_remove_file(os.path.join(abs_collisions, f"{proto}.convexshape"))
    safe_remove_file(os.path.join(abs_collisions, f"{proto}.collisionobject"))

    # export GLB
    select_only(obj)
    export_glb_selected(abs_glb)

    # materials blocks
    materials = iter_unique_materials_in_order(obj)
    blocks = []
    if materials:
        for mat in materials:
            blocks.append(resolve_defold_material_and_texture_for_material(
                settings=s,
                mat=mat,
                abs_textures_dir=abs_textures,
                textures_dir_project=s.textures_dir
            ))
    else:
        blocks.append(resolve_defold_material_and_texture_for_material(
            settings=s, mat=None, abs_textures_dir=abs_textures, textures_dir_project=s.textures_dir
        ))

    write_text_file(abs_model, make_model_text_multi(glb_project_path, proto, blocks))

    collisionobject_project_path = None
    if has_defold_collision(obj):
        group = get_collision_group(obj)
        mask = get_collision_mask(obj)

        abs_convex = os.path.join(abs_collisions, f"{proto}.convexshape")
        abs_colobj = os.path.join(abs_collisions, f"{proto}.collisionobject")

        convex_project_path = f"/{s.collisions_dir}/{proto}.convexshape".replace("\\", "/")
        colobj_project_path = f"/{s.collisions_dir}/{proto}.collisionobject".replace("\\", "/")

        export_convex_hull_points(obj, abs_convex)
        write_text_file(abs_colobj, make_collisionobject_text(convex_project_path, group, mask))
        collisionobject_project_path = colobj_project_path

    if not os.path.isfile(abs_go):
        write_text_file(abs_go, make_go_ref_model_text(model_project_path, collisionobject_project_path))

    return proto

def export_all_prototypes_assets_no_scene(context) -> int:
    s = context.scene.reforge_settings
    view_layer = context.view_layer

    groups = {}
    for obj in context.scene.objects:
        if obj.type != "MESH":
            continue
        if s.export_visible_only and not is_object_visible(obj, view_layer):
            continue
        proto = get_prop(obj, "defold_prototype")
        if not proto:
            continue
        proto = sanitize_id(proto)
        groups.setdefault(proto, []).append(obj)

    if not groups:
        raise RuntimeError("No MESH objects with 'defold_prototype' found (with current visibility filter).")

    n = 0
    for proto in sorted(groups.keys()):
        export_single_prototype_assets(context, groups[proto][0])
        n += 1
    return n

def run_export_scene(context) -> str:
    s = context.scene.reforge_settings
    project_root = s.project_root
    if not project_root or not os.path.isdir(project_root):
        raise RuntimeError("Project Root is empty or not found.")

    abs_scenes = os.path.join(project_root, s.scenes_dir)
    ensure_dir(abs_scenes)

    groups = {}
    view_layer = context.view_layer
    for obj in context.scene.objects:
        if obj.type != "MESH":
            continue
        if s.export_visible_only and not is_object_visible(obj, view_layer):
            continue
        proto = get_prop(obj, "defold_prototype")
        if not proto:
            continue
        proto = sanitize_id(proto)
        groups.setdefault(proto, []).append(obj)

    if not groups:
        raise RuntimeError("No MESH objects with 'defold_prototype' found (with current visibility filter).")

    # Ensure all prototypes are exported (assets + go created once)
    proto_to_go = {}
    for proto, objs in groups.items():
        etalon = objs[0]
        export_single_prototype_assets(context, etalon)
        go_path = f"/{s.prefabs_dir}/{proto}.go".replace("\\", "/")
        proto_to_go[proto] = go_path

    instances_by_proto = {}
    counters = {p: 0 for p in groups.keys()}
    for proto, objs in groups.items():
        for obj in objs:
            counters[proto] += 1
            inst_id = f"{proto}_{counters[proto]:03d}"
            pos, quat, scale = to_defold_trs(obj)
            instances_by_proto.setdefault(proto, []).append({
                "id": inst_id,
                "prototype": proto_to_go[proto],
                "pos": pos,
                "quat": quat,
                "scale": scale,
            })

    protos_sorted = sorted(groups.keys())
    collection_text = make_collection_text_grouped_embedded(s.collection_name, protos_sorted, instances_by_proto)

    abs_collection = os.path.join(abs_scenes, f"{s.collection_name}.collection")
    safe_remove_file(abs_collection)
    write_text_file(abs_collection, collection_text)
    return abs_collection