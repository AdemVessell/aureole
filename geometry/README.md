# Finite gyroid lattice geometry

This folder contains standalone, deterministic geometry assets for the
equation-cinema Unreal scene. It contains no textures, stock meshes, materials,
or project files from the Unreal lane.

The scalar below is a standard trigonometric/nodal gyroid approximation. This
package does not claim an exact minimal surface, physical metal behavior, or a
physics simulation.

## Mathematical definition

The dimensionless gyroid scalar is

```text
g(u,v,w) = sin(u) cos(v) + sin(v) cos(w) + sin(w) cos(u)
```

The solid is the zero isosurface of

```text
F(x,y,z) = max(abs(g(kx,ky,kz)) - 0.16,
               sqrt((x/150)^2 + (y/150)^2 + (z/150)^2) - 1)
```

The inside rule is `F <= 0`. `x,y,z` are centimetres; `u=kx`, `v=ky`, `w=kz`,
`g` and `F` are dimensionless; and `0.16` is the half-width in `g` units. The radius is 150 cm
(nominal diameter 300 cm), the frequency is `k = 1.75 * 2*pi / 300`
radians/cm (1.75 periods across the diameter), and the sheet half-width is
0.16 in `g` units. The spherical clipping surface gives a finite, rounded
volume; marching-cubes triangle vertices are smoothed with area-weighted
vertex normals. The OBJ and FBX are triangle-only and have no texture data.

## Assets

| Asset | Resolution | Vertices | Triangles | Bounds (cm) | Use |
| --- | ---: | ---: | ---: | --- | --- |
| `gyroid_lattice_fine.obj` / `.fbx` | 192³ | 328,572 | 656,980 | ±149.4571 | final high-resolution geometry |
| `gyroid_lattice_300cm.obj` / `.fbx` | 112³ | 110,364 | 220,756 | ±149.4217 | canonical/original control |
| `gyroid_lattice_preview.obj` / `.fbx` | 72³ | 44,646 | 89,384 | ±149.2138 | fast import/preview |

All three meshes pass the closed-manifold audit: 0 boundary edges, 0
non-manifold edges, and 0 degenerate triangles. FBX round-trip through Blender
5.1.2 preserves mesh counts, smooth polygons, origin, and dimensions (fine:
2.9891424 m; original: 2.9884336 m; preview: 2.9842756 m). The FBX conversion
scales the centimetre OBJ by 0.01 and is authored in metres for a clean Unreal
import; the OBJ is kept in centimetres for direct Unreal 1 UU = 1 cm workflows.
The fine mesh is the final geometry variant: it keeps the same equation
parameters and uses the same area-weighted smooth vertex-normal policy at
192³. Its higher sampling density removes the visible low-grid cap stepping in
the first preview. The 112³ mesh remains as a reproducible original control,
not the final render asset.

## Reproduction

From this directory, using the bundled system Python (NumPy + scikit-image):

```sh
python3 -B generate_gyroid.py \
  --resolution 112 --radius-cm 150 --periods-across 1.75 \
  --shell-half-width 0.16 --extent-cm 154 \
  --name gyroid_lattice_300cm
```

Convert the OBJ to FBX with the locally available Blender CLI:

```sh
BLENDER="${BLENDER:-/opt/homebrew/bin/blender}"
"$BLENDER" --background --python export_obj_to_fbx.py -- \
  --obj gyroid_lattice_300cm.obj --fbx gyroid_lattice_300cm.fbx
```

The preview uses the same source and parameters with only
`--resolution 72 --name gyroid_lattice_preview`.

The final high-resolution asset uses:

```sh
python3 -B generate_gyroid.py \
  --resolution 192 --radius-cm 150 --periods-across 1.75 \
  --shell-half-width 0.16 --extent-cm 154 \
  --name gyroid_lattice_fine
BLENDER="${BLENDER:-/opt/homebrew/bin/blender}"
"$BLENDER" --background --python export_obj_to_fbx.py -- \
  --obj gyroid_lattice_fine.obj --fbx gyroid_lattice_fine.fbx
```

The verified local Blender CLI is `/opt/homebrew/bin/blender` (Blender
5.1.2); set `BLENDER` to another Blender 5.x executable when reproducing on a
different machine.

The JSON sidecars preserve the formula, parameters, exact mesh audit, bounds,
runtime versions, and command-line recipe. `generate_gyroid.py` is the sole
geometry source; `export_obj_to_fbx.py` is only a format conversion helper.

## Verification commands

The generation command itself fails on empty, non-finite, out-of-range,
zero-area, boundary-edge, or non-manifold output. For FBX round-trip inspection:

```sh
BLENDER="${BLENDER:-/opt/homebrew/bin/blender}"
"$BLENDER" --background --python-expr \
  'import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath="gyroid_lattice_fine.fbx"); o=[x for x in bpy.context.scene.objects if x.type=="MESH"][0]; print(len(o.data.vertices), len(o.data.polygons), list(o.dimensions))'
```

For the final fine asset, expected round-trip is `328572 656980
[2.9891424, 2.9891424, 2.9891424]` (metres), with all 656,980 polygons
smooth. The original control round-trip is `110364 220756 [2.9884336,
2.9884336, 2.9884336]`.

`gyroid_lattice_fine_audit.json` records the fine-mesh winding audit: positive
signed enclosed volume (`1,463,506.59 cm^3`), zero boundary/non-manifold edges,
and all 656,980 FBX-imported polygons marked smooth. The signed volume and
predominantly outward implicit-field side test confirm the marching-cubes
winding orientation on the main closed component; seam-near side samples are
reported as ambiguous rather than forced. Tiny disconnected 8-face boundary
fragments are preserved as generated rather than silently removed.
