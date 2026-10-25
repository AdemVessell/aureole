#!/usr/bin/env python3
"""Build the local 20-second AUREOLE equation reveal.

The first five seconds are the supplied clean Unreal render. The next three
five-second chapters replay that same clean shot with a restrained, static
disclosure panel. The panels quote the authored geometry metadata and the
actual HLSL strings in ``scripts/build_scene.py``; they do not re-render or
claim that the equations are the rasterizer.

The script deliberately refuses to run without ``clean.mp4``. It uses only
local Pillow and ffmpeg binaries and writes one final ``reveal.mp4``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "clean.mp4"
DEFAULT_OUTPUT = ROOT / "reveal.mp4"
WIDTH, HEIGHT = 1600, 900
FPS = 24


def _font(candidates: tuple[str, ...], size: int) -> object:
    """Load a local system font without downloading or depending on a font URL."""
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


MONO = (
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)
SANS = (
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _wrap_line(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Wrap words and long tokens using measured font bounds, never panel width."""
    words = text.split(" ") or [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = ""
        for character in word:
            candidate = current + character
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = character
    if current or not lines:
        lines.append(current)
    return lines


def _draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill, max_width: int, *, spacing: int = 6) -> int:
    lines: list[str] = []
    for source_line in text.splitlines() or [""]:
        lines.extend(_wrap_line(draw, source_line, font, max_width) if source_line else [""])
    rendered = "\n".join(lines)
    draw.multiline_text(xy, rendered, font=font, fill=fill, spacing=spacing)
    return draw.multiline_textbbox(xy, rendered, font=font, spacing=spacing)[3]


def render_panel(path: Path, number: str, title: str, subtitle: str, lines: list[str], *, note: str) -> None:
    """Render a transparent right-hand editorial panel at the movie raster."""
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x0 = 1112
    draw.rectangle((x0, 0, WIDTH, HEIGHT), fill=(7, 9, 12, 235))
    draw.rectangle((x0, 0, x0 + 1, HEIGHT), fill=(216, 255, 105, 225))
    draw.rectangle((x0 + 32, 86, WIDTH - 34, 87), fill=(236, 236, 232, 62))

    small = _font(MONO, 14)
    label = _font(MONO, 15)
    heading = _font(SANS, 34)
    body = _font(MONO, 25)
    body_small = _font(MONO, 20)
    panel_width = WIDTH - x0 - 68

    draw.text((x0 + 34, 38), f"{number}  /  AUREOLE", font=small, fill=(216, 255, 105, 255))
    draw.text((x0 + 34, 117), title, font=heading, fill=(238, 238, 233, 255))
    _draw_wrapped(draw, (x0 + 34, 166), subtitle.upper(), label, (166, 168, 167, 255), panel_width)

    y = 238
    for block in lines:
        if block == "":
            y += 19
            continue
        font = body_small if len(block) > 39 else body
        y = _draw_wrapped(draw, (x0 + 34, y), block, font, (228, 229, 222, 255), panel_width, spacing=5) + 12

    draw.rectangle((x0 + 34, 760, WIDTH - 34, 761), fill=(236, 236, 232, 48))
    _draw_wrapped(draw, (x0 + 34, 784), note, small, (150, 153, 153, 255), panel_width, spacing=5)
    image.save(path, format="PNG", optimize=True)


def render_panels(directory: Path) -> list[Path]:
    """Create three chapter panels from the recorded source strings."""
    chapters = [
        (
            "01", "GYROID", "chapter 1  /  spatial surface",
            [
                "g(u,v,w) =",
                "sin(u) cos(v)",
                "+ sin(v) cos(w)",
                "+ sin(w) cos(u)", "",
                "F(x,y,z) = max(",
                "|g(kx,ky,kz)| - 0.16,",
                "√(x² + y² + z²) / 150 - 1)", "",
                "inside: F ≤ 0",
                "k = 1.75 · 2π / 300 rad/cm",
            ],
            "finite sheet · 300 cm target diameter · cm coordinates",
        ),
        (
            "02", "WARP", "chapter 2  /  twist + breathing",
            [
                "φ = 2πt / 5",
                "κ = .62 sin(φ − π/2)",
                "a = 1 + .055 sin φ",
                "θ = κz / 150",
                "",
                "x′ = a(x cos θ − y sin θ)",
                "y′ = a(x sin θ + y cos θ)",
                "z′ = az",
            ],
            "Unreal material HLSL implements this world-position offset; exact source remains build_scene.py",
        ),
        (
            "03", "STUDIO", "chapter 3  /  procedural light",
            [
                "L_j(u,v) = P_j exp(−A⁴−B⁴)",
                "A = d_u / s_u",
                "B = (v−v_j) / s_v",
                "",
                "E(u,v) = b + Σ_j c_j L_j",
                "",
                "Three soft panels create",
                "the HDR illumination map.",
                "",
                "Four area lights, metal and",
                "camera finish the Unreal scene.",
            ],
            "Five seconds of unique motion, replayed for these chapters. Unreal renders the final pixels.",
        ),
    ]
    paths: list[Path] = []
    for chapter in chapters:
        path = directory / f"panel_{chapter[0]}.png"
        render_panel(path, *chapter[:4], note=chapter[4])
        paths.append(path)
    return paths


def run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"command failed with exit {exc.returncode}: {' '.join(command)}") from exc


def build(input_path: Path, output_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(
            f"{input_path} is missing; refusing to build the reveal before the clean Unreal render exists"
        )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required and was not found on PATH")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aureole-reveal-") as temporary:
        panel_paths = render_panels(Path(temporary))
        filter_complex = (
            "[0:v]fps=24,scale=1600:900:force_original_aspect_ratio=decrease,"
            "pad=1600:900:(ow-iw)/2:(oh-ih)/2,setsar=1,split=4[clean][one][two][three];"
            "[clean]trim=duration=5,setpts=PTS-STARTPTS[clip0];"
            "[one]trim=duration=5,setpts=PTS-STARTPTS,crop=1112:900:244:0,pad=1600:900:0:0[base1];"
            "[two]trim=duration=5,setpts=PTS-STARTPTS,crop=1112:900:244:0,pad=1600:900:0:0[base2];"
            "[three]trim=duration=5,setpts=PTS-STARTPTS,crop=1112:900:244:0,pad=1600:900:0:0[base3];"
            "[base1][1:v]overlay=0:0:shortest=1,format=yuv420p[clip1];"
            "[base2][2:v]overlay=0:0:shortest=1,format=yuv420p[clip2];"
            "[base3][3:v]overlay=0:0:shortest=1,format=yuv420p[clip3];"
            "[clip0][clip1][clip2][clip3]concat=n=4:v=1:a=0[outv]"
        )
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_path),
            "-loop", "1", "-i", str(panel_paths[0]),
            "-loop", "1", "-i", str(panel_paths[1]),
            "-loop", "1", "-i", str(panel_paths[2]),
            "-filter_complex", filter_complex, "-map", "[outv]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", "24", "-movflags", "+faststart",
            str(output_path),
        ]
        run(command)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="supplied five-second clean render")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="20-second reveal movie")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        build(args.input.resolve(), args.output.resolve())
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"make_reveal: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
