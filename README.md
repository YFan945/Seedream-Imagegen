# Seedream Imagegen

<p align="center">
  <img src="logo/seedream-imagegen-logo.png" alt="Seedream Imagegen" width="900">
</p>

[![CI](https://github.com/YFan945/Seedream-Imagegen/actions/workflows/ci.yml/badge.svg)](https://github.com/YFan945/Seedream-Imagegen/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE.txt)
[![runtime](https://img.shields.io/badge/runtime-Claude%20Code-111827)](https://claude.com/claude-code)

<p align="center">
  <strong>English</strong> · <a href="README-zh.md">简体中文</a>
</p>

A Claude Code skill for generating and editing raster images with Doubao Seedream 5.0 Lite or Pro through Volcengine Ark. It uses one validated Python CLI for model checks, free dry-runs, payload-level request locks, atomic saves, Lite image sets, and optional chroma-key conversion.

## Features

- `generate` for text-to-image, reference-image generation, multi-image fusion, and Lite image sets.
- `edit` for explicit edits that preserve unrequested content.
- Structured prompts for task categories, reference-image roles, exact text, edit invariants, and common scenario templates.
- Conservative billing state: 408, 429, 5xx, unknown Ark errors, timeouts, disconnects, and uncertain saves remain `ambiguous` and are never retried automatically.
- Recursive secret redaction, aggregate request limits, exact output preflight, and atomic no-clobber saves.
- Validated chroma-key matte, foreground recovery, despill, border-connected mode, EXIF transpose, and static HEIF support.

## Documentation

- [Skill workflow](skills/imagegen/SKILL.md): model selection, generation flow, billing safeguards, and delivery rules.
- [Prompt guidance](skills/imagegen/references/prompting.md) and [scenario templates](skills/imagegen/references/sample-prompts.md): structured prompts selected by the agent; users do not need to fill in a form.
- [Visual examples](skills/imagegen/references/visual-examples.md): optional style references that are never added to requests by default.
- [CLI reference](skills/imagegen/references/cli.md), [Lite specification](skills/imagegen/references/lite.md), and [Pro specification](skills/imagegen/references/pro.md): commands, parameters, and model boundaries.
- [Chroma-key reference](skills/imagegen/references/chroma-key.md): validated transparency workflow and limitations.

## Requirements

- Claude Code 2.1.196+ with skills support.
- Python 3.10+ and `pip`.
- A Volcengine Ark API key with access to the selected Seedream model.
- Network access to the configured Ark endpoint for real requests.
- One dependency file: `skills/imagegen/requirements.txt` contains both runtime and test dependencies.

## Install

`npx skills` installs to the current project by default; `-g` selects the personal/global scope. This skill targets Claude Code explicitly.

Personal install, available in every project:

```powershell
npx skills add YFan945/Seedream-Imagegen --skill imagegen -g -a claude-code --copy -y
Test-Path "$HOME\.claude\skills\imagegen\SKILL.md"
python -m pip install -r "$HOME\.claude\skills\imagegen\requirements.txt"
```

Project install, run from the target project root:

```powershell
npx skills add YFan945/Seedream-Imagegen --skill imagegen -a claude-code --copy -y
Test-Path ".claude\skills\imagegen\SKILL.md"
python -m pip install -r ".claude\skills\imagegen\requirements.txt"
```

If installer output differs, do not assume discovery succeeded: the final required entrypoint is exactly `~/.claude/skills/imagegen/SKILL.md` for a personal install or `.claude/skills/imagegen/SKILL.md` for a project install. Claude Code documents those locations in its [skills guide](https://code.claude.com/docs/en/slash-commands); `npx skills` documents scope and `-a claude-code` in its [CLI repository](https://github.com/vercel-labs/skills).

Manual Git install:

```powershell
git clone --depth 1 https://github.com/YFan945/Seedream-Imagegen.git "$HOME\seedream-imagegen"
Copy-Item "$HOME\seedream-imagegen\skills\imagegen" "$HOME\.claude\skills\imagegen" -Recurse
python -m pip install -r "$HOME\.claude\skills\imagegen\requirements.txt"
```

```bash
git clone --depth 1 https://github.com/YFan945/Seedream-Imagegen.git "$HOME/seedream-imagegen"
cp -R "$HOME/seedream-imagegen/skills/imagegen" "$HOME/.claude/skills/imagegen"
python -m pip install -r "$HOME/.claude/skills/imagegen/requirements.txt"
```

For ZIP installation, rename the extracted directory to `imagegen` and verify the same final `SKILL.md` path. To uninstall, remove only that installed `imagegen` directory or run `npx skills remove imagegen -g -a claude-code` for a personal CLI-managed install.

## Configuration

Copy `.env.example` to `.env` inside the installed skill and set the API key. `ARK_BASE_URL` is optional and should only be added for a custom Ark endpoint:

```dotenv
ARK_API_KEY=your_ark_api_key
# ARK_BASE_URL=https://custom.example/api/v3
# ARK_PRO_MODEL=your_pro_model_id
# ARK_LITE_MODEL=your_lite_model_id
```

The built-in base URL is `https://ark.cn-beijing.volces.com/api/v3`; Pro and Lite also have built-in default Model IDs. `ARK_BASE_URL`, `ARK_PRO_MODEL`, and `ARK_LITE_MODEL` are optional overrides. Configuration precedence is process environment, then skill-local `.env`, then built-in defaults. The CLI lazily reads only these four keys into an immutable per-run config; it does not modify `os.environ`, Windows environment settings, or `.env`. UTF-8 files with or without BOM are accepted. Never commit `.env` or paste credentials into prompts and logs.

## Free smoke test

Run from any project directory. This is local-only and does not require an API key:

```powershell
$skillDir = "$HOME\.claude\skills\imagegen"
$projectDir = (Get-Location).Path
python "$skillDir\scripts\image_gen.py" generate --model lite `
  --prompt "一只坐在窗边的橘猫，柔和晨光" `
  --out "$projectDir\output\cat.png" --dry-run
```

Claude Code resolves the skill and project roots while rendering `SKILL.md`; supporting reference files use the resulting local `$skillDir` / `$projectDir` variables instead of raw substitution tokens. Agent prompt files use `.seedream-prompt-<random-id>.txt` in the project root; real generation cleans the file only after creating its submission state, while dry-run and pre-submission failures retain it for correction. Payload locks live in `$projectDir/.seedream-requests/` and can be inspected with `state --project-dir`. Real generation may incur charges. Never delete state or retry a `pending` or `ambiguous` request without checking output and billing first.

`--dry-run` runs only when explicitly supplied; it is not the default for ordinary generation and hides prompts, Base64, and remote URLs by default. Unspecified single images always go to `$projectDir/` with content-derived prompt names; Lite image sets always go to `$projectDir/images/`. `--private-filenames` is off by default and may be used only when the user or prompt explicitly requests hidden content; it switches to a hash name, not a random name. News, weather, market data, sensitive images, and personal data are sent to Ark only with the user's data-processing consent; verify facts outside the model. If web access and Pro capabilities are both explicitly requested, ask the user to choose one.

## Model boundaries

| Capability | Lite | Pro |
|---|---|---|
| Resolution | 2K / 3K / 4K | 1K / 2K |
| Reference images | Up to 14 | Up to 10 |
| Image sets / stream / web search | Supported | Not supported |
| Visual controls | Ordinary arrows, boxes, and doodle cues | Precise coordinate/region interaction preferred |

The public Ark pages do not currently expose every Model ID and limit as directly addressable static text. Treat [`references/lite.md`](skills/imagegen/references/lite.md) and [`references/pro.md`](skills/imagegen/references/pro.md) as versioned local constraints and re-check official Ark documentation before changing them.

## Chroma-key scope

Chroma key is for flat, high-saturation backgrounds and solid subjects that do not contain the key hue family. It is not a general segmentation tool for hair, smoke, glass, liquids, veils, motion blur, soft shadows, or translucency. See [`references/chroma-key.md`](skills/imagegen/references/chroma-key.md) for the validated command, alpha contract, failure rules, and three-step delivery check.

## Development

From the cloned repository root:

```powershell
python -m pip install -r skills/imagegen/requirements.txt
python -m pytest -q
python -m compileall -q skills/imagegen/scripts tests
python tests\benchmark_remove_chroma_key.py --max-seconds 7
git diff --check
```

`pyproject.toml` provides standardized project metadata and `pytest` configuration (currently the test directory and default reporting); it is not a second dependency-installation entry point. Install all dependencies only from `skills/imagegen/requirements.txt`.

Tests globally block real network access and never issue a billable Ark request. See [AGENTS.md](AGENTS.md) for contribution rules.

## License

Apache License 2.0. See [LICENSE.txt](LICENSE.txt).
