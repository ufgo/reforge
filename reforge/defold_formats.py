from typing import List, Tuple, Optional

def make_model_text_multi(mesh_path_project: str, model_name: str, materials_blocks: List[Tuple[str, str, str]]) -> str:
    parts = [
        f'mesh: "{mesh_path_project}"\n',
        f'name: "{model_name}"\n'
    ]
    for mat_name, defold_mat_path, defold_tex_path in materials_blocks:
        parts.append(
            "materials {\n"
            f'  name: "{mat_name}"\n'
            f'  material: "{defold_mat_path}"\n'
            "  textures {\n"
            '    sampler: "tex0"\n'
            f'    texture: "{defold_tex_path}"\n'
            "  }\n"
            "}\n"
        )
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