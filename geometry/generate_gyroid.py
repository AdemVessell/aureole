#!/usr/bin/env python3
"""Deterministically generate a finite, solid gyroid-sheet sculpture.

The mesh is the zero isosurface of

    F(x,y,z) = max(abs(g(k*x,k*y,k*z)) - shell_half_width,
                   ||(x,y,z)|| / sphere_radius - 1)

where ``g(a,b,c) = sin(a)cos(b) + sin(b)cos(c) + sin(c)cos(a)``.
Coordinates and OBJ output are centimetres.  The scalar construction makes a
closed solid: the gyroid sheet is clipped by a smooth spherical boundary.
No external geometry or texture assets are used.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
from pathlib import Path

import numpy as np
from skimage.measure import marching_cubes


FORMULA = "g(u,v,w)=sin(u)*cos(v)+sin(v)*cos(w)+sin(w)*cos(u)"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resolution", type=int, default=112,
                   help="samples per axis (default: 112; about 220k triangles)")
    p.add_argument("--radius-cm", type=float, default=150.0)
    p.add_argument("--periods-across", type=float, default=1.75)
    p.add_argument("--shell-half-width", type=float, default=0.16)
    p.add_argument("--extent-cm", type=float, default=154.0,
                   help="sampling half extent; must exceed radius")
    p.add_argument("--name", default="gyroid_lattice_300cm")
    p.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    return p.parse_args()


def evaluate_field(axis_cm: np.ndarray, radius_cm: float, periods: float,
                   shell_half_width: float) -> tuple[np.ndarray, float]:
    # One full trig period is 2*pi.  `periods` is measured across the 2R diameter.
    k = periods * 2.0 * math.pi / (2.0 * radius_cm)
    x, y, z = np.meshgrid(axis_cm, axis_cm, axis_cm, indexing="ij")
    u, v, w = k * x, k * y, k * z
    g = np.sin(u) * np.cos(v) + np.sin(v) * np.cos(w) + np.sin(w) * np.cos(u)
    sphere_sdf = np.sqrt((x / radius_cm) ** 2 +
                         (y / radius_cm) ** 2 +
                         (z / radius_cm) ** 2) - 1.0
    # Negative means inside the watertight solid.
    field = np.maximum(np.abs(g) - shell_half_width, sphere_sdf).astype(np.float32)
    return field, k


def area_weighted_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Return smooth unit vertex normals, preserving the marching-cubes winding."""
    p0 = vertices[faces[:, 0]]
    p1 = vertices[faces[:, 1]]
    p2 = vertices[faces[:, 2]]
    face_normals = np.cross(p1 - p0, p2 - p0)
    normals = np.zeros_like(vertices, dtype=np.float64)
    for col in range(3):
        np.add.at(normals, faces[:, col], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= 1e-12):
        raise ValueError("degenerate vertex normal")
    return (normals / lengths[:, None]).astype(np.float32)


def mesh_audit(vertices: np.ndarray, faces: np.ndarray) -> dict:
    if len(vertices) == 0 or len(faces) == 0:
        raise ValueError("empty mesh")
    if not np.isfinite(vertices).all():
        raise ValueError("non-finite vertex")
    if faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("face index outside vertex array")
    p0, p1, p2 = (vertices[faces[:, i]] for i in range(3))
    double_area = np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
    if np.any(double_area <= 1e-8):
        raise ValueError("zero-area triangle")
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges.sort(axis=1)
    # A fixed-width byte view makes exact undirected edge counting deterministic.
    edge_keys = np.ascontiguousarray(edges).view(np.dtype((np.void, edges.dtype.itemsize * 2))).ravel()
    _, edge_counts = np.unique(edge_keys, return_counts=True)
    boundary = int(np.count_nonzero(edge_counts == 1))
    nonmanifold = int(np.count_nonzero(edge_counts > 2))
    if boundary or nonmanifold:
        raise ValueError(f"mesh is not closed: boundary_edges={boundary}, nonmanifold_edges={nonmanifold}")
    return {
        "vertices": int(len(vertices)),
        "triangles": int(len(faces)),
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "degenerate_triangles": 0,
        "bounds_cm": [[float(x) for x in row] for row in zip(vertices.min(axis=0), vertices.max(axis=0))],
        "diameter_bounds_cm": [float(x) for x in (vertices.max(axis=0) - vertices.min(axis=0))],
    }


def write_obj(path: Path, vertices: np.ndarray, normals: np.ndarray, faces: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Deterministic finite gyroid sheet; units: centimetres\n")
        fh.write(f"# vertices={len(vertices)} triangles={len(faces)} smooth_normals=area_weighted\n")
        for x, y, z in vertices:
            fh.write(f"v {x:.7f} {y:.7f} {z:.7f}\n")
        for nx, ny, nz in normals:
            fh.write(f"vn {nx:.7f} {ny:.7f} {nz:.7f}\n")
        # The file is triangle-only and each vertex has its matching smooth normal.
        for a, b, c in faces + 1:
            fh.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")


def main() -> int:
    args = parse_args()
    if args.resolution < 16:
        raise SystemExit("--resolution must be >= 16")
    if args.radius_cm <= 0 or args.extent_cm <= args.radius_cm:
        raise SystemExit("extent must be greater than positive radius")
    if args.shell_half_width <= 0:
        raise SystemExit("--shell-half-width must be positive")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    axis = np.linspace(-args.extent_cm, args.extent_cm, args.resolution, dtype=np.float32)
    field, k = evaluate_field(axis, args.radius_cm, args.periods_across, args.shell_half_width)
    spacing = float(axis[1] - axis[0])
    verts, faces, _mc_normals, _values = marching_cubes(
        field, level=0.0, spacing=(spacing, spacing, spacing),
        gradient_direction="descent", allow_degenerate=False,
    )
    verts = verts + np.float32(axis[0])
    faces = faces.astype(np.int32, copy=False)
    normals = area_weighted_normals(verts, faces)
    audit = mesh_audit(verts, faces)
    obj_path = out / f"{args.name}.obj"
    write_obj(obj_path, verts, normals, faces)
    metadata = {
        "artifact": args.name,
        "formula": FORMULA,
        "scalar_field": "max(abs(g)-shell_half_width, sphere_radius_normalized-1)",
        "inside_rule": "field <= 0",
        "units": "cm",
        "radius_cm": args.radius_cm,
        "diameter_cm_target": 2.0 * args.radius_cm,
        "periods_across_target": args.periods_across,
        "frequency_radians_per_cm": k,
        "shell_half_width_g_units": args.shell_half_width,
        "grid_resolution": [args.resolution] * 3,
        "sampling_extent_cm": [-args.extent_cm, args.extent_cm],
        "grid_spacing_cm": spacing,
        "mesh": audit,
        "normal_policy": "area-weighted smooth vertex normals; triangle winding from marching_cubes",
        "source": Path(__file__).name,
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "repro_command": "python3 -B generate_gyroid.py --resolution " + str(args.resolution) +
                          " --radius-cm " + str(args.radius_cm) +
                          " --periods-across " + str(args.periods_across) +
                          " --shell-half-width " + str(args.shell_half_width) +
                          " --extent-cm " + str(args.extent_cm) +
                          " --name " + args.name,
    }
    (out / f"{args.name}.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"obj": str(obj_path), **audit}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
