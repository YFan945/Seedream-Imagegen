#!/usr/bin/env python3
"""Convert a flat chroma-key background to transparent alpha."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from io import BytesIO
import math
import os
from pathlib import Path
import re
from statistics import median
import sys
import tempfile
from typing import TypeAlias
import warnings


Color: TypeAlias = tuple[int, int, int]
ALPHA_NOISE_FLOOR = 8
MAX_INPUT_BYTES = 30_000_000
MAX_INPUT_PIXELS = 36_000_000
AUTO_KEY_CLUSTER_RADIUS = 24
AUTO_KEY_MIN_SHARE = 0.70


@dataclass(frozen=True, slots=True)
class ChromaStats:
    total: int
    source_transparent: int
    key_matched: int
    final_transparent: int
    partial: int


def _die(message: str, code: int = 1) -> None:
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(code)


def _load_pillow():
    try:
        from PIL import Image, ImageChops, ImageFilter, ImageOps, UnidentifiedImageError
    except ImportError:
        _die("缺少 Pillow；请安装 requirements.txt 中声明的依赖。")
    return Image, ImageFilter, ImageChops, ImageOps, UnidentifiedImageError


def _parse_key_color(raw: str) -> Color:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", raw.strip())
    if not match:
        _die("--key-color 必须是六位 RGB 十六进制值，例如 #00ff00。")
    value = match.group(1)
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _validate_number(value: float, option: str, minimum: float, maximum: float) -> None:
    if not math.isfinite(value) or not minimum <= value <= maximum:
        _die(f"{option} 必须是 {minimum:g} 到 {maximum:g} 之间的有限数值。")


def _validate_args(args: argparse.Namespace) -> None:
    _validate_number(args.tolerance, "--tolerance", 0, 255)
    _validate_number(args.transparent_threshold, "--transparent-threshold", 0, 255)
    _validate_number(args.opaque_threshold, "--opaque-threshold", 0, 255)
    _validate_number(args.edge_feather, "--edge-feather", 0, 64)
    _validate_number(args.edge_contract, "--edge-contract", 0, 16)
    if args.transparent_threshold > args.opaque_threshold:
        _die("--transparent-threshold 不能大于 --opaque-threshold。")
    if getattr(args, "auto_key", "none") == "none" and (
        args.soft_matte or getattr(args, "spill_cleanup", False)
    ):
        key = _parse_key_color(getattr(args, "key_color", "#00ff00"))
        if max(key) - min(key) < 96 or not _spill_channels(key):
            _die("--soft-matte/--despill 只支持具有主导亮通道的高饱和色键；灰、白、黑或过暗的键色不受支持。")

    source = Path(args.input)
    if not source.is_file():
        _die(f"输入图片不存在或不是文件：{source}")
    try:
        if source.stat().st_size > MAX_INPUT_BYTES:
            _die(f"输入图片超过 {MAX_INPUT_BYTES} bytes 安全上限：{source}")
    except OSError as error:
        _die(f"无法读取输入图片属性：{source}（{error}）")

    output = Path(args.out)
    if source.resolve(strict=False) == output.resolve(strict=False):
        _die("--input 与 --out 不得指向同一路径。")
    if output.suffix.lower() not in {".png", ".webp"}:
        _die("--out 必须以 .png 或 .webp 结尾以保留 alpha。")
    if output.exists() and not args.force:
        _die(f"输出已存在：{output}（仅在明确授权后使用 --force 覆盖）")
    if output.exists() and not output.is_file():
        _die(f"输出路径不是文件：{output}")


def _channel_distance(left: Color, right: Color) -> int:
    return max(abs(a - b) for a, b in zip(left, right))


def _clamp_channel(value: float) -> int:
    return max(0, min(255, round(value)))


def _spill_channels(key: Color) -> list[int]:
    strongest = max(key)
    if strongest < 128:
        return []
    return [index for index, value in enumerate(key) if value >= 128 and value >= strongest - 16]


def _retain_border_connected_matte(matte):
    """Keep only non-opaque matte pixels connected to an image border."""
    Image, _, _, _, _ = _load_pillow()
    width, height = matte.size
    values = matte.tobytes()
    connected = bytearray(width * height)
    queue: deque[int] = deque()

    def enqueue(index: int) -> None:
        if not connected[index] and values[index] < 255:
            connected[index] = 1
            queue.append(index)

    for x in range(width):
        enqueue(x)
        enqueue((height - 1) * width + x)
    for y in range(height):
        enqueue(y * width)
        enqueue(y * width + width - 1)

    while queue:
        index = queue.popleft()
        x = index % width
        if x:
            enqueue(index - 1)
        if x + 1 < width:
            enqueue(index + 1)
        if index >= width:
            enqueue(index - width)
        if index + width < width * height:
            enqueue(index + width)

    output = bytearray([255]) * (width * height)
    for index, is_connected in enumerate(connected):
        if is_connected:
            output[index] = values[index]
    return Image.frombytes("L", matte.size, bytes(output))


def _apply_alpha_to_image(
    image,
    *,
    key: Color,
    tolerance: int,
    spill_cleanup: bool,
    soft_matte: bool,
    transparent_threshold: float,
    opaque_threshold: float,
    edge_contract: int = 0,
    edge_feather: float = 0.0,
    border_connected: bool = False,
) -> ChromaStats:
    Image, _, ImageChops, _, _ = _load_pillow()
    from PIL import ImageMath

    bands = list(image.split())
    source_rgb = bands[:3]
    source_alpha = bands[3]
    source_transparent = source_alpha.histogram()[0]
    distances = [
        ImageChops.difference(band, Image.new("L", image.size, key_channel))
        for band, key_channel in zip(source_rgb, key)
    ]
    distance = ImageChops.lighter(ImageChops.lighter(distances[0], distances[1]), distances[2])
    hard_matte = distance.point(lambda value: 0 if value <= tolerance else 255)

    if soft_matte:
        if not _spill_channels(key):
            _die("色键缺少主导亮通道（最强通道 < 128），--soft-matte 不受支持。")
        # 对均匀色键，最大 RGB 距离就是可恢复的 alpha 线索。旧的色度分支会把
        # 洋红（R == B）等合法前景误判成中性背景，并把 alpha 放大至不透明。
        lower = transparent_threshold
        upper = opaque_threshold
        if upper <= lower:
            matte = distance.point(lambda value: 0 if value <= lower else 255)
        else:
            matte = distance.point(
                lambda value: 0
                if value <= lower
                else 255
                if value >= upper
                else _clamp_channel(255 * (value - lower) / (upper - lower))
            )
    else:
        matte = hard_matte

    matte = matte.point(
        lambda value: 0 if 0 < value <= ALPHA_NOISE_FLOOR else value
    )
    if border_connected:
        matte = _retain_border_connected_matte(matte)
    key_matched = matte.histogram()[0]
    partial_mask = matte.point(lambda value: 255 if 0 < value < 255 else 0)
    safe_alpha = matte.point(lambda value: max(1, value))
    recovered_rgb = []
    for band, key_channel in zip(source_rgb, key):
        # (channel * 255 - (255 - alpha) * key) / alpha，需要保留符号，
        # 因此用 ImageMath 处理而不是对负值截断的 ImageChops。
        recovered = ImageMath.lambda_eval(
            lambda values, key_channel=key_channel: (
                values["channel"] * 255 - (255 - values["alpha"]) * key_channel
            )
            / values["alpha"],
            channel=band,
            alpha=safe_alpha,
        ).convert("L")
        recovered_rgb.append(recovered)

    output_rgb = [
        Image.composite(recovered, original, partial_mask)
        for recovered, original in zip(recovered_rgb, source_rgb)
    ]
    transparent_mask = matte.point(lambda value: 255 if value == 0 else 0)
    black = Image.new("L", image.size, 0)
    output_rgb = [Image.composite(black, band, transparent_mask) for band in output_rgb]
    image.paste(Image.merge("RGBA", (*output_rgb, source_alpha)))

    _transform_alpha(
        image,
        contract=edge_contract,
        feather=edge_feather,
        source_alpha=source_alpha,
        chroma_matte=matte,
    )
    if spill_cleanup:
        spill = _spill_channels(key)
        other = [index for index in range(3) if index not in spill]
        if other:
            output_bands = list(image.convert("RGB").split())
            cap = output_bands[other[0]]
            for index in other[1:]:
                cap = ImageChops.lighter(cap, output_bands[index])
            partial_alpha = image.getchannel("A").point(
                lambda value: 255 if 0 < value < 255 else 0
            )
            for index in spill:
                despilled = ImageChops.darker(output_bands[index], cap)
                output_bands[index] = Image.composite(despilled, output_bands[index], partial_alpha)
            image.paste(Image.merge("RGBA", (*output_bands, image.getchannel("A"))))
    final_histogram = image.getchannel("A").histogram()
    return ChromaStats(
        total=image.width * image.height,
        source_transparent=source_transparent,
        key_matched=key_matched,
        final_transparent=final_histogram[0],
        partial=sum(final_histogram[1:255]),
    )


def _transform_alpha(
    image,
    *,
    contract: int,
    feather: float,
    source_alpha=None,
    chroma_matte=None,
):
    Image, ImageFilter, ImageChops, _, _ = _load_pillow()
    source_alpha = source_alpha or image.getchannel("A")
    alpha = chroma_matte or Image.new("L", image.size, 255)
    for _ in range(contract):
        alpha = alpha.filter(ImageFilter.MinFilter(3))
    if feather:
        blurred = alpha.filter(ImageFilter.GaussianBlur(radius=feather))
        alpha = ImageChops.darker(alpha, blurred)
    image.putalpha(ImageChops.multiply(source_alpha, alpha))
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


def _corner_sample_groups(image):
    pixels = image.load()
    width, height = image.size
    patch = max(1, min(8, (width + 1) // 2, (height + 1) // 2))
    boxes = (
        (0, 0, patch, patch),
        (width - patch, 0, width, patch),
        (0, height - patch, patch, height),
        (width - patch, height - patch, width, height),
    )
    for left, top, right, bottom in boxes:
        yield [
            pixels[x, y][:3]
            for y in range(top, bottom)
            for x in range(left, right)
            if pixels[x, y][3] > 0
        ]


def _dominant_sample(samples: list[Color], min_share: float) -> Color | None:
    if not samples:
        return None
    # 直接按距离寻找最大簇，避免 239/240 这样仅差 1 的像素因量化桶边界被拆成两峰。
    step = max(1, len(samples) // 256)
    candidates = samples[::step]
    candidate = max(
        candidates,
        key=lambda value: sum(
            _channel_distance(sample, value) <= AUTO_KEY_CLUSTER_RADIUS for sample in samples
        ),
    )
    members = [sample for sample in samples if _channel_distance(sample, candidate) <= AUTO_KEY_CLUSTER_RADIUS]
    if len(members) / len(samples) < min_share:
        return None
    center = tuple(round(median(sample[channel] for sample in members)) for channel in range(3))
    return min(members, key=lambda sample: _channel_distance(sample, center))


def _sample_border_key(image, mode: str) -> Color:
    # Ignore fully transparent pixels: their hidden RGB values are not meaningful.
    samples = [pixel[:3] for pixel in _iter_border_pixels(image, mode) if pixel[3] > 0]
    if not samples:
        _die("无法从图片边框采样可见键色。")
    candidate = _dominant_sample(samples, AUTO_KEY_MIN_SHARE)
    if candidate is None:
        _die("自动取色检测到多峰或不一致边框；请显式传入 --key-color。")
    cluster = [
        sample
        for sample in samples
        if _channel_distance(sample, candidate) <= AUTO_KEY_CLUSTER_RADIUS
    ]
    if len(cluster) / len(samples) < AUTO_KEY_MIN_SHARE:
        _die("自动取色置信度不足；边框颜色不够均匀，请显式传入 --key-color。")
    if max(candidate) - min(candidate) < 96 or not _spill_channels(candidate):
        _die("自动取色只支持具有主导亮通道的高饱和色键；请显式选择绿色、洋红、蓝色或青色色键。")
    for corner_samples in _corner_sample_groups(image):
        if not corner_samples:
            continue
        corner_key = _dominant_sample(corner_samples, 0.60)
        if corner_key is None or _channel_distance(corner_key, candidate) > AUTO_KEY_CLUSTER_RADIUS:
            _die("自动取色的四角背景不一致；请显式传入 --key-color。")
    return candidate


def _encode_image(image, suffix: str) -> bytes:
    buffer = BytesIO()
    if suffix == ".png":
        image.save(buffer, format="PNG", optimize=True)
    else:
        image.save(buffer, format="WEBP", lossless=True)
    return buffer.getvalue()


def _enable_heif_support() -> None:
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        _die("读取 HEIC/HEIF 需要 pillow-heif；请安装 requirements.txt 中的依赖。")
    register_heif_opener()


def _validate_encoded_image(data: bytes, suffix: str, expected_size: tuple[int, int]) -> None:
    Image, _, _, _, UnidentifiedImageError = _load_pillow()
    expected_format = "PNG" if suffix == ".png" else "WEBP"
    try:
        with Image.open(BytesIO(data)) as decoded:
            decoded.load()
            if decoded.format != expected_format:
                _die(f"输出编码格式错误：期望 {expected_format}，实际 {decoded.format}。")
            if decoded.size != expected_size:
                _die(f"输出尺寸错误：期望 {expected_size}，实际 {decoded.size}。")
            if "A" not in decoded.getbands():
                _die("输出图片缺少 alpha 通道。")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        _die(f"输出图片无法重新解码：{error}")


def _atomic_write(output: Path, data: bytes, *, force: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    created_target = False
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temporary, output)
            temporary = None
        else:
            try:
                os.link(temporary, output)
            except FileExistsError:
                _die(f"输出已存在，未覆盖：{output}")
            except OSError:
                # 不支持硬链接的文件系统（exFAT、部分网络盘）退化为排他创建。
                try:
                    with output.open("xb") as target:
                        created_target = True
                        target.write(data)
                        target.flush()
                        os.fsync(target.fileno())
                    created_target = False
                except FileExistsError:
                    _die(f"输出已存在，未覆盖：{output}")
                except OSError as error:
                    _die(f"无法写入输出图片：{output}（{error}）")
    except FileExistsError:
        _die(f"输出已存在，未覆盖：{output}")
    except OSError as error:
        _die(f"无法写入输出图片：{output}（{error}）")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if created_target:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass


def _remove_chroma_key(args: argparse.Namespace) -> None:
    Image, _, _, ImageOps, UnidentifiedImageError = _load_pillow()
    source = Path(args.input)
    output = Path(args.out)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            if source.suffix.lower() in {".heic", ".heif"}:
                _enable_heif_support()
            with Image.open(source) as opened:
                if getattr(opened, "n_frames", 1) != 1:
                    _die("只支持静态图片；动画或多帧输入不会被静默截取首帧。")
                width, height = opened.size
                if width * height > MAX_INPUT_PIXELS:
                    _die(f"输入图片超过 {MAX_INPUT_PIXELS} pixels 安全上限。")
                image = ImageOps.exif_transpose(opened).convert("RGBA")
                image.load()
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
    ) as error:
        _die(f"无法读取输入图片：{error}")

    key = _sample_border_key(image, args.auto_key) if args.auto_key != "none" else _parse_key_color(args.key_color)
    stats = _apply_alpha_to_image(
        image,
        key=key,
        tolerance=args.tolerance,
        spill_cleanup=args.spill_cleanup,
        soft_matte=args.soft_matte,
        transparent_threshold=args.transparent_threshold,
        opaque_threshold=args.opaque_threshold,
        edge_contract=args.edge_contract,
        edge_feather=args.edge_feather,
        border_connected=args.border_connected,
    )
    try:
        encoded = _encode_image(image, output.suffix.lower())
    except (OSError, ValueError) as error:
        _die(f"无法编码输出图片：{error}")
    _validate_encoded_image(encoded, output.suffix.lower(), image.size)
    _atomic_write(output, encoded, force=args.force)

    print(f"已写入：{output}")
    print(f"键色：#{key[0]:02x}{key[1]:02x}{key[2]:02x}")
    print(
        "Alpha："
        f"source-transparent={stats.source_transparent}，"
        f"key-matched={stats.key_matched}，"
        f"final-transparent={stats.final_transparent}，"
        f"partial={stats.partial}，total={stats.total}"
    )
    if stats.final_transparent == stats.total:
        print("警告：输出图片为全透明，请核对键色和阈值。", file=sys.stderr)
    elif stats.final_transparent == 0 and stats.partial == 0:
        print("警告：输出图片为全不透明，可能没有匹配到背景。", file=sys.stderr)
    if stats.key_matched == 0:
        print("警告：边缘处理前没有像素匹配键色。", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将平坦色键背景转换为透明 alpha。"
    )
    parser.add_argument("--input", required=True, help="输入图片路径")
    parser.add_argument("--out", required=True, help="输出 .png 或 .webp 路径")
    parser.add_argument("--key-color", default="#00ff00", help="RGB 十六进制键色，默认 #00ff00")
    parser.add_argument("--auto-key", choices=("none", "corners", "border"), default="none", help="从四角或完整边框自动取色")
    parser.add_argument("--tolerance", type=int, default=12, help="hard key 通道容差 0-255，默认 12")
    parser.add_argument("--soft-matte", action="store_true", help="生成连续 soft matte 并恢复 partial RGB")
    parser.add_argument(
        "--transparent-threshold",
        type=float,
        default=0.0,
        help="soft matte 中完全透明的最大键色距离，默认 0",
    )
    parser.add_argument(
        "--opaque-threshold",
        type=float,
        default=255.0,
        help="soft matte 中完全不透明的最小键色距离，默认 255",
    )
    parser.add_argument("--edge-contract", type=int, default=0, help="向内收缩 matte 0-16 pixels")
    parser.add_argument("--edge-feather", type=float, default=0.0, help="仅向主体内侧柔化 matte，radius 0-64")
    parser.add_argument("--border-connected", action="store_true", help="仅移除与图片边框连通的键色区域")
    parser.add_argument("--despill", dest="spill_cleanup", action="store_true", help="只对 partial edge 执行保守色溢清理")
    parser.add_argument("--spill-cleanup", dest="spill_cleanup", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="覆盖现有输出；仅在明确授权后使用")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    _validate_args(args)
    _remove_chroma_key(args)


if __name__ == "__main__":
    main()
