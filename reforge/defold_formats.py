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


def extract_instance_component_properties(collection_text: str) -> dict:
    """
    Parse existing .collection text and return a dict mapping:
      instance_id -> list of raw '  component_properties { ... }\\n' text blocks
    """
    result = {}
    depth = 0
    in_instance = False
    inst_id = None
    comp_blocks = []
    current_comp_lines = None
    comp_start_depth = 0

    for line in collection_text.splitlines(keepends=True):
        stripped = line.strip()
        delta = _brace_delta(line)

        if depth == 0 and not in_instance:
            if stripped.startswith("instances") and stripped.endswith("{") and delta == 1:
                in_instance = True
                inst_id = None
                comp_blocks = []
                current_comp_lines = None
            depth += delta
            continue

        if in_instance:
            if current_comp_lines is not None:
                current_comp_lines.append(line)
                depth += delta
                if depth <= comp_start_depth:
                    comp_blocks.append("".join(current_comp_lines))
                    current_comp_lines = None
                continue

            if depth == 1:
                if stripped.startswith("id:"):
                    parts = stripped.split('"', 2)
                    if len(parts) >= 2:
                        inst_id = parts[1]
                elif stripped.startswith("component_properties") and stripped.endswith("{") and delta == 1:
                    comp_start_depth = depth
                    current_comp_lines = [line]
                    depth += delta
                    continue

            depth += delta
            if depth <= 0:
                if inst_id and comp_blocks:
                    result[inst_id] = comp_blocks
                in_instance = False
                inst_id = None
                comp_blocks = []
                current_comp_lines = None
                depth = 0
        else:
            depth += delta
            if depth < 0:
                depth = 0

    return result


def make_collection_text_grouped_embedded(collection_name: str, protos_sorted: list, instances_by_proto: dict) -> str:
    parts = [f'name: "{collection_name}"\n']

    for proto in protos_sorted:
        for inst in instances_by_proto.get(proto, []):
            px, py, pz = inst["pos"]
            qx, qy, qz, qw = inst["quat"]
            sx, sy, sz = inst["scale"]

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

    parts.append("scale_along_z: 0\n")

    parts.append("embedded_instances {\n")
    parts.append('  id: "root"\n')
    for proto in protos_sorted:
        parts.append(f'  children: "{proto}"\n')
    parts.append('  data: ""\n')
    parts.append("}\n")

    for proto in protos_sorted:
        parts.append("embedded_instances {\n")
        parts.append(f'  id: "{proto}"\n')
        for inst in instances_by_proto.get(proto, []):
            parts.append(f'  children: "{inst["id"]}"\n')
        parts.append('  data: ""\n')
        parts.append("}\n")

    return "".join(parts)