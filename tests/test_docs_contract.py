from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import yaml
from PIL import Image, ImageChops
import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "imagegen"


def test_claude_md_stays_in_sync_with_agents_md():
    assert (ROOT / "CLAUDE.md").read_bytes() == (ROOT / "AGENTS.md").read_bytes()


def test_skill_frontmatter_is_valid_yaml():
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert content.startswith("---\n")
    frontmatter = content.split("---", 2)[1]
    parsed = yaml.safe_load(frontmatter)
    assert parsed["name"] == "imagegen"
    assert isinstance(parsed["description"], str) and parsed["description"].strip()


def test_relative_markdown_links_and_assets_exist():
    markdown_files = [
        *ROOT.glob("*.md"),
        SKILL_ROOT / "SKILL.md",
        *(SKILL_ROOT / "references").glob("*.md"),
    ]
    link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    html_asset_pattern = re.compile(r"<(?:img|a)\b[^>]*(?:src|href)=\"([^\"]+)\"")
    missing: list[str] = []
    for markdown in markdown_files:
        text = markdown.read_text(encoding="utf-8")
        targets = link_pattern.findall(text) + html_asset_pattern.findall(text)
        for raw_target in targets:
            target = raw_target.strip().split("#", 1)[0]
            if not target or re.match(r"^(?:https?://|mailto:)", target):
                continue
            resolved = (markdown.parent / target).resolve(strict=False)
            if not resolved.exists():
                missing.append(f"{markdown.relative_to(ROOT)} -> {raw_target}")
    assert not missing, "失效 Markdown 链接：\n" + "\n".join(missing)


def test_visual_examples_are_documented_and_valid_images():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references" / "visual-examples.md").read_text(
        encoding="utf-8"
    )
    expected = [
        "photorealistic-natural.png",
        "product-mockup.png",
        "infographic-diagram.png",
        "illustration-story.png",
    ]
    assert "references/visual-examples.md" in skill
    for filename in expected:
        path = SKILL_ROOT / "assets" / "examples" / filename
        assert f"../assets/examples/{filename}" in reference
        assert path.stat().st_size > 0
        with Image.open(path) as opened:
            opened.verify()
        with Image.open(path) as opened:
            assert opened.width > 0 and opened.height > 0
            assert opened.width > opened.height


def test_brand_assets_live_outside_visual_examples():
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (ROOT / "README-zh.md").read_text(encoding="utf-8")
    for filename in ("seedream-imagegen-logo.png", "seedream-imagegen-icon.png"):
        assert (ROOT / "logo" / filename).is_file()
        assert not (SKILL_ROOT / "assets" / filename).exists()
    for readme in (english, chinese):
        assert "logo/seedream-imagegen-logo.png" in readme


def test_runtime_docs_never_use_bare_repository_script_paths():
    runtime_docs = [SKILL_ROOT / "SKILL.md", *(SKILL_ROOT / "references").glob("*.md")]
    pattern = re.compile(r"python\s+(?:scripts|<SKILL_DIR>)[\\/]")
    offenders = [
        str(path.relative_to(ROOT))
        for path in runtime_docs
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders


def test_claude_path_substitutions_are_scoped_to_rendered_skill():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert '$skillDir = "${CLAUDE_SKILL_DIR}"' in skill
    assert '$projectDir = "${CLAUDE_PROJECT_DIR}"' in skill

    raw_docs = [
        ROOT / "README.md",
        ROOT / "README-zh.md",
        *(SKILL_ROOT / "references").glob("*.md"),
    ]
    forbidden = (
        "${CLAUDE_SKILL_DIR}",
        "${CLAUDE_PROJECT_DIR}",
        "$env:CLAUDE_SKILL_DIR",
        "$env:CLAUDE_PROJECT_DIR",
    )
    offenders = [
        f"{path.relative_to(ROOT)} -> {token}"
        for path in raw_docs
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]
    assert not offenders, "普通文档不得依赖 Claude Code 字符串替换：\n" + "\n".join(
        offenders
    )


def test_powershell_reference_commands_use_initialized_local_paths():
    cli = (SKILL_ROOT / "references" / "cli.md").read_text(encoding="utf-8")
    chroma = (SKILL_ROOT / "references" / "chroma-key.md").read_text(encoding="utf-8")
    assert cli.count('python "$skillDir\\scripts\\image_gen.py"') == 5
    assert 'python "$skillDir\\scripts\\remove_chroma_key.py"' in chroma
    for text in (cli, chroma):
        assert "已渲染" in text
        assert "同一次 PowerShell 调用" in text


def test_skill_chooses_shell_without_scanning_unspecified_inputs():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "原生 Windows" in skill
    assert "macOS、Linux 和 WSL" in skill
    assert "不" in skill and "shell 选择" in skill
    assert "输入图片、prompt 文件" in skill
    assert "没有输入文件" in skill
    assert "不得用 Glob" in skill
    assert 'skill_dir="${CLAUDE_SKILL_DIR}"' in skill
    assert 'project_dir="${CLAUDE_PROJECT_DIR}"' in skill


def test_prompt_language_follows_user_language_without_extra_deliberation():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    prompting = (SKILL_ROOT / "references" / "prompting.md").read_text(encoding="utf-8")
    assert "references/prompting.md" in skill
    assert "用户主要输入文本的语言" in prompting
    assert "全局语言习惯" in prompting
    assert "中文、英文" in prompting
    assert "逐字" in prompting and "原文" in prompting


def test_skill_links_every_runtime_reference_directly():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    expected = {
        "lite.md",
        "pro.md",
        "prompting.md",
        "sample-prompts.md",
        "visual-examples.md",
        "cli.md",
        "chroma-key.md",
    }
    for filename in expected:
        assert f"references/{filename}" in skill


def test_prompt_templates_preserve_common_structure_and_scenarios():
    prompting = (SKILL_ROOT / "references" / "prompting.md").read_text(encoding="utf-8")
    samples = (SKILL_ROOT / "references" / "sample-prompts.md").read_text(
        encoding="utf-8"
    )
    assert "## 通用结构" in samples
    for field in ("任务类型", "核心请求", "输入图片", "必须保持", "禁止"):
        assert f"{field}：" in samples

    headings = (
        "### 写实场景",
        "### 商品摄影",
        "### 信息图 / 教学图",
        "### UI 线框图",
        "### 风格化插画",
        "### 历史场景",
        "### 人物一致性",
        "### 精确移除或替换",
        "### 文字本地化",
        "### 光照或天气",
        "### 风格迁移",
        "### 多图融合",
        "### 草图转写实",
        "### 圈选区域编辑",
        "### 坐标对应替换",
        "### 连贯组图",
        "### 联网事实信息图",
        "## 透明背景",
    )
    for heading in headings:
        assert heading in samples

    slugs = (
        "photorealistic-natural",
        "product-mockup",
        "ui-mockup",
        "infographic-diagram",
        "scientific-educational",
        "ads-marketing",
        "productivity-visual",
        "logo-brand",
        "illustration-story",
        "stylized-concept",
        "historical-scene",
        "text-localization",
        "identity-preserve",
        "precise-object-edit",
        "lighting-weather",
        "background-extraction",
        "style-transfer",
        "compositing",
        "sketch-to-render",
    )
    for slug in slugs:
        assert slug in prompting


def test_prompt_temp_workflow_uses_project_root_and_preserves_ambiguous_state():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    cli = (SKILL_ROOT / "references" / "cli.md").read_text(encoding="utf-8")
    for text in (skill, cli):
        assert ".seedream-prompt-<random-id>.txt" in text
        assert "HTTP 400" in text
        assert "不得" in text and "ambiguous" in text
    assert ".seedream-prompt-*.txt" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_readmes_have_aligned_contracts_and_correct_license():
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (ROOT / "README-zh.md").read_text(encoding="utf-8")
    for text in (english, chinese):
        assert "license-Apache--2.0" in text
        assert "license-MIT" not in text
        assert "validate-passing" not in text
        assert "actions/workflows/ci.yml/badge.svg" in text
        assert "-a claude-code" in text
        assert "imagegen\\SKILL.md" in text or "imagegen/SKILL.md" in text
        assert "pending" in text and "ambiguous" in text
        assert "Claude Code 2.1.196+" in text
        assert "references/prompting.md" in text
        assert "references/sample-prompts.md" in text
        assert "references/visual-examples.md" in text
        assert '<p align="center">' in text
    assert 'href="README-zh.md"' in english
    assert 'href="README.md"' in chinese
    assert english.count("\n## ") == chinese.count("\n## ")


def test_ci_workflow_covers_supported_python_and_release_gates():
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    text = workflow_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    matrix = parsed["jobs"]["validate"]["strategy"]["matrix"]
    assert matrix["os"] == ["ubuntu-latest", "windows-latest", "macos-latest"]
    assert matrix["python-version"] == ["3.10", "3.11", "3.12", "3.13"]
    assert "python -m pytest -q" in text
    assert "python -m compileall -q skills/imagegen/scripts tests" in text
    assert "git diff --check" in text
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in pyproject


def test_dependencies_have_one_documented_installation_entry_point():
    requirements = (SKILL_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert not (ROOT / "requirements-dev.txt").exists()
    for dependency in ("Pillow", "pillow-heif", "PyYAML", "pytest"):
        assert dependency in requirements

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "requirements-dev.txt" not in workflow
    assert "requirements.txt" in workflow

    for readme in (ROOT / "README.md", ROOT / "README-zh.md"):
        text = readme.read_text(encoding="utf-8")
        assert "requirements-dev.txt" not in text
        assert "requirements.txt" in text


def test_readme_logo_is_cropped_and_reasonably_compressed():
    path = ROOT / "logo" / "seedream-imagegen-logo.png"
    assert path.stat().st_size < 500_000
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    mask = ImageChops.difference(image, background).convert("L").point(
        lambda value: 255 if value > 8 else 0
    )
    left, top, right, bottom = mask.getbbox()
    assert left < image.width * 0.10
    assert image.width - right < image.width * 0.10
    assert top < image.height * 0.25
    assert image.height - bottom < image.height * 0.25


def test_external_cwd_and_space_paths_support_dry_run_without_real_env():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        skill = root / "skill with spaces"
        project = root / "project with spaces"
        (skill / "scripts").mkdir(parents=True)
        project.mkdir()
        shutil.copy2(SKILL_ROOT / "scripts" / "image_gen.py", skill / "scripts" / "image_gen.py")
        output = project / "output" / "result.png"
        completed = subprocess.run(
            [
                sys.executable,
                str(skill / "scripts" / "image_gen.py"),
                "generate",
                "--model",
                "lite",
                "--prompt",
                "外部 CWD 测试",
                "--out",
                str(output),
                "--dry-run",
            ],
            cwd=project,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        preview = json.loads(completed.stdout)
        assert Path(preview["output"]) == output
        assert preview["config_sources"]["ARK_API_KEY"] == "unset"


@pytest.mark.skipif(sys.platform != "win32", reason="仅验证 Windows PowerShell 语法")
def test_powershell_local_path_initialization_supports_space_paths():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        skill = root / "skill with spaces"
        project = root / "project with spaces"
        (skill / "scripts").mkdir(parents=True)
        project.mkdir()
        shutil.copy2(SKILL_ROOT / "scripts" / "image_gen.py", skill / "scripts" / "image_gen.py")

        def quoted(value: Path | str) -> str:
            return "'" + str(value).replace("'", "''") + "'"

        command = "; ".join(
            [
                f"$skillDir = {quoted(skill)}",
                f"$projectDir = {quoted(project)}",
                f"$python = {quoted(sys.executable)}",
                '& $python "$skillDir\\scripts\\image_gen.py" generate --model lite '
                '--prompt "PowerShell 路径测试" '
                '--out "$projectDir\\output\\result.png" --dry-run',
            ]
        )
        environment = os.environ.copy()
        environment.pop("ARK_API_KEY", None)
        environment.pop("ARK_BASE_URL", None)
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=project,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        preview = json.loads(completed.stdout)
        assert Path(preview["output"]) == project / "output" / "result.png"
        assert preview["config_sources"]["ARK_API_KEY"] == "unset"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows 由 PowerShell 专项用例覆盖")
def test_bash_local_path_initialization_supports_space_paths():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        skill = root / "skill with spaces"
        project = root / "project with spaces"
        (skill / "scripts").mkdir(parents=True)
        project.mkdir()
        shutil.copy2(SKILL_ROOT / "scripts" / "image_gen.py", skill / "scripts" / "image_gen.py")
        command = "; ".join(
            [
                f"skill_dir={shlex.quote(str(skill))}",
                f"project_dir={shlex.quote(str(project))}",
                f"{shlex.quote(sys.executable)} \"$skill_dir/scripts/image_gen.py\" "
                "generate --model lite --prompt 'Bash path test' "
                '--out "$project_dir/output/result.png" --dry-run',
            ]
        )
        environment = os.environ.copy()
        environment.pop("ARK_API_KEY", None)
        environment.pop("ARK_BASE_URL", None)
        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=project,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        preview = json.loads(completed.stdout)
        assert Path(preview["output"]) == project / "output" / "result.png"
        assert preview["config_sources"]["ARK_API_KEY"] == "unset"


def test_external_prompt_file_command_without_flag_is_not_implicit_dry_run():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        skill = root / "skill"
        project = root / "project"
        prompt = project / ".seedream-prompt-abc123.txt"
        (skill / "scripts").mkdir(parents=True)
        project.mkdir(parents=True)
        prompt.write_text("普通 2K 单图", encoding="utf-8")
        shutil.copy2(SKILL_ROOT / "scripts" / "image_gen.py", skill / "scripts" / "image_gen.py")
        output = project / "result.png"
        environment = os.environ.copy()
        environment.pop("ARK_API_KEY", None)
        environment.pop("ARK_BASE_URL", None)
        completed = subprocess.run(
            [
                sys.executable,
                str(skill / "scripts" / "image_gen.py"),
                "generate",
                "--model",
                "lite",
                "--prompt-file",
                str(prompt),
                "--size",
                "2K",
                "--no-watermark",
                "--out",
                str(output),
                "--cleanup-prompt-file",
                "--project-dir",
                str(project),
            ],
            cwd=project,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 1
        assert "ARK_API_KEY 为空" in completed.stderr
        assert '"endpoint"' not in completed.stdout
        assert prompt.exists()
        assert not output.exists()
