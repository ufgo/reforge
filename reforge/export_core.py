# reforge/export_core.py
import os
from mathutils import Matrix

from .utils import (
    ensure_dir,
    safe_remove_file,
    write_text_file,
    sanitize_id,
    select_only,
    export_glb_selected,
    get_prop,
    is_object_visible,
)

from .materials import (
    iter_unique_materials_in_order,
    resolve_defold_material_and_texture_for_material,
    ensure_material_props,
)

from .collision import (
    export_convex_hull_points,
    make_collisionobject_text,
)

from .defold_formats import (
    make_model_text_multi,
    make_go_ref_model_text,
    make_collection_text_grouped_embedded,
    parse_existing_collection,
    extract_instance_component_properties,
)

from .bake import bake_color_emit_png


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


def matrix_to_defold_trs(matrix):
    """
    Convert a 4x4 matrix to Defold-friendly TRS using axis conversion.
    Returns:
      pos (x,y,z), quat (x,y,z,w), scale (x,y,z)
    """
    c = AXIS_CONVERT
    mw_def = c @ matrix @ c.inverted()
    loc = mw_def.to_translation()
    rot = mw_def.to_quaternion()
    scl = mw_def.to_scale()
    return (loc.x, loc.y, loc.z), (rot.x, rot.y, rot.z, rot.w), (scl.x, scl.y, scl.z)


def to_defold_trs(obj):
    """
    Convert Blender world transform to Defold-friendly TRS using axis conversion.
    Returns:
      pos (x,y,z), quat (x,y,z,w), scale (x,y,z)
    """
    return matrix_to_defold_trs(obj.matrix_world)


def _make_baked_texture_filename(proto: str, mat_name: str) -> str:
    # Stable filename, always PNG
    return f"{proto}__{sanitize_id(mat_name)}_albedo.png"

def _material_prop_bool(mat, key: str, default: bool = False) -> bool:
    if not mat:
        return default
    v = mat.get(key)
    return bool(v) if v is not None else default

def _material_prop_int(mat, key: str, default: int) -> int:
    if not mat:
        return default
    v = mat.get(key)
    try:
        return int(v)
    except Exception:
        return default


def export_single_prototype_assets(context, obj) -> str:
    """
    Export assets for ONE prototype:
      - <proto>.glb
      - <proto>.model
      - create <proto>.go once (never overwritten)
      - optional collision: <proto>.convexshape + <proto>.collisionobject (overwritten)
      - optional bake: per-material PNGs (overwritten)
    Returns: proto id (sanitized)
    """
    s = context.scene.reforge_settings
    project_root = s.project_root
    if not project_root or not os.path.isdir(project_root):
        raise RuntimeError("Project Root is empty or not found.")

    if not obj or obj.type != "MESH":
        raise RuntimeError("Active object is not a MESH.")

    proto_raw = get_prop(obj, "defold_prototype")
    if not proto_raw:
        raise RuntimeError("Active object has no 'defold_prototype' custom property.")
    proto = sanitize_id(proto_raw)

    # absolute dirs
    abs_models = os.path.join(project_root, s.models_dir)
    abs_prefabs = os.path.join(project_root, s.prefabs_dir)
    abs_textures = os.path.join(project_root, s.textures_dir)
    abs_collisions = os.path.join(project_root, s.collisions_dir)

    materials = iter_unique_materials_in_order(obj)
    for m in materials:
        ensure_material_props(m)
    needs_bake = any(_material_prop_bool(m, "bake_color_texture") for m in materials)

    # ensure dirs
    ensure_dir(abs_models)
    ensure_dir(abs_prefabs)
    ensure_dir(abs_collisions)
    if s.export_textures or needs_bake:
        ensure_dir(abs_textures)

    # filenames
    glb_filename = f"{proto}.glb"
    model_filename = f"{proto}.model"
    go_filename = f"{proto}.go"

    # absolute paths
    abs_glb = os.path.join(abs_models, glb_filename)
    abs_model = os.path.join(abs_models, model_filename)
    abs_go = os.path.join(abs_prefabs, go_filename)

    # project paths
    glb_project_path = f"/{s.models_dir}/{glb_filename}".replace("\\", "/")
    model_project_path = f"/{s.models_dir}/{model_filename}".replace("\\", "/")

    # cleanup generated files (NEVER delete .go)
    safe_remove_file(abs_glb)
    safe_remove_file(abs_model)

    # cleanup collision generated
    safe_remove_file(os.path.join(abs_collisions, f"{proto}.convexshape"))
    safe_remove_file(os.path.join(abs_collisions, f"{proto}.collisionobject"))

    # export GLB from selection
    select_only(obj)
    export_glb_selected(abs_glb, obj)

    # build .model material blocks
    blocks = []

    if materials:
        for mat in materials:
            mat_name, defold_mat_path, samplers_dict = resolve_defold_material_and_texture_for_material(
                settings=s,
                mat=mat,
                abs_textures_dir=abs_textures,
                textures_dir_project=s.textures_dir,
                obj=obj
            )

            # Bake overrides tex0 path (works with complex materials / Ucupaint)
            if _material_prop_bool(mat, "bake_color_texture"):
                baked_filename = _make_baked_texture_filename(proto, mat_name)
                baked_tex_path = f"/{s.textures_dir}/{baked_filename}".replace("\\", "/")

                if s.export_textures:
                    bake_resolution = _material_prop_int(mat, "bake_resolution", 1024)
                    bake_padding = _material_prop_int(mat, "bake_padding", 8)
                    baked_abs = os.path.join(abs_textures, baked_filename)

                    # overwrite old baked file to avoid _1/_2 naming issues
                    safe_remove_file(baked_abs)

                    baked_ok = bake_color_emit_png(
                        obj=obj,
                        mat=mat,
                        out_abs_path=baked_abs,
                        resolution=bake_resolution,
                        padding=bake_padding,
                    )
                    if not baked_ok:
                        print(f"[Reforge][WARN] Failed to bake texture for {mat_name}")

                # Even if we skip baking (export_textures is False), we still map the path
                if "DIFFUSE_TEXTURE" in samplers_dict:
                    samplers_dict["DIFFUSE_TEXTURE"] = baked_tex_path
                else:
                    samplers_dict["tex0"] = baked_tex_path

            blocks.append((mat_name, defold_mat_path, samplers_dict))
    else:
        # no materials on mesh -> use default single block
        mat_name, defold_mat_path, samplers_dict = resolve_defold_material_and_texture_for_material(
            settings=s,
            mat=None,
            abs_textures_dir=abs_textures,
            textures_dir_project=s.textures_dir,
            obj=obj
        )
        blocks.append((mat_name, defold_mat_path, samplers_dict))

    # write .model
    write_text_file(abs_model, make_model_text_multi(glb_project_path, proto, blocks))

    # optional collision
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

    # create .go ONCE (do not overwrite to preserve manual edits like collision/logic added in Defold)
    if not os.path.isfile(abs_go):
        write_text_file(abs_go, make_go_ref_model_text(model_project_path, collisionobject_project_path))

    return proto


def export_all_prototypes_assets_no_scene(context) -> int:
    """
    Export assets (.glb/.model/optional collisions/bake) for all prototypes in scene.
    Does NOT regenerate .collection.
    """
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
        # export only "etalon" mesh for this proto
        export_single_prototype_assets(context, groups[proto][0])
        n += 1
    return n


def run_export_scene(context) -> str:
    """
    Full pipeline:
      - export assets for each prototype (etalon)
      - generate <collection_name>.collection with grouped embedded instances:
            root
              ├─ <protoA> -> children instances
              ├─ <protoB> -> children instances
              ...
      - for each unique non-empty defold_group value found on objects,
        grouped as an embedded instance directly under 'root'.
    Returns absolute path to generated main .collection
    """
    s = context.scene.reforge_settings
    project_root = s.project_root
    if not project_root or not os.path.isdir(project_root):
        raise RuntimeError("Project Root is empty or not found.")

    abs_scenes = os.path.join(project_root, s.scenes_dir)
    ensure_dir(abs_scenes)

    # group objects by prototype; track defold_group per object
    groups = {}       # proto -> list of obj (all objs sharing that proto)
    obj_group = {}    # obj -> group name (str, may be "")
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

        raw_grp = get_prop(obj, "defold_group")
        if raw_grp is None:
            raw_grp = get_prop(obj, "defold_collection")
        grp_name = (str(raw_grp).strip() if raw_grp is not None else "")
        obj_group[id(obj)] = grp_name

    if not groups:
        raise RuntimeError("No MESH objects with 'defold_prototype' found (with current visibility filter).")

    # ensure all prototypes are exported; create .go once
    proto_to_go = {}
    for proto, objs in groups.items():
        export_single_prototype_assets(context, objs[0])
        proto_to_go[proto] = f"/{s.prefabs_dir}/{proto}.go".replace("\\", "/")

    # ----------------------------------------------------------------
    # Build instance data for MAIN collection (defold_group == "")
    # and per-named sub-groups
    # ----------------------------------------------------------------

    # Load existing collection data (component_properties, embedded instances, etc.)
    abs_main_collection = os.path.join(abs_scenes, f"{s.collection_name}.collection")
    preserved_data = {}
    if os.path.isfile(abs_main_collection):
        try:
            with open(abs_main_collection, "r", encoding="utf-8") as f:
                preserved_data = parse_existing_collection(f.read())
        except Exception as e:
            print(f"[Reforge][WARN] Failed to read existing collection for preserving properties: {e}")

    preserved_comp_props = preserved_data.get("instance_comp_props", {})

    # Discover all group names
    all_group_names: set[str] = set()
    for proto, objs in groups.items():
        for obj in objs:
            grp_name = obj_group[id(obj)]
            if grp_name:
                all_group_names.add(grp_name)

    # Discover group centers if specified (via group_center / defold_group_center custom prop)
    group_centers = {}
    for obj in context.scene.objects:
        if s.export_visible_only and not is_object_visible(obj, view_layer):
            continue
        raw_grp = get_prop(obj, "defold_group")
        if raw_grp is None:
            raw_grp = get_prop(obj, "defold_collection")
        grp_name = (str(raw_grp).strip() if raw_grp is not None else "")
        if not grp_name:
            continue
        is_center = bool(get_prop(obj, "defold_group_center")) or bool(get_prop(obj, "group_center"))
        if is_center and grp_name not in group_centers:
            group_centers[grp_name] = obj

    group_center_rigids = {}
    group_transforms = {}
    for grp_name, center_obj in group_centers.items():
        mw_center = center_obj.matrix_world.copy()
        loc = mw_center.to_translation()
        rot = mw_center.to_quaternion()
        m_rigid = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
        group_center_rigids[grp_name] = m_rigid
        pos, quat, _ = matrix_to_defold_trs(m_rigid)
        group_transforms[grp_name] = {
            "pos": pos,
            "quat": quat,
            "scale": (1.0, 1.0, 1.0),
        }

    # Build instance lists
    main_instances_by_proto = {}
    sub_instances: dict[str, list] = {grp_name: [] for grp_name in all_group_names}
    counters = {p: 0 for p in groups.keys()}

    for proto, objs in groups.items():
        for obj in objs:
            counters[proto] += 1
            inst_id = f"{proto}_{counters[proto]:03d}"
            grp_name = obj_group[id(obj)]

            if grp_name and grp_name in group_center_rigids:
                m_rigid = group_center_rigids[grp_name]
                m_local = m_rigid.inverted() @ obj.matrix_world
                pos, quat, scale = matrix_to_defold_trs(m_local)
            else:
                pos, quat, scale = to_defold_trs(obj)

            inst_data = {
                "id": inst_id,
                "prototype": proto_to_go[proto],
                "pos": pos,
                "quat": quat,
                "scale": scale,
                "component_properties": preserved_comp_props.get(inst_id, []),
            }

            if grp_name:
                sub_instances[grp_name].append(inst_data)
            else:
                main_instances_by_proto.setdefault(proto, []).append(inst_data)

    # Write single .collection with sub-collection groups embedded inside
    protos_sorted = sorted(p for p in groups.keys() if p in main_instances_by_proto)
    collection_text = make_collection_text_grouped_embedded(
        s.collection_name,
        protos_sorted,
        main_instances_by_proto,
        sub_collections=sub_instances,
        preserved_data=preserved_data,
        group_transforms=group_transforms,
    )
    safe_remove_file(abs_main_collection)
    write_text_file(abs_main_collection, collection_text)

    return abs_main_collection
