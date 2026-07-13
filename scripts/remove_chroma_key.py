#!/usr/bin/env python3
"""Convert a flat chroma-key background to transparent alpha."""

from __future__ import annotations

import argparse
from io import BytesIO
import math
import os
from pathlib import Path
import re
from statistics import median
import sys
import tempfile
from typing import TypeAlias


Color: TypeAlias = tuple[int, int, int]
ALPHA_NOISE_FLOOR = 8
KEY_DOMINANCE_THRESHOLD = 16.0


def _die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _load_pillow():
    try:
        from PIL import Image, ImageFilter, UnidentifiedImageError
    except ImportError:
        _die("Pillow is required. Install the dependencies listed in requirements.txt.")
    return Image, ImageFilter, UnidentifiedImageError


def _parse_key_color(raw: str) -> Color:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", raw.strip())
    if not match:
        _die("--key-color must be a six-digit RGB hex value such as #00ff00.")
    value = match.group(1)
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _validate_number(value: float, option: str, minimum: float, maximum: float) -> None:
    if not math.isfinite(value) or not minimum <= value <= maximum:
        _die(f"{option} must be a finite number between {minimum:g} and {maximum:g}.")


def _validate_args(args: argparse.Namespace) -> None:
    _validate_number(args.tolerance, "--tolerance", 0, 255)
    _validate_number(args.transparent_threshold, "--transparent-threshold", 0, 255)
    _validate_number(args.opaque_threshold, "--opaque-threshold", 0, 255)
    _validate_number(args.edge_feather, "--edge-feather", 0, 64)
    _validate_number(args.edge_contract, "--edge-contract", 0, 16)
    if args.soft_matte and args.transparent_threshold >= args.opaque_threshold:
        _die("--transparent-threshold must be lower than --opaque-threshold.")

    source = Path(args.input)
    if not source.is_file():
        _die(f"Input image not found or not a file: {source}")

    output = Path(args.out)
    if output.suffix.lower() not in {".png", ".webp"}:
        _die("--out must end in .png or .webp to preserve alpha.")
    if output.exists() and not args.force:
        _die(f"Output already exists: {output} (use --force to overwrite)")
    if output.exists() and not output.is_file():
        _die(f"Output path is not a file: {output}")


def _channel_distance(left: Color, right: Color) -> int:
    return max(abs(a - b) for a, b in zip(left, right))


def _clamp_channel(value: float) -> int:
    return max(0, min(255, round(value)))


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _soft_alpha(distance: int, transparent: float, opaque: float) -> int:
    if distance <= transparent:
        return 0
    if distance >= opaque:
        return 255
    return _clamp_channel(255 * _smoothstep((distance - transparent) / (opaque - transparent)))


def _spill_channels(key: Color) -> list[int]:
    strongest = max(key)
    if strongest < 128:
        return []
    return [index for index, value in enumerate(key) if value >= 128 and value >= strongest - 16]


def _key_dominance(rgb: Color, key: Color) -> float:
    spill = _spill_channels(key)
    if not spill:
        return 0.0
    other = [index for index in range(3) if index not in spill]
    key_strength = min(rgb[index] for index in spill)
    other_strength = max((rgb[index] for index in other), default=0)
    return float(key_strength - other_strength)


def _dominance_alpha(rgb: Color, key: Color) -> int:
    dominance = _key_dominance(rgb, key)
    if dominance <= 0:
        return 255
    spill = _spill_channels(key)
    other = [index for index in range(3) if index not in spill]
    other_strength = max((rgb[index] for index in other), default=0)
    denominator = max(1.0, max(key) - other_strength)
    return _clamp_channel(255 * (1.0 - min(1.0, dominance / denominator)))


def _is_key_edge(rgb: Color, key: Color, distance: int, opaque_threshold: float) -> bool:
    """Return true only for pixels plausibly belonging to the key-colored edge."""
    if distance > opaque_threshold:
        return False
    return distance <= 32 or _key_dominance(rgb, key) >= KEY_DOMINANCE_THRESHOLD


def _despill(rgb: Color, key: Color) -> Color:
    spill = _spill_channels(key)
    if not spill:
        return rgb
    channels = list(rgb)
    other = [index for index in range(3) if index not in spill]
    cap = max((channels[index] for index in other), default=0)
    for index in spill:
        channels[index] = min(channels[index], cap)
    return tuple(channels)  # type: ignore[return-value]


def _apply_alpha_to_image(
    image,
    *,
    key: Color,
    tolerance: int,
    spill_cleanup: bool,
    soft_matte: bool,
    transparent_threshold: float,
    opaque_threshold: float,
) -> int:
    pixels = image.load()
    transparent_count = 0

    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, source_alpha = pixels[x, y]
            rgb = (red, green, blue)
            distance = _channel_distance(rgb, key)
            key_edge = _is_key_edge(rgb, key, distance, opaque_threshold)

            if soft_matte and key_edge:
                matte_alpha = min(
                    _soft_alpha(distance, transparent_threshold, opaque_threshold),
                    _dominance_alpha(rgb, key),
                )
            else:
                matte_alpha = 0 if distance <= tolerance else 255

            alpha = round(matte_alpha * source_alpha / 255)
            if 0 < alpha <= ALPHA_NOISE_FLOOR:
                alpha = 0
            if alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)
                transparent_count += 1
                continue

            if spill_cleanup and key_edge:
                red, green, blue = _despill(rgb, key)
            pixels[x, y] = (red, green, blue, alpha)

    return transparent_count


def _transform_alpha(image, *, contract: int, feather: float):
    if not contract and not feather:
        return image
    _, ImageFilter, _ = _load_pillow()
    alpha = image.getchannel("A")
    for _ in range(contract):
        alpha = alpha.filter(ImageFilter.MinFilter(3))
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=feather))
    image.putalpha(alpha)
    return image


def _iter_border_pixels(image, mode: str):
    pixels = image.load()
    width, height = image.size
    if mode == "corners":
        patch = max(1, min(width, height, 12))
        boxes = (
            (0, 0, patch, patch),
            (width - patch, 0, width, patch),
            (0, height - patch, patch, height),
            (width - patch, height - patch, width, height),
        )
        for left, top, right, bottom in boxes:
            for y in range(top, bottom):
                for x in range(left, right):
                    yield pixels[x, y]
        return

    band = max(1, min(width, height, 6))
    step = max(1, min(width, height) // 256)
    for x in range(0, width, step):
        for offset in range(band):
            yield pixels[x, offset]
            yield pixels[x, height - 1 - offset]
    for y in range(0, height, step):
        for offset in range(band):
            yield pixels[offset, y]
            yield pixels[width - 1 - offset, y]


def _sample_border_key(image, mode: str) -> Color:
    # Ignore fully transparent pixels: their hidden RGB values are not meaningful.
    samples = [pixel[:3] for pixel in _iter_border_pixels(image, mode) if pixel[3] > 0]
    if not samples:
        _die("Could not sample a visible key color from the image border.")
    return tuple(round(median(sample[channel] for sample in samples)) for channel in range(3))  # type: ignore[return-value]


def _alpha_counts(image) -> tuple[int, int, int]:
    alphas = image.getchannel("A").tobytes()
    total = image.width * image.height
    transparent = sum(alpha == 0 for alpha in alphas)
    partial = sum(0 < alpha < 255 for alpha in alphas)
    return total, transparent, partial


def _encode_image(image, suffix: str) -> bytes:
    buffer = BytesIO()
    if suffix == ".png":
        image.save(buffer, format="PNG", optimize=True)
    else:
        image.save(buffer, format="WEBP", lossless=True)
    return buffer.getvalue()


def _atomic_write(output: Path, data: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _remove_chroma_key(args: argparse.Namespace) -> None:
    Image, _, UnidentifiedImageError = _load_pillow()
    source = Path(args.input)
    output = Path(args.out)
    try:
        with Image.open(source) as opened:
            opened.load()
            image = opened.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        _die(f"Could not read input image: {error}")

    key = _sample_border_key(image, args.auto_key) if args.auto_key != "none" else _parse_key_color(args.key_color)
    matched = _apply_alpha_to_image(
        image,
        key=key,
        tolerance=args.tolerance,
        spill_cleanup=args.spill_cleanup,
        soft_matte=args.soft_matte,
        transparent_threshold=args.transparent_threshold,
        opaque_threshold=args.opaque_threshold,
    )
    _transform_alpha(image, contract=args.edge_contract, feather=args.edge_feather)
    total, transparent, partial = _alpha_counts(image)
    _atomic_write(output, _encode_image(image, output.suffix.lower()))

    print(f"Wrote {output}")
    print(f"Key color: #{key[0]:02x}{key[1]:02x}{key[2]:02x}")
    print(f"Alpha: {transparent} transparent, {partial} partial, {total} total")
    if matched == 0:
        print("Warning: no pixels matched the key color before edge processing.", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replace a flat chroma-key background with transparent alpha."
    )
    parser.add_argument("--input", required=True, help="Input image path.")
    parser.add_argument("--out", required=True, help="Output .png or .webp path.")
    parser.add_argument("--key-color", default="#00ff00", help="Key color as RGB hex (default: #00ff00).")
    parser.add_argument("--auto-key", choices=("none", "corners", "border"), default="none", help="Sample the key from corners or the full border.")
    parser.add_argument("--tolerance", type=int, default=12, help="Hard-key channel tolerance, 0-255 (default: 12).")
    parser.add_argument("--soft-matte", action="store_true", help="Create a smooth edge alpha ramp.")
    parser.add_argument("--transparent-threshold", type=float, default=12.0, help="Soft-matte transparent distance (default: 12).")
    parser.add_argument("--opaque-threshold", type=float, default=96.0, help="Soft-matte opaque distance (default: 96).")
    parser.add_argument("--edge-contract", type=int, default=0, help="Contract alpha by 0-16 pixels.")
    parser.add_argument("--edge-feather", type=float, default=0.0, help="Blur alpha by radius 0-64.")
    parser.add_argument("--despill", dest="spill_cleanup", action="store_true", help="Reduce key-color spill on matched edge pixels.")
    parser.add_argument("--spill-cleanup", dest="spill_cleanup", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    _validate_args(args)
    _remove_chroma_key(args)


if __name__ == "__main__":
    main()
