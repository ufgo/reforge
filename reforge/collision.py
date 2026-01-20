import bpy
import bmesh
from mathutils import Matrix

AXIS_CONVERT = Matrix((
    (1, 0, 0, 0),
    (0, 0, 1, 0),
    (0, -1, 0, 0),
    (0, 0, 0, 1),
))

DEFAULT_COLLISION_FRICTION = 0.1
DEFAULT_COLLISION_RESTITUTION = 0.5

def export_convex_hull_points(obj: bpy.types.Object, filepath: str) -> None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)

    mesh = None
    try:
        mesh = obj_eval.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(mesh)

        if not bm.verts:
            bm.free()
            return

        bmesh.ops.convex_hull(bm, input=bm.verts)

        rs = obj.matrix_world.to_3x3()
        axis_rs = AXIS_CONVERT.to_3x3()

        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            f.write("shape_type: TYPE_HULL\n")
            for v in bm.verts:
                p = rs @ v.co
                p = axis_rs @ p
                f.write(f"data: {p.x}\n")
                f.write(f"data: {p.y}\n")
                f.write(f"data: {p.z}\n")

        bm.free()
    finally:
        if mesh is not None:
            obj_eval.to_mesh_clear()

def make_collisionobject_text(convexshape_project_path: str, group: str, mask: str) -> str:
    group = group or "default"
    mask = mask or "default"
    return (
        f'collision_shape: "{convexshape_project_path}"\n'
        f"type: COLLISION_OBJECT_TYPE_STATIC\n"
        f"mass: 0.0\n"
        f"friction: {DEFAULT_COLLISION_FRICTION:.3f}\n"
        f"restitution: {DEFAULT_COLLISION_RESTITUTION:.3f}\n"
        f'group: "{group}"\n'
        f'mask: "{mask}"\n'
    )