# Defold Scene Exporter (Blender Add-on)

Blender add-on for exporting scenes into a Defold project as:
- `.glb` meshes
- `.model` files (supports **multiple materials**)
- `.go` prefabs (created once, never overwritten)
- `.collection` scene file (instances grouped under embedded `root`)

Also supports optional **convex collision export** per prototype and **texture export** into your Defold project.

Author: Alexander Bulatov

---

## Features

### Scene export
- Generates a Defold `.collection` with instances matching Blender transforms.
- Instances are grouped like:
  - `embedded_instances { id: "root" children: "<prototype>" ... }`
  - one embedded group per prototype that contains all instances of that prototype.

### Prototype export (no scene regeneration)
- Export only assets (GLB + .model + convex collision files) without touching the `.collection`.
- Useful when you updated a mesh/materials/textures and want to refresh only one prototype.

### Multi-material `.model`
- For each prototype, the exporter creates a `.model` file with **one `materials {}` block per Blender material slot** (unique materials, in slot order).
- Material matching uses the **Blender material name** (must match the material name in the exported GLB).

### Material-driven Defold paths (stored on Blender Materials)
Add custom properties on Blender **Material** datablocks:
- `defold_material` (string) — Defold `.material` path  
- `defold_texture` (string) — Defold texture path (optional)

If these are not set:
- `defold_material` falls back to **Default Material** from the add-on UI
- `defold_texture` is found from the material nodes:
  - `Principled BSDF -> Base Color -> Image Texture`
- if no image is found, a fallback built-in Defold logo texture is used.

### Texture export
When enabled, the add-on copies/saves textures into:
- `assets/textures/`

Textures are **overwritten** (no `_1`, `_2` duplicates).

### Convex collision export
Per-prototype collision export is controlled via **Object** custom properties:
- `defold_collision` (bool) — enable convex collision export
- `collision_group` (string, default: `"default"`)
- `collision_mask` (string, default: `"default"`)

For prototypes with `defold_collision = true`, exporter generates:
- `assets/collisions/<proto>.convexshape`
- `assets/collisions/<proto>.collisionobject`

Collision objects are created as **STATIC**:
```text
type: COLLISION_OBJECT_TYPE_STATIC
mass: 0.0
friction: 0.1
restitution: 0.5
```

# Safe Clear (with Confirmation)

The add-on can remove only exporter-created custom properties from:

- Objects
- Materials used by those objects

Keys removed:

- **Object**: `defold_prototype`, `defold_collision`, `collision_group`, `collision_mask`
- **Material**: `defold_material`, `defold_texture`

Each Clear action uses Blender’s confirmation popup.

# Installation

1. Save the add-on script as a single `.py` file (example: `defold_scene_exporter.py`).

2. In Blender:

   - Edit → Preferences → Add-ons
   - Install… → select the `.py` file
   - Enable the add-on checkbox

Panel location:

- 3D Viewport → Sidebar (N) → Defold Export

# Quick Start

## 1) Set Defold Project Path

In the add-on panel:

- Defold Project Root → select your Defold project folder

Default folders (editable):

- `assets/models`
- `assets/models` (for `.model`)
- `assets/prefabs`
- `assets/scenes`
- `assets/textures`
- `assets/collisions`

## 2) Tag Objects with `defold_prototype`

The exporter only includes objects that have custom property:

- `defold_prototype`

Fast way:

- Use Tools section:
  - 1) Set Props (Selected)
  - 2) Set Props (Visible)
  - 3) Set Props (All)

This creates `defold_prototype` using the object name.

## 3) Export a Scene

- Set Collection Name
- Press Generate Scene (`.collection`)

## 4) Export Only One Prototype (No Scene Regen)

Select the prototype’s mesh object and press:

- Export Selected Prototype (No Scene)

# Setting Up Multiple Materials

How to assign Defold material/texture per Blender material

Select your material → Material Properties → Custom Properties:

Optional:

- `defold_material` = `/assets/materials/my.material`
- `defold_texture` = `/assets/textures/my.png`

If you don’t set them:

- `defold_material` uses UI Default Material
- `defold_texture` is taken from Principled BSDF -> Base Color image node

# Collision Setup

On the Blender Object (not Material):

- `defold_collision` = `True`
- `collision_group` = `default` (or your group)
- `collision_mask` = `default` (or your mask)

You can set these quickly using the Tools section in the panel.

# Notes / Behavior

## `.go` Prefabs Are NOT Overwritten

- If a `.go` file already exists, exporter will not rewrite it.
- This is intentional to preserve manual edits (collision setup, scripts, etc).

## Files That ARE Overwritten

Per export, for each prototype:

- `<proto>.glb`
- `<proto>.model`
- `<proto>.convexshape` (if enabled)
- `<proto>.collisionobject` (if enabled)
- the `.collection` file (when generating scene)

## Export Visible Only

If enabled, only objects that are visible in the viewport are exported.

# Troubleshooting

## “No MESH objects with ‘defold_prototype’…”

- Ensure objects are Meshes
- Ensure `defold_prototype` exists as a custom property
- Check Export Visible Only and visibility of objects

## Textures Create Duplicates Like `_1`, `_2`

This add-on overwrites by filename. If you still see duplicates:

- Make sure your Defold textures folder isn’t read-only
- Ensure images have stable filenames (not generated temporary names)

## Collision Seems Offset

- Convex hull export uses rotation+scale but not translation (correct for Defold local collision space).
- Avoid negative scale / mirrored objects.
- Apply transforms in Blender if your object has unusual transforms.


