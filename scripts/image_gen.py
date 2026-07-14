#!/usr/bin/env python3
"""Validated Seedream 5.0 Pro/Lite CLI with single-submit billing safeguards."""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import http.client
from io import BytesIO
import json
import math
import os
import re
import signal
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Iterator


SKILL_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SKILL_DIR / ".env"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
PRO_MODEL = "doubao-seedream-5-0-pro-260628"
LITE_MODEL = "doubao-seedream-5-0-260128"
LITE_MODEL_ALIAS = "doubao-seedream-5-0-lite-260128"
DEFAULT_MODEL = "lite"
DEFAULT_SIZE = "2K"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_OUTPUT_DIRECTORY = Path(".")
DEFAULT_GROUP_OUTPUT_DIRECTORY = Path("images")
DEFAULT_OUTPUT_STEM = "seedream"
MAX_DEFAULT_OUTPUT_STEM_LENGTH = 64
MAX_PORTABLE_PATH_LENGTH = 240
MAX_INPUT_BYTES = 30_000_000
MAX_TOTAL_INPUT_BYTES = 120_000_000
MAX_REQUEST_BODY_BYTES = 170_000_000
MAX_OUTPUT_BYTES = 100_000_000
MAX_RESPONSE_BYTES = 512_000_000
MAX_ERROR_BYTES = 64_000
MAX_TOTAL_LITE_IMAGES = 15
MIN_ASPECT_RATIO = 1 / 16
MAX_ASPECT_RATIO = 16
MAX_INPUT_PIXELS = 36_000_000
MIN_SEED = -(2**31)
MAX_SEED = 2**31 - 1
ENV_KEYS = ("ARK_API_KEY", "ARK_BASE_URL", "ARK_PRO_MODEL", "ARK_LITE_MODEL")
API_KEY_PLACEHOLDERS = frozenset(
    {"your api key", "your-api-key", "replace-me", "changeme", "<api-key>"}
)
WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)
PORTABLE_INVALID_PATH_CHARS = frozenset('<>:"/\\|?*')
ROOT_PROMPT_NAME_PATTERN = re.compile(
    r"^\.seedream-prompt-[A-Za-z0-9][A-Za-z0-9_-]{5,63}\.txt$"
)

# 只有能够明确证明请求在生成前被参数校验拒绝的组合，才可清理付费请求状态。
# 扩充此白名单前必须补充 Ark 官方语义依据和状态文件测试。
REJECTED_HTTP_ARK_CODES = frozenset(
    {
        (400, "BadRequest"),
        (400, "InvalidParameter"),
    }
)

SUPPORTED_INPUT_SUBTYPES = {"jpeg", "png", "webp", "bmp", "tiff", "gif", "heic", "heif"}
PIL_FORMAT_TO_SUBTYPE = {
    "JPEG": "jpeg",
    "PNG": "png",
    "WEBP": "webp",
    "BMP": "bmp",
    "TIFF": "tiff",
    "GIF": "gif",
    "HEIF": "heif",
    "HEIC": "heic",
}
LOCAL_SUFFIX_TO_SUBTYPE = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
    ".bmp": "bmp",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".gif": "gif",
    ".heic": "heic",
    ".heif": "heif",
}


@dataclass(frozen=True, slots=True)
class ModelProfile:
    tier: str
    model_id: str
    size_tiers: frozenset[str]
    min_output_pixels: int
    max_output_pixels: int
    max_input_images: int
    supports_groups: bool
    supports_stream: bool
    supports_web_search: bool


MODEL_PROFILES = {
    "pro": ModelProfile(
        tier="pro",
        model_id=PRO_MODEL,
        size_tiers=frozenset({"1K", "2K"}),
        min_output_pixels=921_600,
        max_output_pixels=4_624_220,
        max_input_images=10,
        supports_groups=False,
        supports_stream=False,
        supports_web_search=False,
    ),
    "lite": ModelProfile(
        tier="lite",
        model_id=LITE_MODEL,
        size_tiers=frozenset({"2K", "3K", "4K"}),
        min_output_pixels=3_686_400,
        max_output_pixels=16_777_216,
        max_input_images=14,
        supports_groups=True,
        supports_stream=True,
        supports_web_search=True,
    ),
}

NAMED_TIER_PIXEL_RANGES = {
    "1K": (921_600, 1_638_400),
    "2K": (3_686_400, 4_624_220),
    "3K": (8_294_400, 10_485_760),
    "4K": (14_745_600, 16_777_216),
}


@dataclass(frozen=True, slots=True)
class OutputPlan:
    group: bool
    display_path: Path
    targets: tuple[Path, ...]
    state_path: Path


@dataclass(frozen=True, slots=True)
class ArkConfig:
    api_key: str
    base_url: str
    sources: dict[str, str]
    pro_model: str = PRO_MODEL
    lite_model: str = LITE_MODEL


class ArkRequestError(RuntimeError):
    """A safe Ark request error with retry ambiguity metadata."""

    def __init__(self, message: str, *, ambiguous: bool) -> None:
        super().__init__(message)
        self.ambiguous = ambiguous


def load_config(
    path: Path | None = None, *, environ: dict[str, str] | None = None
) -> ArkConfig:
    """Read Ark configuration without mutating the process environment."""
    env_path = path or ENV_FILE
    process_env = os.environ if environ is None else environ
    values = {key: "" for key in ENV_KEYS}
    sources = {key: "unset" for key in ENV_KEYS}
    if env_path.exists():
        try:
            # utf-8-sig 同时兼容普通 UTF-8 与 Windows 编辑器常见的 UTF-8 BOM。
            lines = env_path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"无法读取 skill-local .env：{env_path}（{exc}）") from None
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key in ENV_KEYS and value:
                values[key] = value
                sources[key] = "skill-local .env"
    # 进程环境优先，便于 CI、容器和不同电脑在不改安装目录的情况下覆盖配置。
    for key in ENV_KEYS:
        process_value = process_env.get(key, "").strip()
        if process_value:
            values[key] = process_value
            sources[key] = "process environment"
    for key in ("ARK_BASE_URL", "ARK_PRO_MODEL", "ARK_LITE_MODEL"):
        if sources[key] == "unset":
            sources[key] = "default"
    return ArkConfig(
        api_key=values["ARK_API_KEY"],
        base_url=_normalize_base_url(values["ARK_BASE_URL"] or DEFAULT_BASE_URL),
        sources=sources,
        pro_model=_normalize_model_id(values["ARK_PRO_MODEL"] or PRO_MODEL, "ARK_PRO_MODEL"),
        lite_model=_normalize_model_id(
            values["ARK_LITE_MODEL"] or LITE_MODEL, "ARK_LITE_MODEL"
        ),
    )


def _process_config() -> ArkConfig:
    """Build a no-disk configuration snapshot for helpers and injected tests."""
    values = {key: os.getenv(key, "").strip() for key in ENV_KEYS}
    return ArkConfig(
        api_key=values["ARK_API_KEY"],
        base_url=_normalize_base_url(values["ARK_BASE_URL"] or DEFAULT_BASE_URL),
        sources={
            "ARK_API_KEY": "process environment" if values["ARK_API_KEY"] else "unset",
            "ARK_BASE_URL": "process environment" if values["ARK_BASE_URL"] else "default",
            "ARK_PRO_MODEL": "process environment" if values["ARK_PRO_MODEL"] else "default",
            "ARK_LITE_MODEL": "process environment" if values["ARK_LITE_MODEL"] else "default",
        },
        pro_model=_normalize_model_id(values["ARK_PRO_MODEL"] or PRO_MODEL, "ARK_PRO_MODEL"),
        lite_model=_normalize_model_id(
            values["ARK_LITE_MODEL"] or LITE_MODEL, "ARK_LITE_MODEL"
        ),
    )


def die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _normalize_model_id(value: str, key: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 256
        or any(character.isspace() or ord(character) < 32 for character in normalized)
    ):
        die(f"{key} 必须是 1–256 个不含空白或控制字符的模型 ID。")
    return normalized


@lru_cache(maxsize=1)
def _load_pillow():
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        die("图片校验依赖 Pillow 未安装。请运行：python -m pip install Pillow")
    return Image, (UnidentifiedImageError, Image.DecompressionBombError)


@lru_cache(maxsize=1)
def _enable_heif_support() -> None:
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        die("处理 HEIC/HEIF 需要 pillow-heif。请运行：python -m pip install pillow-heif")
    register_heif_opener()


def _load_image_dependencies(subtype: str | None = None):
    if subtype in {"heic", "heif"}:
        _enable_heif_support()
    return _load_pillow()


def resolve_model(
    value: str | None,
    *,
    allow_fallback: bool = False,
    config: ArkConfig | None = None,
) -> tuple[ModelProfile, str]:
    pro_model = config.pro_model if config else PRO_MODEL
    lite_model = config.lite_model if config else LITE_MODEL
    requested = (value or DEFAULT_MODEL).strip()
    normalized = requested.lower()
    if normalized in {"pro", pro_model.lower()}:
        return replace(MODEL_PROFILES["pro"], model_id=pro_model), requested
    known_lite = {"", "lite", lite_model.lower(), LITE_MODEL_ALIAS.lower()}
    if normalized not in known_lite:
        if not allow_fallback:
            die(f"未识别模型 {requested!r}；请明确使用 lite 或 pro。")
        print(
            f"Warning: 未识别模型 {requested!r}，按规则回退到 Seedream 5.0 Lite。",
            file=sys.stderr,
        )
    return replace(MODEL_PROFILES["lite"], model_id=lite_model), requested


def read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if bool(prompt) == bool(prompt_file):
        die("必须且只能提供 --prompt 或 --prompt-file。")
    if prompt_file:
        path = Path(prompt_file)
        if not path.is_file():
            die(f"Prompt 文件不存在：{path}")
        try:
            prompt = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            die(f"无法读取 UTF-8 Prompt 文件：{path}（{exc}）")
    assert prompt is not None
    prompt = prompt.strip()
    if not prompt:
        die("Prompt 不能为空。")
    chinese_chars = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", prompt))
    english_words = len(re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)*", prompt))
    if chinese_chars > 300 or english_words > 600:
        print(
            f"Warning: Prompt 较长（中文字符 {chinese_chars}，英文单词 {english_words}）；"
            "官方建议不超过 300 个汉字或 600 个英文单词。",
            file=sys.stderr,
        )
    return prompt


def _normalize_pil_format(raw_format: str | None, declared_subtype: str | None = None) -> str:
    actual = PIL_FORMAT_TO_SUBTYPE.get((raw_format or "").upper())
    if actual == "heif" and declared_subtype == "heic":
        return "heic"
    if actual not in SUPPORTED_INPUT_SUBTYPES:
        die(f"不支持或无法识别的图片格式：{raw_format or 'unknown'}")
    return actual


def _validate_dimensions(width: int, height: int, *, source: str) -> None:
    if width <= 14 or height <= 14:
        die(f"输入图片宽和高必须均大于 14 px：{source} ({width}x{height})")
    ratio = width / height
    if not MIN_ASPECT_RATIO <= ratio <= MAX_ASPECT_RATIO:
        die(f"输入图片宽高比必须在 [1/16, 16]：{source} ({width}x{height})")
    if width * height > MAX_INPUT_PIXELS:
        die(f"输入图片总像素不得超过 36000000：{source} ({width}x{height})")


def _inspect_image_bytes(content: bytes, *, declared_subtype: str, source: str) -> str:
    if not content:
        die(f"输入图片为空：{source}")
    if len(content) > MAX_INPUT_BYTES:
        die(f"输入图片超过 30 MB：{source}")
    Image, image_errors = _load_image_dependencies(declared_subtype)
    try:
        with Image.open(BytesIO(content)) as image:
            actual_subtype = _normalize_pil_format(image.format, declared_subtype)
            width, height = image.size
            image.verify()
    except image_errors + (OSError, ValueError) as exc:
        die(f"输入图片损坏或无法解码：{source}（{exc}）")
    if actual_subtype != declared_subtype:
        die(
            f"输入图片声明格式与实际格式不一致：{source} "
            f"(声明 {declared_subtype}，实际 {actual_subtype})"
        )
    _validate_dimensions(width, height, source=source)
    return actual_subtype


def _validate_remote_url(value: str) -> str:
    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        die("输入图片 URL 不允许包含空白或控制字符。")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        die(f"输入图片 URL 无效：{value}")
    if parsed.username or parsed.password:
        die("输入图片 URL 不允许包含用户名或密码。")
    try:
        parsed.port
    except ValueError:
        die("输入图片 URL 端口无效。")
    return value


def _data_uri_to_api_value(value: str) -> str:
    match = re.fullmatch(r"data:image/([^;,]+);base64,(.*)", value, re.DOTALL)
    if not match:
        die("图片 data URI 必须使用 data:image/<格式>;base64,<Base64编码>。")
    subtype = match.group(1)
    if subtype != subtype.lower() or subtype not in SUPPORTED_INPUT_SUBTYPES:
        die("data URI 图片格式必须为受支持的小写格式名。")
    encoded = match.group(2)
    max_encoded_length = ((MAX_INPUT_BYTES + 2) // 3) * 4
    if len(encoded) > max_encoded_length:
        die("图片 data URI 解码后可能超过 30 MB。")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        die("图片 data URI 包含非法 Base64 数据。")
    _inspect_image_bytes(content, declared_subtype=subtype, source="data URI")
    return value


def image_to_api_value(value: str) -> str:
    if value.startswith("data:"):
        return _data_uri_to_api_value(value)
    if value.startswith(("http://", "https://")):
        return _validate_remote_url(value)
    path = Path(value)
    if not path.is_file():
        die(f"输入图片不存在：{path}")
    declared_subtype = LOCAL_SUFFIX_TO_SUBTYPE.get(path.suffix.lower())
    if declared_subtype is None:
        die(f"不支持的输入图片扩展名：{path.suffix or '<none>'}")
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            die(f"输入图片超过 30 MB：{path}")
        content = path.read_bytes()
    except OSError as exc:
        die(f"无法读取输入图片：{path}（{exc}）")
    _inspect_image_bytes(content, declared_subtype=declared_subtype, source=str(path))
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/{declared_subtype};base64,{encoded}"


def _preflight_image_payload(values: list[str]) -> None:
    raw_total = 0
    encoded_total = 0
    for value in values:
        if value.startswith(("http://", "https://")):
            encoded_total += len(value)
            continue
        if value.startswith("data:"):
            encoded = value.partition(",")[2]
            raw_total += ((len(encoded) + 3) // 4) * 3
            encoded_total += len(value)
            continue
        path = Path(value)
        try:
            size = path.stat().st_size
        except OSError as exc:
            die(f"无法读取输入图片属性：{path}（{exc}）")
        raw_total += size
        encoded_total += len("data:image/heif;base64,") + ((size + 2) // 3) * 4
    if raw_total > MAX_TOTAL_INPUT_BYTES:
        die(f"输入图片总大小超过 {MAX_TOTAL_INPUT_BYTES} bytes 聚合上限。")
    if encoded_total > MAX_REQUEST_BODY_BYTES:
        die(f"图片 payload 预计超过 {MAX_REQUEST_BODY_BYTES} bytes 请求体上限。")


def _estimate_json_bytes(value: Any) -> int:
    if isinstance(value, dict):
        return 2 + sum(
            len(str(key).encode("utf-8")) + 4 + _estimate_json_bytes(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return 2 + sum(_estimate_json_bytes(item) + 1 for item in value)
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return len(value) + 2
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _normalize_size(value: str, profile: ModelProfile | None = None) -> str:
    profile = profile or MODEL_PROFILES["pro"]
    tier_match = re.fullmatch(r"[1-4]k", value, re.IGNORECASE)
    if tier_match:
        normalized = value.upper()
        if normalized not in profile.size_tiers:
            allowed = "、".join(sorted(profile.size_tiers))
            die(f"Seedream 5.0 {profile.tier.title()} 分辨率档位只支持 {allowed}。")
        return normalized
    match = re.fullmatch(r"([1-9]\d*)x([1-9]\d*)", value)
    if not match:
        allowed = "、".join(sorted(profile.size_tiers))
        die(f"--size 只支持 {allowed} 或 WIDTHxHEIGHT。")
    width, height = map(int, match.groups())
    pixels = width * height
    ratio = width / height
    if not profile.min_output_pixels <= pixels <= profile.max_output_pixels:
        die(
            f"Seedream 5.0 {profile.tier.title()} 自定义输出总像素必须在 "
            f"{profile.min_output_pixels} 到 {profile.max_output_pixels} 之间："
            f"{width}x{height}={pixels}"
        )
    if not MIN_ASPECT_RATIO <= ratio <= MAX_ASPECT_RATIO:
        die(f"自定义输出尺寸宽高比必须在 [1/16, 16]：{width}x{height}")
    return f"{width}x{height}"


def _normalize_base_url(value: str | None = None) -> str:
    raw = (value or DEFAULT_BASE_URL).strip().rstrip("/")
    if not raw or any(character.isspace() or ord(character) < 32 for character in raw):
        die("ARK_BASE_URL 不能为空或包含空白、控制字符。")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        die("ARK_BASE_URL 必须是有效的 HTTP(S) 基础地址。")
    if parsed.username or parsed.password:
        die("ARK_BASE_URL 不允许包含用户名或密码。")
    if parsed.query or parsed.fragment:
        die("ARK_BASE_URL 不允许包含查询参数或片段。")
    try:
        parsed.port
    except ValueError:
        die("ARK_BASE_URL 端口无效。")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        die("ARK_BASE_URL 仅允许 HTTPS；本地测试地址可使用 HTTP。")
    return raw


def _config_sources(config: ArkConfig) -> dict[str, str]:
    return dict(config.sources)


def validate_args(args: argparse.Namespace, config: ArkConfig | None = None) -> None:
    config = config or _process_config()
    profile, requested = resolve_model(
        args.model,
        allow_fallback=getattr(args, "allow_model_fallback", False),
        config=config,
    )
    args.model_profile = profile
    args.requested_model = requested
    if args.guidance_scale is not None:
        if not math.isfinite(args.guidance_scale) or not 1 <= args.guidance_scale <= 10:
            die("--guidance-scale 必须是 1 到 10 之间的有限数值。")
    if args.seed is not None and not MIN_SEED <= args.seed <= MAX_SEED:
        die(f"--seed 必须是 {MIN_SEED} 到 {MAX_SEED} 之间的整数。")
    if args.timeout < 1:
        die("--timeout 必须大于 0。")
    if args.cleanup_prompt_file and not args.prompt_file:
        die("--cleanup-prompt-file 只能与 --prompt-file 一起使用。")
    args.resolved_prompt = read_prompt(args.prompt, args.prompt_file)
    if args.cleanup_prompt_file:
        _validate_prompt_cleanup_path(args)
    args.base_url = config.base_url
    images = args.image or []
    if len(images) > profile.max_input_images:
        die(
            f"Seedream 5.0 {profile.tier.title()} 最多支持 "
            f"{profile.max_input_images} 张参考图。"
        )
    args.size = _normalize_size(args.size, profile)
    if not profile.supports_groups and args.sequential != "disabled":
        die("Seedream 5.0 Pro 不支持组图输出。")
    if not profile.supports_stream and args.stream:
        die("Seedream 5.0 Pro 不支持流式输出。")
    if not profile.supports_web_search and args.web_search:
        die("Seedream 5.0 Pro 不支持模型原生联网搜索。")

    if args.sequential == "auto":
        if args.max_images is None:
            die("--sequential auto 必须同时指定 --max-images。")
        if args.out:
            die("组图模式使用 --out-dir，不能同时使用 --out。")
        max_allowed = MAX_TOTAL_LITE_IMAGES - len(images)
        if not 1 <= args.max_images <= max_allowed:
            die(
                "Seedream 5.0 Lite 要求参考图数量 + 最终生成图片数量不超过 15；"
                f"当前最多可生成 {max_allowed} 张。"
            )
    else:
        if args.max_images is not None:
            die("--max-images 仅可与 --sequential auto 一起使用。")
        if args.out_dir:
            die("单图模式使用 --out，不能使用 --out-dir。")


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    profile = args.model_profile
    payload: dict[str, Any] = {
        "model": profile.model_id,
        "prompt": args.resolved_prompt,
        "size": args.size,
        "response_format": args.response_format,
        "watermark": args.watermark,
        "output_format": args.output_format,
    }
    if args.image:
        _preflight_image_payload(args.image)
        images = [image_to_api_value(item) for item in args.image]
        payload["image"] = images[0] if len(images) == 1 else images
    if args.seed is not None:
        payload["seed"] = args.seed
    if args.guidance_scale is not None:
        payload["guidance_scale"] = args.guidance_scale
    if profile.tier == "lite":
        payload["sequential_image_generation"] = args.sequential
        if args.sequential == "auto":
            payload["sequential_image_generation_options"] = {"max_images": args.max_images}
        if args.web_search:
            payload["tools"] = [{"type": "web_search"}]
        if args.stream:
            payload["stream"] = True
    if _estimate_json_bytes(payload) > MAX_REQUEST_BODY_BYTES:
        die(f"完整请求体预计超过 {MAX_REQUEST_BODY_BYTES} bytes 安全上限。")
    return payload


def preview_payload(
    payload: dict[str, Any], *, secrets: Iterable[str] = ()
) -> dict[str, Any]:
    preview = dict(payload)
    images = preview.get("image")
    if images:
        is_list = isinstance(images, list)
        values = images if is_list else [images]
        redacted = [
            f"<base64 image: {len(item)} chars>"
            if item.startswith("data:image/")
            else "<remote image URL>"
            for item in values
        ]
        preview["image"] = redacted if is_list else redacted[0]
    return _scrub_structure(preview, secrets=secrets)


def _output_suffix(output_format: str) -> str:
    return ".png" if output_format == "png" else ".jpeg"


def _prompt_output_stem(prompt: str) -> str:
    """Build a portable, readable filename stem from the request prompt."""
    compact = re.sub(r"\s+", "-", prompt.strip())
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", compact)
    safe = re.sub(r"[^\w.-]+", "-", safe, flags=re.UNICODE)
    safe = re.sub(r"[-. ]{2,}", "-", safe).strip(" .-")
    safe = safe[:MAX_DEFAULT_OUTPUT_STEM_LENGTH].rstrip(" .-")
    return safe or DEFAULT_OUTPUT_STEM


def _selected_output_stem(prompt: str, private: bool) -> str:
    if private:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        return f"{DEFAULT_OUTPUT_STEM}-{digest}"
    return _prompt_output_stem(prompt)


def _validate_portable_target(path: Path) -> None:
    anchor = path.anchor
    components = [
        part for part in path.parts if part not in {anchor, "", ".", ".."}
    ]
    if not components:
        die(f"输出路径缺少文件名：{path}")
    for component in components:
        if component.endswith((" ", ".")):
            die(f"输出路径组件不能以空格或句点结尾：{component}")
        if any(
            ord(character) < 32 or character in PORTABLE_INVALID_PATH_CHARS
            for character in component
        ):
            die(f"输出路径组件包含不可移植字符：{component}")
        # Windows 设备名在第一个句点前即生效，例如 CON.png、CON.extra.png。
        if component.split(".", 1)[0].upper() in WINDOWS_RESERVED_STEMS:
            die(f"输出路径组件是 Windows 保留名：{component}")
        if len(component.encode("utf-8")) > 255:
            die(f"输出路径组件过长：{component}")
    if len(str(path.resolve(strict=False))) > MAX_PORTABLE_PATH_LENGTH:
        die(f"输出路径超过 {MAX_PORTABLE_PATH_LENGTH} 字符可移植上限：{path}")


def _next_default_output_path(prompt: str, suffix: str, *, private: bool = False) -> Path:
    """Return a non-conflicting prompt-derived path in the current project."""
    stem = _selected_output_stem(prompt, private)
    candidate = DEFAULT_OUTPUT_DIRECTORY / f"{stem}{suffix}"
    version = 2
    while candidate.exists():
        candidate = DEFAULT_OUTPUT_DIRECTORY / f"{stem}-v{version}{suffix}"
        version += 1
    return candidate


def _default_group_targets(
    prompt: str, suffix: str, count: int, *, private: bool = False
) -> tuple[Path, tuple[Path, ...]]:
    """Return a non-conflicting prompt-derived group under the project images directory."""
    stem = _selected_output_stem(prompt, private)
    version = 1
    while True:
        group_stem = stem if version == 1 else f"{stem}-v{version}"
        targets = tuple(
            DEFAULT_GROUP_OUTPUT_DIRECTORY / f"{group_stem}-{index:02d}{suffix}"
            for index in range(1, count + 1)
        )
        if not any(path.exists() for path in targets):
            return DEFAULT_GROUP_OUTPUT_DIRECTORY, targets
        version += 1


def _default_group_state_path(prompt: str, *, private: bool = False) -> Path:
    """Scope default-group recovery state to the exact prompt, not all of images/."""
    stem = _selected_output_stem(prompt, private)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    return DEFAULT_GROUP_OUTPUT_DIRECTORY / f".{stem}-{prompt_hash}.seedream-request.json"


def _resolved_prompt(args: argparse.Namespace) -> str:
    prompt = getattr(args, "resolved_prompt", None)
    return prompt if prompt is not None else read_prompt(args.prompt, args.prompt_file)


def output_path(args: argparse.Namespace, *, check_conflicts: bool = True) -> Path:
    suffix = _output_suffix(args.output_format)
    prompt = _resolved_prompt(args)
    path = (
        Path(args.out)
        if args.out
        else _next_default_output_path(
            prompt, suffix, private=getattr(args, "private_filenames", False)
        )
    )
    if not path.suffix:
        path = path.with_suffix(suffix)
    allowed = {".png"} if args.output_format == "png" else {".jpg", ".jpeg"}
    if path.suffix.lower() not in allowed:
        die(
            f"输出扩展名 {path.suffix} 与 --output-format {args.output_format} 不一致；"
            f"请使用 {', '.join(sorted(allowed))}。"
        )
    _validate_portable_target(path)
    if path.exists() and not path.is_file():
        die(f"输出路径不是文件：{path}")
    if check_conflicts and path.exists() and not args.force:
        die(
            f"输出文件已存在：{path}。请改用新文件名；"
            "仅在用户明确授权覆盖时使用 --force。"
        )
    return path


def build_output_plan(args: argparse.Namespace, *, check_conflicts: bool = True) -> OutputPlan:
    if args.sequential == "auto":
        suffix = _output_suffix(args.output_format)
        if args.out_dir:
            directory = Path(args.out_dir)
            targets = tuple(
                directory / f"image-{index:02d}{suffix}"
                for index in range(1, args.max_images + 1)
            )
            state_path = directory / ".seedream-request.json"
        else:
            prompt = _resolved_prompt(args)
            private = getattr(args, "private_filenames", False)
            directory, targets = _default_group_targets(
                prompt, suffix, args.max_images, private=private
            )
            state_path = _default_group_state_path(prompt, private=private)
        if directory.exists() and not directory.is_dir():
            die(f"组图输出路径不是目录：{directory}")
        invalid_targets = [path for path in targets if path.exists() and not path.is_file()]
        if invalid_targets:
            die(f"组图目标路径不是文件：{invalid_targets[0]}")
        for target in targets:
            _validate_portable_target(target)
        conflicts = [path for path in targets if path.exists()]
        if check_conflicts and conflicts and not args.force:
            die(
                f"组图目标文件已存在：{conflicts[0]}。请改用新目录；"
                "仅在用户明确授权覆盖时使用 --force。"
            )
        return OutputPlan(
            group=True,
            display_path=directory,
            targets=targets,
            state_path=state_path,
        )
    path = output_path(args, check_conflicts=check_conflicts)
    return OutputPlan(
        group=False,
        display_path=path,
        targets=(path,),
        state_path=_request_state_path(path),
    )


def prepare_output_destination(plan: OutputPlan) -> None:
    """Create and verify the destination before a billable API request."""
    directory = plan.display_path if plan.group else plan.display_path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".seedream-write-test-", delete=True
        ):
            pass
    except OSError as exc:
        die(f"输出目录不可写：{directory}（{exc}）")


def _dry_run_diagnostics(plan: OutputPlan, args: argparse.Namespace) -> dict[str, Any]:
    conflicts = [str(path) for path in plan.targets if path.exists()]
    return {
        "output_conflicts": conflicts,
        "force_requested": bool(args.force),
        "request_state": "present" if plan.state_path.exists() else "absent",
        "billable_request_blocked": bool(plan.state_path.exists()),
    }


SENSITIVE_FIELD_NAMES = frozenset(
    {"authorization", "cookie", "set-cookie", "api_key", "access_token", "token", "secret"}
)


def _redact_message(value: str, api_key: str = "") -> str:
    if api_key:
        value = value.replace(api_key, "<redacted>")
    value = re.sub(r"data:image/[^;,]+;base64,[A-Za-z0-9+/=\r\n]+", "<redacted-data-uri>", value)
    value = re.sub(r"https?://[^\s\"']+", "<redacted-url>", value)
    return value[:500]


def _scrub_structure(
    value: Any, *, secrets: Iterable[str] = (), field_name: str = ""
) -> Any:
    if field_name.casefold() in SENSITIVE_FIELD_NAMES:
        return "<redacted>"
    if isinstance(value, dict):
        return {
            key: _scrub_structure(item, secrets=secrets, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_structure(item, secrets=secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_structure(item, secrets=secrets) for item in value)
    if isinstance(value, str):
        scrubbed = value
        for secret in secrets:
            if secret:
                scrubbed = scrubbed.replace(secret, "<redacted>")
        return _redact_message(scrubbed)
    return value


def _safe_http_error(exc: urllib.error.HTTPError, api_key: str) -> tuple[str, str]:
    body = exc.read(MAX_ERROR_BYTES).decode("utf-8", errors="replace")
    code = ""
    request_id = ""
    message = body
    try:
        parsed = json.loads(body)
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, dict):
            code = str(error.get("code") or "")
            message = str(error.get("message") or body)
            request_id = str(error.get("request_id") or "")
        if isinstance(parsed, dict):
            request_id = request_id or str(parsed.get("request_id") or "")
    except json.JSONDecodeError:
        pass
    details = [f"HTTP {exc.code}"]
    if code:
        details.append(f"code={code}")
    if request_id:
        details.append(f"request_id={request_id}")
    details.append(_redact_message(message, api_key))
    return "；".join(details), code


def classify_submission_outcome(http_status: int, ark_code: str) -> str:
    """Classify whether an HTTP response proves the billable work was rejected."""
    if (http_status, ark_code) in REJECTED_HTTP_ARK_CODES:
        return "rejected"
    return "ambiguous"


def _request_state_path(path: Path) -> Path:
    return path.parent / f".{path.name}.seedream-request.json"


def _request_fingerprint(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256()

    def update(value: Any) -> None:
        if isinstance(value, dict):
            digest.update(b"{")
            for key in sorted(value):
                update(str(key))
                update(value[key])
            digest.update(b"}")
        elif isinstance(value, (list, tuple)):
            digest.update(b"[")
            for item in value:
                update(item)
            digest.update(b"]")
        elif isinstance(value, str):
            digest.update(b"s")
            if value.startswith("data:image/"):
                digest.update(len(value).to_bytes(8, "big"))
                for offset in range(0, len(value), 1_048_576):
                    digest.update(value[offset : offset + 1_048_576].encode("ascii"))
            else:
                encoded = value.encode("utf-8")
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
        else:
            digest.update(b"v")
            digest.update(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))

    update(payload)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_request_state(state_path: Path, state: dict[str, Any], *, create: bool = False) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if create:
        try:
            with state_path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            return
        except FileExistsError:
            die(
                f"检测到未完成或状态未知的付费请求：{state_path}。不得自动重试；"
                "请先核实输出和计费状态，确认接受可能的重复计费后再手动删除该状态文件。"
            )
        except OSError as exc:
            die(f"无法创建请求状态文件：{state_path}（{exc}）")

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            suffix=".tmp",
        ) as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, state_path)
        temporary = None
    except OSError as exc:
        die(f"无法更新请求状态文件：{state_path}（{exc}）")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _new_request_state(
    plan: OutputPlan, payload: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    state = {
        "version": 1,
        "status": "pending",
        "payload_sha256": _request_fingerprint(payload),
        "output": str(plan.display_path.resolve()),
        "started_at": _utc_now(),
        "pid": os.getpid(),
    }
    _write_request_state(plan.state_path, state, create=True)
    return plan.state_path, state


def _mark_request_ambiguous(
    state_path: Path,
    state: dict[str, Any],
    reason: str,
    *,
    api_key: str = "",
) -> None:
    state["status"] = "ambiguous"
    state["updated_at"] = _utc_now()
    state["reason"] = _redact_message(reason, api_key or os.getenv("ARK_API_KEY", "").strip())
    _write_request_state(state_path, state)


def _ensure_no_request_state(plan: OutputPlan) -> None:
    if plan.state_path.exists():
        die(
            f"检测到未完成或状态未知的付费请求：{plan.state_path}。不得自动重试；"
            "请先核实输出和计费状态，确认接受可能的重复计费后再手动删除该状态文件。"
        )


def _cleanup_prompt_file(args: argparse.Namespace) -> None:
    """Remove an explicitly designated agent-owned prompt and empty temp dirs."""
    if not args.cleanup_prompt_file or not args.prompt_file:
        return
    try:
        prompt_path = _validate_prompt_cleanup_path(args)
    except SystemExit:
        print("Warning: prompt 临时文件 ownership 已变化，拒绝自动删除。", file=sys.stderr)
        return
    try:
        prompt_path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"Warning: 已完成生成，但无法清理临时 prompt 文件：{args.prompt_file}（{exc}）", file=sys.stderr)
        return

    project_dir = _project_directory(args)
    owned_root = (project_dir / "tmp" / "seedream").resolve(strict=False)
    if not prompt_path.is_relative_to(owned_root):
        return
    current = prompt_path.parent
    while current.is_relative_to(owned_root):
        try:
            current.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            break
        if current == owned_root:
            break
        current = current.parent

    # 只在 agent 临时根已经为空并被删除后，顺带删除空的 project/tmp；
    # rmdir 不会删除含有其他文件或目录的用户内容。
    if not owned_root.exists():
        try:
            owned_root.parent.rmdir()
        except (FileNotFoundError, OSError):
            pass


def _project_directory(args: argparse.Namespace) -> Path:
    return Path(
        getattr(args, "project_dir", None)
        or os.getenv("CLAUDE_PROJECT_DIR", "")
        or Path.cwd()
    ).resolve(strict=False)


def _validate_prompt_cleanup_path(args: argparse.Namespace) -> Path:
    path = Path(args.prompt_file)
    project_dir = _project_directory(args)
    owned_root = (project_dir / "tmp" / "seedream").resolve(strict=False)
    resolved = path.resolve(strict=False)
    lexical = path.absolute()
    unsafe_link = False
    for candidate in (lexical, *lexical.parents):
        if candidate.is_symlink() or (
            hasattr(candidate, "is_junction") and candidate.is_junction()
        ):
            unsafe_link = True
            break
        if candidate == project_dir:
            break
    if unsafe_link or not path.is_file():
        die("--cleanup-prompt-file 只允许删除现存的普通非 symlink 文件。")
    root_owned = (
        resolved.parent == project_dir
        and ROOT_PROMPT_NAME_PATTERN.fullmatch(resolved.name) is not None
    )
    legacy_owned = resolved.is_relative_to(owned_root)
    if not root_owned and not legacy_owned:
        die(
            "--cleanup-prompt-file 仅允许项目根目录下名为 "
            ".seedream-prompt-<random-id>.txt 的 agent 临时文件；"
            f"旧版目录 {owned_root} 仅保留兼容。"
        )
    conflicts = [getattr(args, "out", None), *(getattr(args, "image", None) or [])]
    for conflict in conflicts:
        if conflict and not str(conflict).startswith(("http://", "https://", "data:")):
            if Path(conflict).resolve(strict=False) == resolved:
                die("prompt 临时文件不得与输入图片或输出路径相同。")
    return resolved


def _ensure_prompt_cleanup_not_plan_conflict(
    args: argparse.Namespace, plan: OutputPlan
) -> None:
    if not args.cleanup_prompt_file:
        return
    prompt_path = Path(args.prompt_file).resolve(strict=False)
    protected = (*plan.targets, plan.state_path)
    if any(path.resolve(strict=False) == prompt_path for path in protected):
        die("prompt 临时文件不得与输出目标或请求状态文件相同。")


def _require_api_key(config: ArkConfig) -> None:
    if not config.api_key or config.api_key.casefold() in API_KEY_PLACEHOLDERS:
        die(f"ARK_API_KEY 为空。请填写 {ENV_FILE} 或设置环境变量。")


def _api_request_object(
    payload: dict[str, Any], config: ArkConfig, *, stream: bool
) -> urllib.request.Request:
    return urllib.request.Request(
        f"{config.base_url}/images/generations",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        },
        method="POST",
    )


@contextmanager
def _api_response(
    payload: dict[str, Any], timeout: int, *, stream: bool, config: ArkConfig | None = None
) -> Iterator[Any]:
    config = config or _process_config()
    api_key = config.api_key
    if not api_key:
        raise ArkRequestError(
            f"ARK_API_KEY 为空。请填写 {ENV_FILE} 或设置环境变量。", ambiguous=False
        )
    request = _api_request_object(payload, config, stream=stream)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            yield response
    except urllib.error.HTTPError as exc:
        details, ark_code = _safe_http_error(exc, api_key)
        outcome = classify_submission_outcome(exc.code, ark_code)
        raise ArkRequestError(
            f"Ark API 请求失败：{details}", ambiguous=outcome != "rejected"
        ) from None
    except urllib.error.URLError as exc:
        raise ArkRequestError(
            f"无法连接 Ark API：{_redact_message(str(exc.reason), api_key)}",
            ambiguous=True,
        ) from None
    except TimeoutError:
        raise ArkRequestError(f"Ark API 请求超过 {timeout} 秒。", ambiguous=True) from None
    except (OSError, http.client.HTTPException) as exc:
        raise ArkRequestError(
            f"Ark API 连接中断：{_redact_message(str(exc), api_key)}", ambiguous=True
        ) from None


def api_request(
    payload: dict[str, Any], timeout: int, config: ArkConfig | None = None
) -> dict[str, Any]:
    try:
        with _api_response(payload, timeout, stream=False, config=config) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ArkRequestError("Ark API 响应超过安全上限。", ambiguous=True)
        result = json.loads(raw.decode("utf-8"))
        if not isinstance(result, dict):
            raise ArkRequestError("Ark API 返回的 JSON 顶层不是对象。", ambiguous=True)
        return result
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArkRequestError(f"Ark API 返回了无效 JSON：{exc}", ambiguous=True) from None


def _decode_sse_events(lines: Iterable[bytes]) -> Iterator[dict[str, Any]]:
    data_lines: list[str] = []
    total = 0

    def flush() -> dict[str, Any] | None:
        if not data_lines:
            return None
        raw = "\n".join(data_lines).strip()
        data_lines.clear()
        if not raw or raw == "[DONE]":
            return None
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ArkRequestError(f"Ark 流式响应包含无效 JSON：{exc}", ambiguous=True) from None
        if not isinstance(event, dict):
            raise ArkRequestError("Ark 流式事件不是 JSON 对象。", ambiguous=True)
        return event

    for raw_line in lines:
        total += len(raw_line)
        if total > MAX_RESPONSE_BYTES:
            raise ArkRequestError("Ark 流式响应超过安全上限。", ambiguous=True)
        try:
            line = raw_line.decode("utf-8").rstrip("\r\n")
        except UnicodeError as exc:
            raise ArkRequestError(f"Ark 流式响应不是有效 UTF-8：{exc}", ambiguous=True) from None
        if not line:
            event = flush()
            if event is not None:
                yield event
        elif line.startswith(":"):
            continue
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.lstrip().startswith("{"):
            event = flush()
            if event is not None:
                yield event
            data_lines.append(line.strip())
            event = flush()
            if event is not None:
                yield event
    event = flush()
    if event is not None:
        yield event


def api_stream(
    payload: dict[str, Any], timeout: int, config: ArkConfig | None = None
) -> Iterator[dict[str, Any]]:
    with _api_response(payload, timeout, stream=True, config=config) as response:
        yield from _decode_sse_events(response)


def download_bytes(url: str, timeout: int, attempts: int = 3) -> bytes:
    request = urllib.request.Request(
        _validate_remote_url(url),
        headers={"Accept": "image/*", "User-Agent": "seedream-imagegen/1"},
    )
    last_error = "unknown"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > MAX_OUTPUT_BYTES:
                            die("生成图片超过 100 MB 安全上限。")
                    except ValueError:
                        pass
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_OUTPUT_BYTES:
                        die("生成图片超过 100 MB 安全上限。")
                    chunks.append(chunk)
                return b"".join(chunks)
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code < 500 or attempt == attempts:
                break
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            http.client.HTTPException,
        ) as exc:
            last_error = _redact_message(str(exc))
            if attempt == attempts:
                break
        time.sleep(0.2 * attempt)
    die(f"下载生成图片失败（已尝试 {attempts} 次）：{last_error}")
    return b""


def _validate_generated_image(content: bytes, args: argparse.Namespace) -> None:
    expected = "png" if args.output_format == "png" else "jpeg"
    Image, image_errors = _load_image_dependencies()
    try:
        with Image.open(BytesIO(content)) as image:
            actual = PIL_FORMAT_TO_SUBTYPE.get((image.format or "").upper())
            width, height = image.size
            image.verify()
    except image_errors + (OSError, ValueError) as exc:
        die(f"生成结果不是有效图片：{exc}")
    if actual != expected:
        die(f"生成结果格式与请求不一致：请求 {expected}，实际 {actual or 'unknown'}")
    profile = getattr(args, "model_profile", resolve_model(getattr(args, "model", None))[0])
    if "x" in args.size.lower():
        expected_width, expected_height = map(int, args.size.lower().split("x", 1))
        if (width, height) != (expected_width, expected_height):
            die(
                "生成结果尺寸与自定义请求不一致："
                f"请求 {expected_width}x{expected_height}，实际 {width}x{height}"
            )
    else:
        pixels = width * height
        ratio = width / height
        minimum, maximum = NAMED_TIER_PIXEL_RANGES[args.size.upper()]
        if not minimum <= pixels <= maximum:
            die(
                f"生成结果尺寸不符合 {args.size.upper()} 档位："
                f"{width}x{height}={pixels}，期望 {minimum} 到 {maximum} pixels"
            )
        if not MIN_ASPECT_RATIO <= ratio <= MAX_ASPECT_RATIO:
            die(f"生成结果宽高比超出 [1/16, 16]：{width}x{height}")


def _atomic_write(path: Path, content: bytes, *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        if force:
            os.replace(temporary, path)
            temporary = None
        else:
            os.link(temporary, path)
    except FileExistsError:
        die(f"保存前检测到输出文件已被创建，拒绝覆盖：{path}")
    except OSError as exc:
        die(f"无法保存生成图片：{path}（{exc}）")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _item_bytes(item: dict[str, Any], args: argparse.Namespace) -> bytes:
    if item.get("b64_json"):
        encoded = item["b64_json"]
        if not isinstance(encoded, str):
            die("Ark API 返回的 b64_json 不是字符串。")
        if len(encoded) > ((MAX_OUTPUT_BYTES + 2) // 3) * 4:
            die("Ark API 返回的 Base64 图片超过 100 MB 安全上限。")
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError, ValueError):
            die("Ark API 返回了非法 Base64 图片数据。")
    if item.get("url"):
        return download_bytes(str(item["url"]), args.timeout)
    die("Ark API 图片项缺少 url 或 b64_json。")
    return b""


def _save_item(item: dict[str, Any], args: argparse.Namespace, path: Path) -> Path:
    content = _item_bytes(item, args)
    _validate_generated_image(content, args)
    _atomic_write(path, content, force=args.force)
    print(path.resolve())
    return path


def save_response(
    result: dict[str, Any], args: argparse.Namespace, plan: OutputPlan
) -> list[Path]:
    data = result.get("data")
    if not isinstance(data, list):
        die("Ark API 返回的 data 不是数组。")
    if plan.group:
        if not 1 <= len(data) <= len(plan.targets):
            die(
                f"Seedream 5.0 Lite 组图应返回 1 到 {len(plan.targets)} 张图片，"
                f"实际 data 数量：{len(data)}"
            )
    elif len(data) != 1:
        die(f"单图模式应返回且只返回一张图片，实际 data 数量：{len(data)}")
    saved: list[Path] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            die("Ark API 图片项不是对象。")
        saved.append(_save_item(item, args, plan.targets[index]))
    return saved


def _stream_item(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    if isinstance(data, dict):
        return data
    return event


def save_stream_response(
    events: Iterable[dict[str, Any]], args: argparse.Namespace, plan: OutputPlan
) -> list[Path]:
    saved: list[Path] = []
    completed = False
    seen: set[str] = set()
    partial_errors: list[str] = []
    for event in events:
        event_type = str(event.get("type") or "")
        if event_type == "image_generation.partial_image":
            continue
        if event_type == "image_generation.partial_failed":
            error = event.get("error") if isinstance(event.get("error"), dict) else {}
            code = str(error.get("code") or "unknown")
            message = _redact_message(str(error.get("message") or "partial failure"))
            partial_errors.append(f"{code}: {message}")
            print(f"Warning: 流式图片生成部分失败：{code}: {message}", file=sys.stderr)
            if code == "InternalServiceError":
                raise ArkRequestError("Ark 流式生成发生 InternalServiceError。", ambiguous=True)
            continue
        if event_type == "image_generation.partial_succeeded":
            item = _stream_item(event)
            image_index = event.get("image_index", event.get("partial_image_index"))
            if image_index is not None:
                token_source = f"index:{image_index}"
            elif item.get("url"):
                token_source = f"url:{item['url']}"
            elif item.get("b64_json"):
                token_source = f"base64:{item['b64_json']}"
            else:
                die("Ark 流式成功事件缺少图片数据。")
            token = hashlib.sha256(token_source.encode("utf-8")).hexdigest()
            if token in seen:
                continue
            seen.add(token)
            if len(saved) >= len(plan.targets):
                die(f"流式响应图片数量超过计划上限 {len(plan.targets)}。")
            saved.append(_save_item(item, args, plan.targets[len(saved)]))
            continue
        if event_type == "image_generation.completed":
            completed = True
            usage = event.get("usage")
            if isinstance(usage, dict):
                print(f"Usage: {json.dumps(usage, ensure_ascii=False)}", file=sys.stderr)
    if not completed:
        raise ArkRequestError("Ark 流式响应未收到 completed 事件。", ambiguous=True)
    if not saved:
        detail = f"；部分错误：{' | '.join(partial_errors)}" if partial_errors else ""
        raise ArkRequestError(f"Ark 流式响应没有成功图片{detail}", ambiguous=True)
    if not plan.group and len(saved) != 1:
        raise ArkRequestError("单图流式响应返回了多张图片。", ambiguous=True)
    return saved


def _run(args: argparse.Namespace) -> None:
    config = load_config()
    validate_args(args, config)
    plan = build_output_plan(args, check_conflicts=not args.dry_run)
    _ensure_prompt_cleanup_not_plan_conflict(args, plan)
    payload = build_payload(args)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "endpoint": "/images/generations",
                    "requested_model": args.requested_model,
                    "resolved_model": args.model_profile.tier,
                    "output": str(plan.display_path),
                    "planned_outputs": [str(path) for path in plan.targets],
                    "config_sources": _config_sources(config),
                    "preflight": _dry_run_diagnostics(plan, args),
                    "payload": preview_payload(payload, secrets=(config.api_key,)),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    _ensure_no_request_state(plan)
    prepare_output_destination(plan)
    _require_api_key(config)
    state_path, state = _new_request_state(plan, payload)
    started = time.monotonic()
    previous_handlers: dict[int, Any] = {}

    def handle_termination(signum, _frame) -> None:
        _mark_request_ambiguous(
            state_path, state, f"进程收到终止信号 {signum}", api_key=config.api_key
        )
        raise SystemExit(128 + signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, handle_termination)
        except (OSError, ValueError):
            pass

    try:
        if args.stream:
            save_stream_response(api_stream(payload, args.timeout, config), args, plan)
        else:
            save_response(api_request(payload, args.timeout, config), args, plan)
    except ArkRequestError as exc:
        if exc.ambiguous:
            _mark_request_ambiguous(state_path, state, str(exc), api_key=config.api_key)
        else:
            state_path.unlink(missing_ok=True)
        die(str(exc))
    except KeyboardInterrupt:
        _mark_request_ambiguous(state_path, state, "用户中断请求", api_key=config.api_key)
        die("请求已被中断，结果和计费状态未知；不得自动重试。", 130)
    except SystemExit:
        if state_path.exists() and state.get("status") != "ambiguous":
            _mark_request_ambiguous(
                state_path, state, "请求提交后的处理失败", api_key=config.api_key
            )
        raise
    except BaseException as exc:
        _mark_request_ambiguous(
            state_path,
            state,
            f"未处理异常：{type(exc).__name__}",
            api_key=config.api_key,
        )
        raise
    else:
        state_path.unlink(missing_ok=True)
    finally:
        for signum, previous in previous_handlers.items():
            try:
                signal.signal(signum, previous)
            except (OSError, ValueError):
                pass
    print(f"完成，用时 {time.monotonic() - started:.1f}s", file=sys.stderr)


def run(args: argparse.Namespace) -> None:
    try:
        _run(args)
    finally:
        # dry-run 常作为真实请求前的同形预检，需要保留 prompt 供后续调用；
        # 真实生成尝试一旦结束，无论成功或失败都清理显式标记的 agent prompt。
        if not getattr(args, "dry_run", False):
            _cleanup_prompt_file(args)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file")
    parser.add_argument(
        "--cleanup-prompt-file",
        action="store_true",
        help="真实生成尝试结束后删除 agent 创建的 --prompt-file；dry-run 保留。",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="pro 或 lite；默认 lite；未知值默认拒绝",
    )
    parser.add_argument(
        "--allow-model-fallback",
        action="store_true",
        help="显式允许未知模型兼容回退 Lite；真实请求前必须审查 warning",
    )
    parser.add_argument("--project-dir", help=argparse.SUPPRESS)
    parser.add_argument("--image", action="append", help="本地路径、HTTP(S) URL 或 data URI")
    parser.add_argument("--size", default=DEFAULT_SIZE, help="模型支持的分辨率档位或 WIDTHxHEIGHT")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--guidance-scale", type=float)
    parser.add_argument(
        "--output-format",
        choices=["jpeg", "png"],
        default=DEFAULT_OUTPUT_FORMAT,
        help="输出图片格式，默认 png",
    )
    parser.add_argument("--response-format", choices=["url", "b64_json"], default="url")
    parser.add_argument("--watermark", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--sequential", choices=["disabled", "auto"], default="disabled")
    parser.add_argument("--max-images", type=int)
    parser.add_argument("--web-search", action="store_true")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--out", help="单图输出文件")
    parser.add_argument("--out-dir", help="组图输出目录")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--private-filenames",
        action="store_true",
        help="默认输出名仅使用 seedream + prompt hash，不暴露 prompt 摘要",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="单次网络操作/socket timeout（秒），不是整次生成总 deadline",
    )
    parser.add_argument("--dry-run", action="store_true")


def main() -> int:
    parser = argparse.ArgumentParser(description="使用火山方舟 Seedream 5.0 Pro/Lite 生成或编辑图片")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="文生图、参考图生图、多图融合或 Lite 组图")
    add_common_args(generate)
    edit = subparsers.add_parser("edit", help="使用一张或多张参考图进行编辑")
    add_common_args(edit)
    args = parser.parse_args()
    if args.command == "edit" and not args.image:
        die("edit 子命令至少需要一个 --image。")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
