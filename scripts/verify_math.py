#!/usr/bin/env python3
"""Verify lattice deformation and inverse-transpose normal transport locally.

The check reads the authored OBJ, samples stored smooth vertex normals, and
tests orthogonality against finite-difference deformed tangents. A deliberately
wrong control (leaving normals unchanged) must fail the same test.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBJ = ROOT / "geometry" / "gyroid_lattice_300cm.obj"
DEFAULT_LOG = ROOT / "proof" / "MATH_CHECK.json"


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                vertices.append([float(v) for v in line.split()[1:4]])
            elif line.startswith("vn "):
                normals.append([float(v) for v in line.split()[1:4]])
    v = np.asarray(vertices, dtype=np.float64)
    n = np.asarray(normals, dtype=np.float64)
    if v.ndim != 2 or v.shape[1] != 3 or not len(v):
        raise ValueError("OBJ has no usable vertices")
    if n.shape != v.shape:
        raise ValueError(f"expected one OBJ normal per vertex, got {n.shape} for {v.shape}")
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    return v, n


def deformation(p: np.ndarray, time_s: float) -> np.ndarray:
    phase = 2.0 * math.pi * time_s / 5.0
    k = 0.62 * math.sin(phase - math.pi / 2.0) / 150.0
    a = 1.0 + 0.055 * math.sin(phase)
    theta = k * p[..., 2]
    c, s = np.cos(theta), np.sin(theta)
    return a * np.stack((c * p[..., 0] - s * p[..., 1],
                         s * p[..., 0] + c * p[..., 1],
                         p[..., 2]), axis=-1)


def jacobian(p: np.ndarray, time_s: float) -> np.ndarray:
    """Analytic dq/dP for build_scene.py's twist-plus-expansion deformation."""
    phase = 2.0 * math.pi * time_s / 5.0
    k = 0.62 * math.sin(phase - math.pi / 2.0) / 150.0
    a = 1.0 + 0.055 * math.sin(phase)
    theta = k * p[..., 2]
    c, s = np.cos(theta), np.sin(theta)
    x, y = p[..., 0], p[..., 1]
    j = np.zeros(p.shape[:-1] + (3, 3), dtype=np.float64)
    j[..., 0, 0] = a * c
    j[..., 0, 1] = -a * s
    j[..., 0, 2] = -a * k * (s * x + c * y)
    j[..., 1, 0] = a * s
    j[..., 1, 1] = a * c
    j[..., 1, 2] = a * k * (c * x - s * y)
    j[..., 2, 2] = a
    return j


def hlsl_normal(p: np.ndarray, n: np.ndarray, time_s: float) -> np.ndarray:
    """Literal normal expression from build_scene.py, translated to NumPy."""
    phase = 2.0 * math.pi * time_s / 5.0
    k = 0.62 * math.sin(phase - math.pi / 2.0) / 150.0
    theta = k * p[..., 2]
    c, s = np.cos(theta), np.sin(theta)
    out = np.stack((c * n[..., 0] - s * n[..., 1],
                    s * n[..., 0] + c * n[..., 1],
                    n[..., 2] + k * (p[..., 1] * n[..., 0] - p[..., 0] * n[..., 1])), axis=-1)
    return out / np.linalg.norm(out, axis=-1, keepdims=True)


def inverse_transpose_normal(p: np.ndarray, n: np.ndarray, time_s: float) -> np.ndarray:
    j = jacobian(p, time_s)
    out = np.linalg.solve(np.swapaxes(j, -1, -2), n[..., None])[..., 0]
    return out / np.linalg.norm(out, axis=-1, keepdims=True)


def finite_difference_tangents(p: np.ndarray, n: np.ndarray, time_s: float,
                               epsilon_cm: float) -> tuple[np.ndarray, np.ndarray]:
    axes = np.zeros_like(n)
    axes[:, 0] = 1.0
    axes[np.abs(n[:, 0]) > 0.9] = (0.0, 1.0, 0.0)
    t1 = np.cross(n, axes)
    t1 /= np.linalg.norm(t1, axis=1, keepdims=True)
    t2 = np.cross(n, t1)
    t2 /= np.linalg.norm(t2, axis=1, keepdims=True)

    def fd(tangent: np.ndarray) -> np.ndarray:
        return (deformation(p + epsilon_cm * tangent, time_s) -
                deformation(p - epsilon_cm * tangent, time_s)) / (2.0 * epsilon_cm)

    return fd(t1), fd(t2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obj", type=Path, default=DEFAULT_OBJ)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--sample-count", type=int, default=96)
    parser.add_argument("--epsilon-cm", type=float, default=1e-2)
    args = parser.parse_args()
    if args.sample_count < 8 or args.epsilon_cm <= 0:
        raise SystemExit("sample-count must be >= 8 and epsilon-cm must be positive")

    vertices, source_normals = read_obj(args.obj)
    sample_indices = np.linspace(0, len(vertices) - 1, args.sample_count, dtype=np.int64)
    sample_indices = np.unique(sample_indices)
    p = vertices[sample_indices]
    n = source_normals[sample_indices]
    times = np.linspace(0.0, 5.0, 11)

    corrected_residuals: list[float] = []
    wrong_residuals: list[float] = []
    hlsl_errors: list[float] = []
    jacobian_errors: list[float] = []
    bounds = []
    finite = True
    for time_s in times:
        time_s = float(time_s)
        q_all = deformation(vertices, time_s)
        finite = finite and bool(np.isfinite(q_all).all())
        bounds.append({
            "time_s": time_s,
            "min_cm": [float(v) for v in q_all.min(axis=0)],
            "max_cm": [float(v) for v in q_all.max(axis=0)],
            "max_radius_cm": float(np.linalg.norm(q_all, axis=1).max()),
        })

        j = jacobian(p, time_s)
        corrected = inverse_transpose_normal(p, n, time_s)
        literal = hlsl_normal(p, n, time_s)
        hlsl_errors.append(float(np.max(np.linalg.norm(corrected - literal, axis=1))))
        numeric_j = np.empty_like(j)
        for axis in range(3):
            delta = np.zeros_like(p)
            delta[:, axis] = args.epsilon_cm
            numeric_j[..., :, axis] = (deformation(p + delta, time_s) -
                                       deformation(p - delta, time_s)) / (2.0 * args.epsilon_cm)
        jacobian_errors.append(float(np.max(np.abs(j - numeric_j))))

        tangent_1, tangent_2 = finite_difference_tangents(p, n, time_s, args.epsilon_cm)
        for tangent in (tangent_1, tangent_2):
            corrected_residuals.append(float(np.max(np.abs(np.sum(corrected * tangent, axis=1)))))
            # Deliberate failure control: unchanged normals are not valid under
            # the z-dependent shear introduced by the twist.
            wrong_residuals.append(float(np.max(np.abs(np.sum(n * tangent, axis=1)))))

    corrected_max = max(corrected_residuals)
    wrong_max = max(wrong_residuals)
    hlsl_max = max(hlsl_errors)
    jacobian_max = max(jacobian_errors)
    max_radius = max(row["max_radius_cm"] for row in bounds)
    bounded = max_radius < 170.0
    result = {
        "status": "PASS" if finite and bounded and corrected_max < 1e-6 and hlsl_max < 1e-10 and jacobian_max < 1e-7 and wrong_max > 1e-3 else "FAIL",
        "scope": "local deformation math only; no Unreal render claim",
        "source_obj": str(args.obj.resolve()),
        "source_vertices": int(len(vertices)),
        "sample_count": int(len(p)),
        "times_s": [float(t) for t in times],
        "epsilon_cm": args.epsilon_cm,
        "deformation": "q=a(t)*Rz(k(t)*Pz)*P; a=1+0.055*sin(2*pi*t/5); k=0.62*sin(2*pi*t/5-pi/2)/150",
        "checks": {
            "finite_all_vertices_t0_to_t5": finite,
            "bounded_max_radius_cm": max_radius,
            "bounded_threshold_cm": 170.0,
            "bounded_pass": bounded,
            "analytic_jacobian_vs_finite_difference_max_abs": jacobian_max,
            "inverse_transpose_vs_literal_hlsl_max_vector_error": hlsl_max,
            "corrected_normal_vs_fd_tangent_max_abs_dot": corrected_max,
            "wrong_no_normal_correction_max_abs_dot": wrong_max,
            "wrong_control_must_fail": wrong_max > 1e-3,
        },
        "bounds": bounds,
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "reproduction": "python3 -B scripts/verify_math.py",
    }
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
