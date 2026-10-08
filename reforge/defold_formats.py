from typing import List, Tuple, Optional

def make_model_text_multi(mesh_path_project: str, model_name: str, materials_blocks: List[Tuple[str, str, dict]]) -> str:
    parts = [
        f'mesh: "{mesh_path_project}"\n',
        f'name: "{model_name}"\n'
    ]
    for mat_name, defold_mat_path, samplers_dict in materials_blocks:
        parts.append(
            "materials {\n"
            f'  name: "{mat_name}"\n'
            f'  material: "{defold_mat_path}"\n'
        )
        for sampler, tex_path in samplers_dict.items():
            parts.append(
                "  textures {\n"
                f'    sampler: "{sampler}"\n'
                f'    texture: "{tex_path}"\n'
                "  }\n"
            )
        parts.append("}\n")
    return "".join(parts)


def make_go_ref_model_text(model_path_project: str, collisionobject_project_path: Optional[str]):
    if collisionobject_project_path:
        return f'''components {{
  id: "model"
  component: "{model_path_project}"
}}
components {{
  id: "collision"
  component: "{collisionobject_project_path}"
}}
'''
    return f'''components {{
  id: "model"
  component: "{model_path_project}"
}}
'''

def _brace_delta(line: str) -> int:
    delta = 0
    in_quotes = False
    escape = False
    for ch in line:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_quotes = not in_quotes
            continue
        if not in_quotes:
            if ch == "{":
                delta += 1
            elif ch == "}":
                delta -= 1
    return delta


def parse_existing_collection(collection_text: str) -> dict:
    """
    Parse an existing .collection text and return:
      {
        "scale_along_z": int,
        "instance_comp_props": dict[inst_id -> list[str]],
        "old_instance_ids": set[str],
        "embedded_instances": dict[emb_id -> dict],
        "collection_instances": list[str],
      }
    """
    scale_along_z = 0
    instance_comp_props = {}
    old_instance_ids = set()
    embedded_instances = {}
    collection_instances = []

    depth = 0
    in_block_type = None
    current_block_lines = []

    for line in collection_text.splitlines(keepends=True):
        stripped = line.strip()
        delta = _brace_delta(line)

        if depth == 0:
            if stripped.startswith("scale_along_z:"):
                try:
                    scale_along_z = int(stripped.split(":", 1)[1].strip())
                except Exception:
                    pass
                continue

            if stripped.startswith("instances") and stripped.endswith("{") and delta == 1:
                in_block_type = "instances"
                depth = 1
                current_block_lines = [line]
                continue
            elif stripped.startswith("embedded_instances") and stripped.endswith("{") and delta == 1:
                in_block_type = "embedded_instances"
                depth = 1
                current_block_lines = [line]
                continue
            elif stripped.startswith("collection_instances") and stripped.endswith("{") and delta == 1:
                in_block_type = "collection_instances"
                depth = 1
                current_block_lines = [line]
                continue
            else:
                continue

        current_block_lines.append(line)
        depth += delta

        if depth <= 0:
            if in_block_type == "instances":
                inst_id = None
                comp_props = []
                cp_lines = None
                cp_depth = 0
                inner_depth = 0
                for l in current_block_lines[1:-1]:
                    st = l.strip()
                    d = _brace_delta(l)
                    if cp_lines is not None:
                        cp_lines.append(l)
                        inner_depth += d
                        if inner_depth <= cp_depth:
                            comp_props.append("".join(cp_lines))
                            cp_lines = None
                        continue
                    if inner_depth == 0:
                        if st.startswith("id:"):
                            parts = st.split('"', 2)
                            if len(parts) >= 2:
                                inst_id = parts[1]
                        elif st.startswith("component_properties") and st.endswith("{") and d == 1:
                            cp_depth = inner_depth
                            cp_lines = [l]
                            inner_depth += d
                            continue
                    inner_depth += d

                if inst_id:
                    old_instance_ids.add(inst_id)
                    if comp_props:
                        instance_comp_props[inst_id] = comp_props

            elif in_block_type == "embedded_instances":
                emb_id = None
                children = []
                other_lines = []
                for l in current_block_lines[1:-1]:
                    st = l.strip()
                    if st.startswith("id:"):
                        parts = st.split('"', 2)
                        if len(parts) >= 2 and emb_id is None:
                            emb_id = parts[1]
                            continue
                    elif st.startswith("children:"):
                        parts = st.split('"', 2)
                        if len(parts) >= 2:
                            children.append(parts[1])
                            continue
                    other_lines.append(l)

                if emb_id:
                    embedded_instances[emb_id] = {
                        "children": children,
                        "other_lines": other_lines,
                    }

            elif in_block_type == "collection_instances":
                collection_instances.append("".join(current_block_lines))

            in_block_type = None
            current_block_lines = []
            depth = 0

    return {
        "scale_along_z": scale_along_z,
        "instance_comp_props": instance_comp_props,
        "old_instance_ids": old_instance_ids,
        "embedded_instances": embedded_instances,
        "collection_instances": collection_instances,
    }


def extract_instance_component_properties(collection_text: str) -> dict:
    """
    Parse existing .collection text and return a dict mapping:
      instance_id -> list of raw '  component_properties { ... }\\n' text blocks
    """
    parsed = parse_existing_collection(collection_text)
    return parsed.get("instance_comp_props", {})


def _strip_transform_lines(lines: list) -> list:
    """
    Remove position, rotation, and scale blocks from raw embedded instance lines.
    """
    filtered = []
    depth = 0
    in_transform = False
    for line in lines:
        st = line.strip()
        d = _brace_delta(line)
        if depth == 0 and not in_transform:
            if (st.startswith("position") or st.startswith("rotation") or
                st.startswith("scale3") or st.startswith("scale")) and st.endswith("{") and d == 1:
                in_transform = True
                depth = 1
                continue
            filtered.append(line)
            continue
        if in_transform:
            depth += d
            if depth <= 0:
                in_transform = False
                depth = 0
            continue
        filtered.append(line)
    return filtered


def _format_embedded_instance(
    emb_id: str,
    children: list,
    preserved_payload: Optional[list] = None,
    extra_children: Optional[list] = None,
    transform: Optional[dict] = None,
) -> list:
    """
    Format a single embedded_instances {} block preserving components / script data / transforms.
    If transform is provided (e.g. from group_center), it overrides any preserved transform.
    """
    parts = ["embedded_instances {\n", f'  id: "{emb_id}"\n']

    seen = set()
    for child in children:
        if child not in seen:
            seen.add(child)
            parts.append(f'  children: "{child}"\n')
    if extra_children:
        for child in extra_children:
            if child not in seen:
                seen.add(child)
                parts.append(f'  children: "{child}"\n')

    payload_to_use = preserved_payload
    if transform and payload_to_use:
        payload_to_use = _strip_transform_lines(payload_to_use)

    if payload_to_use:
        has_data = any(line.strip().startswith("data:") for line in payload_to_use)
        if not has_data:
            parts.append('  data: ""\n')
        for line in payload_to_use:
            parts.append(line if line.endswith("\n") else line + "\n")
    else:
        parts.append('  data: ""\n')

    if transform:
        px, py, pz = transform.get("pos", (0.0, 0.0, 0.0))
        qx, qy, qz, qw = transform.get("quat", (0.0, 0.0, 0.0, 1.0))
        sx, sy, sz = transform.get("scale", (1.0, 1.0, 1.0))

        if abs(px) > 1e-9 or abs(py) > 1e-9 or abs(pz) > 1e-9:
            parts.append("  position {\n")
            parts.append(f"    x: {px:.6f}\n")
            parts.append(f"    y: {py:.6f}\n")
            parts.append(f"    z: {pz:.6f}\n")
            parts.append("  }\n")

        if abs(qx) > 1e-9 or abs(qy) > 1e-9 or abs(qz) > 1e-9 or abs(qw - 1.0) > 1e-9:
            parts.append("  rotation {\n")
            parts.append(f"    x: {qx:.6f}\n")
            parts.append(f"    y: {qy:.6f}\n")
            parts.append(f"    z: {qz:.6f}\n")
            parts.append(f"    w: {qw:.6f}\n")
            parts.append("  }\n")

        if abs(sx - 1.0) > 1e-9 or abs(sy - 1.0) > 1e-9 or abs(sz - 1.0) > 1e-9:
            parts.append("  scale3 {\n")
            parts.append(f"    x: {sx:.6f}\n")
            parts.append(f"    y: {sy:.6f}\n")
            parts.append(f"    z: {sz:.6f}\n")
            parts.append("  }\n")

    parts.append("}\n")
    return parts


def make_collection_text_grouped_embedded(
    collection_name: str,
    protos_sorted: list,
    instances_by_proto: dict,
    sub_collections: Optional[dict] = None,
    preserved_data: Optional[dict] = None,
    group_transforms: Optional[dict] = None,
) -> str:
    """
    Generate a .collection text.

    Main objects (no defold_group):
        root → <proto> → instances

    Named sub-groups (defold_group="col"):
        root → col → instances   (flat, no intermediate proto layer)

    Preserves existing embedded components (scripts, models, etc.),
    component_properties, and transforms on groups, as well as custom
    embedded instances and collection_instances.
    group_transforms: optional dict { col_name: {"pos": ..., "quat": ..., "scale": ...} }
    """
    sub_collections = sub_collections or {}
    preserved_data = preserved_data or {}
    group_transforms = group_transforms or {}
    scale_along_z = preserved_data.get("scale_along_z", 0)
    preserved_embedded = preserved_data.get("embedded_instances", {})
    old_instance_ids = preserved_data.get("old_instance_ids", set())
    collection_instances = preserved_data.get("collection_instances", [])

    parts = [f'name: "{collection_name}"\n']

    # ---- instances: main (grouped by proto) ----
    for proto in protos_sorted:
        for inst in instances_by_proto.get(proto, []):
            parts.extend(_instance_block(inst))

    # ---- instances: sub-collection objects (flat) ----
    for col_name in sorted(sub_collections.keys()):
        for inst in sub_collections[col_name]:
            parts.extend(_instance_block(inst))

    parts.append(f"scale_along_z: {scale_along_z}\n")

    managed_ids = {"root"} | set(protos_sorted) | set(sub_collections.keys())

    def get_extra_children(emb_id, current_children):
        existing = preserved_embedded.get(emb_id, {}).get("children", [])
        curr_set = set(current_children)
        extra = []
        for c in existing:
            if c not in curr_set and c not in old_instance_ids:
                if emb_id == "root" and c in preserved_embedded:
                    c_info = preserved_embedded[c]
                    c_children = c_info.get("children", [])
                    has_comp = any("components" in l for l in c_info.get("other_lines", []))
                    if c_children and all(x in old_instance_ids for x in c_children) and not has_comp:
                        continue
                extra.append(c)
        return extra

    # ---- embedded root ----
    root_primary_children = list(protos_sorted) + sorted(sub_collections.keys())
    root_payload = preserved_embedded.get("root", {}).get("other_lines")
    root_extra = get_extra_children("root", root_primary_children)
    parts.extend(_format_embedded_instance("root", root_primary_children, root_payload, root_extra))

    # ---- embedded proto groups (main objects) ----
    for proto in protos_sorted:
        proto_children = [inst["id"] for inst in instances_by_proto.get(proto, [])]
        proto_payload = preserved_embedded.get(proto, {}).get("other_lines")
        proto_extra = get_extra_children(proto, proto_children)
        parts.extend(_format_embedded_instance(proto, proto_children, proto_payload, proto_extra))

    # ---- embedded sub-collection groups ----
    for col_name in sorted(sub_collections.keys()):
        col_children = [inst["id"] for inst in sub_collections[col_name]]
        col_payload = preserved_embedded.get(col_name, {}).get("other_lines")
        col_extra = get_extra_children(col_name, col_children)
        col_tf = group_transforms.get(col_name)
        parts.extend(_format_embedded_instance(col_name, col_children, col_payload, col_extra, transform=col_tf))

    # ---- other custom embedded instances from Defold ----
    for emb_id, emb_info in preserved_embedded.items():
        if emb_id in managed_ids:
            continue
        ch = emb_info.get("children", [])
        other_lines = emb_info.get("other_lines", [])
        has_components = any("components" in l for l in other_lines)
        if ch and all(c in old_instance_ids for c in ch) and not has_components:
            continue
        remaining_children = [c for c in ch if c not in old_instance_ids]
        parts.extend(_format_embedded_instance(emb_id, remaining_children, other_lines))

    # ---- collection instances ----
    for ci in collection_instances:
        if not ci.endswith("\n"):
            ci += "\n"
        parts.append(ci)

    return "".join(parts)


def _instance_block(inst: dict) -> list:
    """Return list of text parts for one instances {} block."""
    px, py, pz = inst["pos"]
    qx, qy, qz, qw = inst["quat"]
    sx, sy, sz = inst["scale"]

    parts = []
    parts.append("instances {\n")
    parts.append(f'  id: "{inst["id"]}"\n')
    parts.append(f'  prototype: "{inst["prototype"]}"\n')

    if abs(px) > 1e-9 or abs(py) > 1e-9 or abs(pz) > 1e-9:
        parts.append("  position {\n")
        parts.append(f"    x: {px:.6f}\n")
        parts.append(f"    y: {py:.6f}\n")
        parts.append(f"    z: {pz:.6f}\n")
        parts.append("  }\n")

    if abs(qx) > 1e-9 or abs(qy) > 1e-9 or abs(qz) > 1e-9 or abs(qw - 1.0) > 1e-9:
        parts.append("  rotation {\n")
        parts.append(f"    x: {qx:.6f}\n")
        parts.append(f"    y: {qy:.6f}\n")
        parts.append(f"    z: {qz:.6f}\n")
        parts.append(f"    w: {qw:.6f}\n")
        parts.append("  }\n")

    for cp_block in inst.get("component_properties", []):
        if not cp_block.endswith("\n"):
            cp_block += "\n"
        parts.append(cp_block)

    if abs(sx - 1.0) > 1e-9 or abs(sy - 1.0) > 1e-9 or abs(sz - 1.0) > 1e-9:
        parts.append("  scale3 {\n")
        parts.append(f"    x: {sx:.6f}\n")
        parts.append(f"    y: {sy:.6f}\n")
        parts.append(f"    z: {sz:.6f}\n")
        parts.append("  }\n")

    parts.append("}\n")
    return parts