from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import yaml
from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]


def test_skill_frontmatter_is_valid_yaml():
    content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert content.startswith("---\n")
    frontmatter = content.split("---", 2)[1]
    parsed = yaml.safe_load(frontmatter)
    assert parsed["name"] == "imagegen"
    assert isinstance(parsed["description"], str) and parsed["description"].strip()


def test_relative_markdown_links_and_assets_exist():
    markdown_files = list(ROOT.glob("*.md")) + list((ROOT / "references").glob("*.md"))
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


def test_runtime_docs_never_use_bare_repository_script_paths():
    runtime_docs = [ROOT / "SKILL.md", *(ROOT / "references").glob("*.md")]
    pattern = re.compile(r"python\s+(?:scripts|<SKILL_DIR>)[\\/]")
    offenders = [
        str(path.relative_to(ROOT))
        for path in runtime_docs
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders


def test_prompt_temp_workflow_uses_project_root_and_preserves_ambiguous_state():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    cli = (ROOT / "references" / "cli.md").read_text(encoding="utf-8")
    for text in (skill, cli):
        assert ".seedream-prompt-<random-id>.txt" in text
        assert "HTTP 400" in text
        assert "不得" in text and "ambiguous" in text
    assert "agent 不再新建" in skill
    assert "agent 不再新建" in cli
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
    assert english.count("\n## ") == chinese.count("\n## ")


def test_ci_workflow_covers_supported_python_and_release_gates():
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    text = workflow_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    matrix = parsed["jobs"]["validate"]["strategy"]["matrix"]
    assert matrix["os"] == ["ubuntu-latest", "windows-latest"]
    assert matrix["python-version"] == ["3.10", "3.11", "3.12", "3.13"]
    assert "python -m pytest -q" in text
    assert "python -m compileall -q scripts tests" in text
    assert "git diff --check" in text
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in pyproject


def test_readme_logo_is_cropped_and_reasonably_compressed():
    path = ROOT / "assets" / "seedream-imagegen-logo.png"
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
        shutil.copy2(ROOT / "scripts" / "image_gen.py", skill / "scripts" / "image_gen.py")
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
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        preview = json.loads(completed.stdout)
        assert Path(preview["output"]) == output
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
        shutil.copy2(ROOT / "scripts" / "image_gen.py", skill / "scripts" / "image_gen.py")
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
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 1
        assert "ARK_API_KEY 为空" in completed.stderr
        assert '"endpoint"' not in completed.stdout
        assert not prompt.exists()
        assert not output.exists()
