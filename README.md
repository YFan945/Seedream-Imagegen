# Seedream Imagegen

<p align="center">
  <img src="assets/seedream-imagegen-logo.png" alt="Seedream Imagegen" width="900">
</p>

[![validate](https://img.shields.io/badge/validate-passing-brightgreen)](https://github.com/YFan945/Seedream-Imagegen)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)
[![runtime](https://img.shields.io/badge/runtime-Claude%20Code-111827)](https://claude.com/claude-code)

Claude Code skill for generating and editing raster images with **Doubao Seedream 5.0 Lite / Pro** through Volcengine Ark. It provides a validated CLI, model-specific capability checks, dry-run previews, reference-image workflows, batch generation for Lite, and optional chroma-key cleanup.

> 中文文档：[README-zh.md](README-zh.md)

## Features

- `generate` for text-to-image, reference-image generation, multi-image fusion, and Lite image sets.
- `edit` for localized edits that preserve the rest of an existing image.
- Explicit Lite/Pro capability validation; the selected model is never silently changed.
- Safe `--dry-run` payload inspection before billable requests.
- Output collision protection, request-state files, and recovery guidance.
- `remove_chroma_key.py` for simple solid-color background to alpha conversion.

## Requirements

- Claude Code with skill support.
- Python 3.10+ and `pip`.
- A Volcengine Ark account and an Ark API key with access to Seedream 5.0 Lite or Pro.
- Network access to the configured Ark endpoint.

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Install as a Claude Code skill

Recommended:

```powershell
npx skills add YFan945/Seedream-Imagegen
```

If your `skills` CLI version requires an explicit global install:

```powershell
npx skills add YFan945/Seedream-Imagegen -g
```

The repository can also be downloaded without Git:

- ZIP: open [the repository archive page](https://github.com/YFan945/Seedream-Imagegen/archive/refs/heads/main.zip), download and extract it into your Claude Code skills directory.
- `npx` source copy: `npx degit YFan945/Seedream-Imagegen ~/.claude/skills/imagegen`.
- Git: `git clone https://github.com/YFan945/Seedream-Imagegen.git ~/.claude/skills/imagegen`.

`npx` is used here as a download/bootstrap method; this project is a Python skill and is not an npm image-generation runtime.

## Configuration

Copy `.env.example` to `.env` in this skill directory and set:

```dotenv
ARK_API_KEY=your_ark_api_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

The CLI reads these values for its current process only. You may instead set them in the process environment. Never commit `.env`, paste the key into prompts, or print it in logs.

## Usage

Run a free local validation first:

```powershell
python scripts\image_gen.py generate --model lite --prompt "一只坐在窗边的橘猫，柔和晨光" --out output\cat.png --dry-run
```

Generate after confirming the dry-run output:

```powershell
python scripts\image_gen.py generate --model lite --prompt "一只坐在窗边的橘猫，柔和晨光" --out output\cat.png
```

Edit an existing image:

```powershell
python scripts\image_gen.py edit --model pro --image input\photo.png --prompt "只把背景改成深蓝色；保持人物、姿态和光线不变" --out output\edited.png --dry-run
```

For multi-line prompts, references, batch generation, model limits, and recovery rules, read [SKILL.md](SKILL.md) and the relevant files under [`references/`](references/).

## Model notes

| Capability | Lite | Pro |
| --- | --- | --- |
| Resolution | 2K / 3K / 4K | 1K / 2K |
| Reference images | Up to 14 | Up to 10 |
| Image sets, stream, web search | Supported | Not supported |
| Point/box/doodle/sketch editing | Supported | Preferred for interactive edits |

Image generation may incur charges. Confirm model, prompt, output path, and parameters before every real request. Do not automatically retry `pending` or `ambiguous` requests.

## Development

```powershell
python -m pytest -q
```

Tests never call the real Ark API. See [AGENTS.md](AGENTS.md) for repository and contribution rules.

## License

See [LICENSE.txt](LICENSE.txt).
