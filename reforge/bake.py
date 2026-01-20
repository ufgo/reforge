# reforge/bake.py
import bpy
import os


# ---------------------------
# Helpers
# ---------------------------

def _ensure_cycles_engine(scene: bpy.types.Scene):
    """Bake works through Cycles. Temporarily switch engine to CYCLES and return previous."""
    prev_engine = scene.render.engine
    if prev_engine != "CYCLES":
        scene.render.engine = "CYCLES"
    return prev_engine


def _activate_first_uv(obj: bpy.types.Object) -> bool:
    """Ensure mesh has UVs and first UV is active (and render-active if available)."""
    uv_layers = getattr(obj.data, "uv_layers", None)
    if not uv_layers or len(uv_layers) == 0:
        return False
    try:
        obj.data.uv_layers.active_index = 0
        obj.data.uv_layers.active = obj.data.uv_layers[0]
        if hasattr(obj.data.uv_layers[0], "active_render"):
            obj.data.uv_layers[0].active_render = True
    except Exception:
        pass
    return True


def _set_active_object(context, obj: bpy.types.Object):
    """Select only this object and set it active."""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _set_active_material_slot(obj: bpy.types.Object, mat: bpy.types.Material) -> bool:
    """Make given material active on object material slots (important for baking)."""
    mat_index = None
    for i, slot in enumerate(obj.material_slots):
        if slot.material == mat:
            mat_index = i
            break
    if mat_index is None:
        return False
    obj.active_material_index = mat_index
    obj.active_material = mat
    return True


def _find_output_node(nt: bpy.types.NodeTree):
    for n in nt.nodes:
        if n.type == "OUTPUT_MATERIAL":
            return n
    return None


def _find_principled_node(nt: bpy.types.NodeTree):
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def _first_link_source_socket(input_socket):
    """Return from_socket of first link feeding this INPUT socket."""
    try:
        if input_socket and input_socket.is_linked and input_socket.links:
            return input_socket.links[0].from_socket
    except Exception:
        pass
    return None


def _walk_upstream_find_color_source(from_socket, max_nodes=250):
    """
    Try to find a good COLOR OUTPUT socket by walking upstream through node links.
    Returns an OUTPUT socket suitable to link into Emission Color, or None.
    """
    if from_socket is None:
        return None

    stack = []
    visited = set()

    def push_node(node):
        if node is None:
            return
        ptr = node.as_pointer()
        if ptr in visited:
            return
        visited.add(ptr)
        stack.append(node)

    # seed from socket's node
    node0 = getattr(from_socket, "node", None)
    if node0 is not None:
        push_node(node0)

    steps = 0
    while stack and steps < max_nodes:
        steps += 1
        node = stack.pop()

        # Ideal: Image Texture
        if node.type == "TEX_IMAGE":
            out = node.outputs.get("Color") or (node.outputs[0] if node.outputs else None)
            if out and getattr(out, "is_output", False):
                return out

        # Common color providers
        if node.type in {"RGB", "VERTEX_COLOR", "ATTRIBUTE"}:
            out = node.outputs.get("Color") or (node.outputs[0] if node.outputs else None)
            if out and getattr(out, "is_output", False):
                return out

        # Walk linked inputs
        for inp in getattr(node, "inputs", []):
            src = _first_link_source_socket(inp)
            if src is not None:
                push_node(getattr(src, "node", None))

    return None


def _setup_diffuse_color_bake(scene: bpy.types.Scene):
    """
    Configure Cycles bake settings to bake DIFFUSE COLOR only.
    Returns previous values to restore.
    """
    b = scene.render.bake
    prev = {
        "use_pass_direct": getattr(b, "use_pass_direct", None),
        "use_pass_indirect": getattr(b, "use_pass_indirect", None),
        "use_pass_color": getattr(b, "use_pass_color", None),
    }
    try:
        b.use_pass_direct = False
        b.use_pass_indirect = False
        b.use_pass_color = True
    except Exception:
        pass
    return prev


def _restore_diffuse_color_bake(scene: bpy.types.Scene, prev: dict):
    b = scene.render.bake
    try:
        if prev.get("use_pass_direct") is not None:
            b.use_pass_direct = prev["use_pass_direct"]
        if prev.get("use_pass_indirect") is not None:
            b.use_pass_indirect = prev["use_pass_indirect"]
        if prev.get("use_pass_color") is not None:
            b.use_pass_color = prev["use_pass_color"]
    except Exception:
        pass


def _save_solid_png(out_abs_path: str, rgba, size: int = 1) -> bool:
    """Create and save a solid-color PNG (size x size)."""
    os.makedirs(os.path.dirname(out_abs_path), exist_ok=True)

    name = os.path.splitext(os.path.basename(out_abs_path))[0]
    img = bpy.data.images.new(name, width=int(size), height=int(size), alpha=True, float_buffer=False)

    r, g, b, a = rgba
    pixels = [float(r), float(g), float(b), float(a)] * (int(size) * int(size))
    img.pixels = pixels

    img.filepath_raw = out_abs_path
    img.file_format = "PNG"
    img.save()

    try:
        bpy.data.images.remove(img)
    except Exception:
        pass

    return True


# ---------------------------
# Main bake
# ---------------------------

def bake_color_emit_png(
    obj: bpy.types.Object,
    mat: bpy.types.Material,
    out_abs_path: str,
    resolution: int,
    padding: int,
) -> bool:
    """
    Bake FINAL COLOR to PNG.

    Strategy:
      0) If there are NO UVs and we can detect a constant Base Color -> write 1x1 PNG and return.
      1) Try EMIT override (best for Ucupaint / layered graphs):
          - Feed Emission Color from:
              a) Principled Base Color source (link source socket), or constant Base Color
              b) Else: walk upstream from Material Output Surface shader and try to find an Image Texture / RGB / Vertex Color
      2) If EMIT override cannot find a reasonable color input, fallback to DIFFUSE bake with COLOR-only pass.

    Returns True on success.
    """
    if not obj or obj.type != "MESH":
        print("[Reforge][Bake] Not a MESH object")
        return False
    if not mat or not mat.use_nodes or not mat.node_tree:
        print("[Reforge][Bake] Material missing or does not use nodes")
        return False

    # Try to detect constant base color early (for no-UV fallback)
    nt = mat.node_tree
    principled = _find_principled_node(nt)
    early_constant_rgba = None
    if principled is not None:
        bc = principled.inputs.get("Base Color") or principled.inputs.get("Color")
        if bc is not None and (not bc.is_linked or not bc.links):
            try:
                early_constant_rgba = tuple(bc.default_value)  # RGBA
            except Exception:
                early_constant_rgba = None

    # UV check
    uv_layers = getattr(obj.data, "uv_layers", None)
    has_uv = bool(uv_layers and len(uv_layers) > 0)

    # If no UVs but we have constant color -> 1x1 PNG fallback
    if not has_uv and early_constant_rgba is not None:
        print("[Reforge][Bake] No UVs: saving solid 1x1 PNG instead of baking.")
        return _save_solid_png(out_abs_path, early_constant_rgba, size=1)

    # If we want to bake but no UVs and no constant -> cannot bake
    if not has_uv:
        print("[Reforge][Bake] No UVs and color is not constant -> cannot bake.")
        return False

    # Activate first UV
    if not _activate_first_uv(obj):
        print("[Reforge][Bake] UV activate failed")
        return False

    os.makedirs(os.path.dirname(out_abs_path), exist_ok=True)

    ctx = bpy.context
    scene = ctx.scene
    prev_engine = _ensure_cycles_engine(scene)

    # Ensure correct active object/material
    _set_active_object(ctx, obj)
    if not _set_active_material_slot(obj, mat):
        print(f"[Reforge][Bake] Material '{mat.name}' not found in object slots")
        try:
            scene.render.engine = prev_engine
        except Exception:
            pass
        return False

    # Create image datablock (target)
    img_name = os.path.splitext(os.path.basename(out_abs_path))[0]
    img = bpy.data.images.new(
        img_name,
        width=int(resolution),
        height=int(resolution),
        alpha=True,
        float_buffer=False,
    )

    nodes = nt.nodes
    links = nt.links

    out_node = _find_output_node(nt)
    if out_node is None:
        out_node = nodes.new("ShaderNodeOutputMaterial")
        out_node.location = (500, 0)

    surface_input = out_node.inputs.get("Surface")
    if surface_input is None:
        print("[Reforge][Bake] Material Output has no Surface input")
        try:
            bpy.data.images.remove(img)
        except Exception:
            pass
        try:
            scene.render.engine = prev_engine
        except Exception:
            pass
        return False

    # Save original surface links as socket pairs (robust restore)
    original_surface_pairs = [(l.from_socket, l.to_socket) for l in surface_input.links]

    # Disconnect surface
    for l in list(surface_input.links):
        try:
            links.remove(l)
        except Exception:
            pass

    # Temp nodes
    emit_node = nodes.new("ShaderNodeEmission")
    emit_node.location = (200, 0)

    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.location = (-400, -200)
    tex_node.image = img

    # Decide emission color source
    from_color_socket = None
    constant_rgba = early_constant_rgba

    # A) Prefer Principled Base Color (linked)
    if principled is not None and constant_rgba is None:
        bc = principled.inputs.get("Base Color") or principled.inputs.get("Color")
        if bc is not None and bc.is_linked and bc.links:
            try:
                # bc is INPUT -> take the OUTPUT feeding it
                from_color_socket = bc.links[0].from_socket
            except Exception:
                from_color_socket = None

    # B) If no principled/color found, try graph traversal from original Surface source
    if constant_rgba is None and from_color_socket is None:
        surf_from = original_surface_pairs[0][0] if original_surface_pairs else None
        color_candidate = _walk_upstream_find_color_source(surf_from)
        if color_candidate is not None:
            from_color_socket = color_candidate

    # Apply to emission
    if constant_rgba is not None:
        emit_node.inputs["Color"].default_value = constant_rgba
    elif from_color_socket is not None:
        try:
            links.new(from_color_socket, emit_node.inputs["Color"])
        except Exception as e:
            print("[Reforge][Bake] Failed to link color into emission:", e)
            from_color_socket = None  # force fallback
    else:
        pass  # force fallback

    # Link emission to output surface
    can_emit = (constant_rgba is not None) or (from_color_socket is not None)
    if can_emit:
        try:
            links.new(emit_node.outputs["Emission"], surface_input)
        except Exception as e:
            print("[Reforge][Bake] Failed to link emission to output:", e)
            can_emit = False

    # Make image node ACTIVE for baking (critical)
    for n in nodes:
        n.select = False
    tex_node.select = True
    nodes.active = tex_node

    try:
        ctx.view_layer.update()
    except Exception:
        pass

    ok = False
    prev_bake = None

    try:
        if can_emit:
            print(f"[Reforge][Bake] EMIT bake: obj='{obj.name}', mat='{mat.name}', res={resolution}, pad={padding}")
            bpy.ops.object.bake(type='EMIT', margin=int(padding), use_clear=True)
            ok = True
        else:
            prev_bake = _setup_diffuse_color_bake(scene)
            print(f"[Reforge][Bake] DIFFUSE(COLOR) fallback: obj='{obj.name}', mat='{mat.name}', res={resolution}, pad={padding}")
            bpy.ops.object.bake(type='DIFFUSE', margin=int(padding), use_clear=True)
            ok = True

        if ok:
            img.filepath_raw = out_abs_path
            img.file_format = "PNG"
            img.save()
            print(f"[Reforge][Bake] Saved: {out_abs_path}")

    except Exception as e:
        print(f"[Reforge][Bake][ERROR] Bake failed: {e}")
        ok = False

    finally:
        # Restore bake settings if changed
        if prev_bake is not None:
            _restore_diffuse_color_bake(scene, prev_bake)

        # Restore Surface links
        try:
            for l in list(surface_input.links):
                links.remove(l)
        except Exception:
            pass

        for from_sock, to_sock in original_surface_pairs:
            try:
                links.new(from_sock, to_sock)
            except Exception:
                pass

        # Remove temp nodes
        for n in (emit_node, tex_node):
            try:
                nodes.remove(n)
            except Exception:
                pass

        # Restore render engine
        try:
            scene.render.engine = prev_engine
        except Exception:
            pass

        # Remove temp image datablock (file already saved)
        try:
            bpy.data.images.remove(img)
        except Exception:
            pass

    return ok