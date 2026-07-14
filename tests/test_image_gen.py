from __future__ import annotations

import argparse
import base64
from contextlib import redirect_stderr
from io import BytesIO, StringIO
import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from PIL import Image
from pillow_heif import register_heif_opener

from skills.imagegen.scripts import image_gen


register_heif_opener()


class ImageGenTests(unittest.TestCase):
    def setUp(self):
        config_directory = TemporaryDirectory()
        self.addCleanup(config_directory.cleanup)
        env_patch = mock.patch.object(
            image_gen, "ENV_FILE", Path(config_directory.name) / ".env"
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)
        network_patch = mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("测试禁止真实网络访问")
        )
        network_patch.start()
        self.addCleanup(network_patch.stop)

    def make_args(self, **overrides):
        values = {
            "command": "generate",
            "prompt": "测试图片",
            "prompt_file": None,
            "cleanup_prompt_file": False,
            "image": None,
            "size": "2K",
            "seed": None,
            "guidance_scale": None,
            "output_format": "png",
            "response_format": "url",
            "watermark": False,
            "model": "lite",
            "allow_model_fallback": False,
            "project_dir": None,
            "sequential": "disabled",
            "max_images": None,
            "out_dir": None,
            "web_search": False,
            "stream": False,
            "out": None,
            "force": False,
            "private_filenames": False,
            "timeout": 30,
            "dry_run": True,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    @staticmethod
    def image_bytes(image_format="PNG", size=(1920, 1920), color=(255, 0, 0)):
        out = BytesIO()
        Image.new("RGB", size, color).save(out, format=image_format)
        return out.getvalue()

    @staticmethod
    def single_plan(path: Path):
        return image_gen.OutputPlan(
            group=False,
            display_path=path,
            targets=(path,),
            state_path=image_gen._request_state_path(path),
        )

    def test_pro_supported_output_sizes(self):
        for size in ("1K", "2k", "1280x720", "3136x1344"):
            args = self.make_args(model="pro", size=size)
            image_gen.validate_args(args)
            if size == "2k":
                self.assertEqual("2K", args.size)

    def test_lite_supported_output_sizes(self):
        for size in ("2K", "3k", "4K", "2560x1440", "4096x4096"):
            args = self.make_args(model="lite", size=size)
            image_gen.validate_args(args)
            if size == "3k":
                self.assertEqual("3K", args.size)

    def test_model_specific_unsupported_output_sizes(self):
        cases = (
            ("pro", "3K"), ("pro", "4K"), ("lite", "1K"),
            ("pro", "100x100"), ("lite", "100x100"),
            ("pro", "99999x99999"), ("lite", "99999x99999"),
            ("lite", "100x9999"), ("lite", "abc"),
        )
        for model, size in cases:
            with self.subTest(size=size), self.assertRaises(SystemExit):
                image_gen.validate_args(self.make_args(model=model, size=size))

    def test_model_resolution_rejects_unknown_without_explicit_fallback(self):
        pro_values = ("pro", image_gen.PRO_MODEL)
        lite_values = (
            "lite", image_gen.LITE_MODEL, image_gen.LITE_MODEL_ALIAS, None, "",
        )
        for value in pro_values:
            profile, _ = image_gen.resolve_model(value)
            self.assertEqual("pro", profile.tier)
        for value in lite_values:
            profile, _ = image_gen.resolve_model(value)
            self.assertEqual("lite", profile.tier)
        with self.assertRaises(SystemExit):
            image_gen.resolve_model("some-future-model")
        stderr = StringIO()
        with redirect_stderr(stderr):
            profile, requested = image_gen.resolve_model(
                "some-future-model", allow_fallback=True
            )
        self.assertEqual("lite", profile.tier)
        self.assertEqual("some-future-model", requested)
        self.assertIn("回退", stderr.getvalue())

    def test_model_specific_reference_image_limits(self):
        with self.assertRaises(SystemExit):
            image_gen.validate_args(
                self.make_args(model="pro", image=["https://example.com/a.png"] * 11)
            )
        with self.assertRaises(SystemExit):
            image_gen.validate_args(
                self.make_args(model="lite", image=["https://example.com/a.png"] * 15)
            )
        image_gen.validate_args(
            self.make_args(model="pro", image=["https://example.com/a.png"] * 10)
        )
        image_gen.validate_args(
            self.make_args(model="lite", image=["https://example.com/a.png"] * 14)
        )

    def test_payload_has_only_pro_single_image_fields(self):
        args = self.make_args(model="pro", size="2K")
        image_gen.validate_args(args)
        payload = image_gen.build_payload(args)
        self.assertEqual(image_gen.PRO_MODEL, payload["model"])
        for unsupported in ("stream", "tools", "sequential_image_generation", "sequential_image_generation_options"):
            self.assertNotIn(unsupported, payload)

    def test_lite_payload_defaults_and_optional_capabilities(self):
        args = self.make_args()
        image_gen.validate_args(args)
        payload = image_gen.build_payload(args)
        self.assertEqual(image_gen.LITE_MODEL, payload["model"])
        self.assertEqual("disabled", payload["sequential_image_generation"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("stream", payload)

        args = self.make_args(
            model=image_gen.LITE_MODEL_ALIAS,
            sequential="auto",
            max_images=3,
            out_dir="group",
            web_search=True,
            stream=True,
            out=None,
        )
        image_gen.validate_args(args)
        payload = image_gen.build_payload(args)
        self.assertEqual(image_gen.LITE_MODEL, payload["model"])
        self.assertEqual("auto", payload["sequential_image_generation"])
        self.assertEqual({"max_images": 3}, payload["sequential_image_generation_options"])
        self.assertEqual([{"type": "web_search"}], payload["tools"])
        self.assertIs(payload["stream"], True)

    def test_configured_model_ids_override_payload_without_changing_tier_rules(self):
        config = image_gen.ArkConfig(
            api_key="test-key",
            base_url=image_gen.DEFAULT_BASE_URL,
            sources={},
            pro_model="custom-pro-model",
            lite_model="custom-lite-model",
        )
        for tier, configured_model in (
            ("pro", "custom-pro-model"),
            ("lite", "custom-lite-model"),
        ):
            with self.subTest(tier=tier):
                args = self.make_args(model=tier)
                image_gen.validate_args(args, config)
                self.assertEqual(configured_model, image_gen.build_payload(args)["model"])
                profile, _ = image_gen.resolve_model(configured_model, config=config)
                self.assertEqual(tier, profile.tier)

    def test_cli_default_output_uses_a_prompt_derived_png_name(self):
        parser = argparse.ArgumentParser()
        image_gen.add_common_args(parser)
        args = parser.parse_args(["--prompt", "默认 PNG"])
        self.assertEqual(image_gen.DEFAULT_OUTPUT_FORMAT, args.output_format)
        self.assertEqual("png", args.output_format)
        self.assertEqual(
            Path("默认-PNG.png"),
            image_gen.output_path(args),
        )

    def test_default_output_name_is_sanitized_and_versioned(self):
        parser = argparse.ArgumentParser()
        image_gen.add_common_args(parser)
        args = parser.parse_args(["--prompt", "  Cup: blue / white?\n  "])
        self.assertEqual(Path("Cup-blue-white.png"), image_gen.output_path(args))

    def test_default_output_name_versions_on_conflict(self):
        parser = argparse.ArgumentParser()
        image_gen.add_common_args(parser)
        args = parser.parse_args(["--prompt", "蓝色杯子"])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(image_gen, "DEFAULT_OUTPUT_DIRECTORY", root):
                (root / "蓝色杯子.png").touch()
                (root / "蓝色杯子-v2.png").touch()
                self.assertEqual(root / "蓝色杯子-v3.png", image_gen.output_path(args))

    def test_private_default_output_name_does_not_contain_prompt(self):
        args = self.make_args(prompt="高度敏感的项目代号", private_filenames=True)
        image_gen.validate_args(args)
        path = image_gen.output_path(args)
        self.assertNotIn("高度敏感", path.name)
        self.assertRegex(path.name, r"^seedream-[0-9a-f]{16}\.png$")

    def test_request_body_budget_includes_prompt_and_non_image_fields(self):
        args = self.make_args(prompt="x" * 100)
        image_gen.validate_args(args)
        with mock.patch.object(image_gen, "MAX_REQUEST_BODY_BYTES", 50):
            with self.assertRaises(SystemExit):
                image_gen.build_payload(args)

    def test_request_fingerprint_is_order_independent_without_canonical_json_copy(self):
        left = {"prompt": "x", "nested": {"b": 2, "a": 1}}
        right = {"nested": {"a": 1, "b": 2}, "prompt": "x"}
        self.assertEqual(
            image_gen._request_fingerprint(left),
            image_gen._request_fingerprint(right),
        )

    def test_prompt_file_is_loaded_before_default_output_planning(self):
        parser = argparse.ArgumentParser()
        image_gen.add_common_args(parser)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.txt"
            path.write_text('带引号的 "提示词"', encoding="utf-8")
            args = parser.parse_args(["--prompt-file", str(path)])
            image_gen.validate_args(args)
            self.assertEqual('带引号的 "提示词"', args.resolved_prompt)
            self.assertEqual(Path("带引号的-提示词.png"), image_gen.output_path(args))
            self.assertEqual(args.resolved_prompt, image_gen.build_payload(args)["prompt"])

    def test_cleanup_prompt_file_requires_prompt_file(self):
        with self.assertRaises(SystemExit):
            image_gen.validate_args(self.make_args(cleanup_prompt_file=True))

    def test_watermark_flags_are_boolean_payload_values(self):
        parser = argparse.ArgumentParser()
        image_gen.add_common_args(parser)
        for option, expected in (("--watermark", True), ("--no-watermark", False)):
            with self.subTest(option=option):
                args = parser.parse_args(["--prompt", "测试", option])
                image_gen.validate_args(args)
                self.assertIs(expected, image_gen.build_payload(args)["watermark"])

    def test_dry_run_reports_default_and_explicit_fallback_models(self):
        for requested, allow_fallback in (("lite", False), ("unknown", True)):
            stdout = StringIO()
            stderr = StringIO()
            args = self.make_args(model=requested, allow_model_fallback=allow_fallback)
            with redirect_stderr(stderr), mock.patch("sys.stdout", stdout):
                image_gen.run(args)
            result = json.loads(stdout.getvalue())
            self.assertEqual(requested, result["requested_model"])
            self.assertEqual("lite", result["resolved_model"])
            self.assertEqual(image_gen.LITE_MODEL, result["payload"]["model"])
            self.assertNotEqual(requested, result["payload"]["model"])
            self.assertEqual("/images/generations", result["endpoint"])
            configured_base_url = os.getenv("ARK_BASE_URL", "")
            if configured_base_url:
                self.assertNotIn(configured_base_url, stdout.getvalue())

    def test_prompt_file_and_cleanup_do_not_enable_dry_run_implicitly(self):
        parser = argparse.ArgumentParser()
        image_gen.add_common_args(parser)
        args = parser.parse_args(
            [
                "--prompt-file",
                ".seedream-prompt-abc123.txt",
                "--size",
                "2K",
                "--no-watermark",
                "--out",
                "result.png",
                "--cleanup-prompt-file",
            ]
        )
        self.assertFalse(args.dry_run)

    def test_skill_documents_model_question_contract(self):
        skill = (image_gen.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("用户只明确选择 Lite 或 Pro，且没有与联网或模型能力冲突时直接使用", skill)
        self.assertIn("需要联网且未指定模型", skill)
        self.assertIn("Lite 联网", skill)
        self.assertIn("Pro 生图能力", skill)
        self.assertIn("AskUserQuestion", skill)
        self.assertIn("不静默切换模型", skill)
        self.assertIn("`--web-search` 本身不要求 dry-run", skill)
        self.assertIn("具体近期日期", skill)
        self.assertIn(".seedream-prompt-<random-id>.txt", skill)
        self.assertIn("HTTP 400、内容审核、敏感内容", skill)
        self.assertIn("内容审核明确拒绝后改写 prompt", skill)

    def test_process_env_overrides_skill_local_without_mutating_environment_or_file(self):
        with TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "ARK_API_KEY=local-key\n"
                "ARK_BASE_URL=https://local.example/api/v3\n"
                "ARK_PRO_MODEL=local-pro\n"
                "ARK_LITE_MODEL=local-lite\n"
                "IGNORED=x\n",
                encoding="utf-8",
            )
            before = env_path.read_bytes()
            before_mtime = env_path.stat().st_mtime_ns
            with mock.patch.dict(
                os.environ,
                {
                    "ARK_API_KEY": "process-key",
                    "ARK_BASE_URL": "https://process.example/api/v3",
                    "ARK_PRO_MODEL": "process-pro",
                    "ARK_LITE_MODEL": "process-lite",
                    "IGNORED": "process-value",
                },
                clear=False,
            ):
                config = image_gen.load_config(env_path)
                self.assertEqual("process-key", config.api_key)
                self.assertEqual("https://process.example/api/v3", config.base_url)
                self.assertEqual("process-pro", config.pro_model)
                self.assertEqual("process-lite", config.lite_model)
                self.assertEqual("process-key", os.environ["ARK_API_KEY"])
                self.assertEqual("https://process.example/api/v3", os.environ["ARK_BASE_URL"])
                self.assertEqual("process-value", os.environ["IGNORED"])
                self.assertEqual("process environment", config.sources["ARK_API_KEY"])
                self.assertEqual("process environment", config.sources["ARK_BASE_URL"])
                self.assertEqual("process environment", config.sources["ARK_PRO_MODEL"])
                self.assertEqual("process environment", config.sources["ARK_LITE_MODEL"])
            self.assertEqual(before, env_path.read_bytes())
            self.assertEqual(before_mtime, env_path.stat().st_mtime_ns)

    def test_missing_process_value_falls_back_to_skill_local_env(self):
        with TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("ARK_API_KEY=local-key\n", encoding="utf-8")
            config = image_gen.load_config(
                env_path,
                environ={"ARK_BASE_URL": "https://process.example/api/v3"},
            )
            self.assertEqual("local-key", config.api_key)
            self.assertEqual("https://process.example/api/v3", config.base_url)
            self.assertEqual("skill-local .env", config.sources["ARK_API_KEY"])
            self.assertEqual("process environment", config.sources["ARK_BASE_URL"])

    def test_skill_local_env_accepts_utf8_bom_and_uses_default_base_url(self):
        with TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("ARK_API_KEY=local-key\n", encoding="utf-8-sig")
            config = image_gen.load_config(env_path, environ={})
            self.assertEqual("local-key", config.api_key)
            self.assertEqual(image_gen.DEFAULT_BASE_URL, config.base_url)
            self.assertEqual(image_gen.PRO_MODEL, config.pro_model)
            self.assertEqual(image_gen.LITE_MODEL, config.lite_model)
            self.assertEqual("skill-local .env", config.sources["ARK_API_KEY"])
            self.assertEqual("default", config.sources["ARK_BASE_URL"])
            self.assertEqual("default", config.sources["ARK_PRO_MODEL"])
            self.assertEqual("default", config.sources["ARK_LITE_MODEL"])

    def test_invalid_configured_model_id_is_rejected(self):
        with TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("ARK_PRO_MODEL=invalid model\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                image_gen.load_config(env_path, environ={})

    def test_module_reload_does_not_read_env_or_mutate_environment(self):
        before = {key: os.environ.get(key) for key in image_gen.ENV_KEYS}
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("unexpected read")):
            importlib.reload(image_gen)
        self.assertEqual(before, {key: os.environ.get(key) for key in image_gen.ENV_KEYS})

    def test_placeholder_api_key_is_rejected_before_request(self):
        config = image_gen.ArkConfig(
            api_key="Your api key",
            base_url=image_gen.DEFAULT_BASE_URL,
            sources={"ARK_API_KEY": "skill-local .env", "ARK_BASE_URL": "default"},
        )
        with self.assertRaises(SystemExit):
            image_gen._require_api_key(config)

    def test_base_url_and_numeric_validation(self):
        valid = (
            "https://ark.example/api/v3/",
            "http://localhost:8080/api/v3",
            "http://127.0.0.1:8080/api/v3",
        )
        for value in valid:
            with self.subTest(value=value):
                self.assertEqual(value.rstrip("/"), image_gen._normalize_base_url(value))
        invalid = (
            "http://ark.example/api/v3",
            "https://user:pass@ark.example/api/v3",
            "https://ark.example/api/v3?token=x",
            "https://ark.example/api/v3#x",
            "file:///api/v3",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SystemExit):
                image_gen._normalize_base_url(value)
        for overrides in (
            {"seed": image_gen.MIN_SEED - 1},
            {"seed": image_gen.MAX_SEED + 1},
            {"guidance_scale": float("nan")},
            {"guidance_scale": float("inf")},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(SystemExit):
                image_gen.validate_args(self.make_args(**overrides))

    def test_png_dependency_path_does_not_enable_heif(self):
        with mock.patch.object(image_gen, "_enable_heif_support") as enable_heif:
            image_gen._load_image_dependencies("png")
        enable_heif.assert_not_called()
        with mock.patch.object(image_gen, "_enable_heif_support", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                image_gen._load_image_dependencies("heif")

    def test_pro_rejects_lite_only_capabilities(self):
        cases = (
            {"sequential": "auto", "max_images": 2, "out_dir": "group"},
            {"stream": True},
            {"web_search": True},
        )
        for override in cases:
            with self.subTest(override=override), self.assertRaises(SystemExit):
                image_gen.validate_args(self.make_args(model="pro", **override))

    def test_group_argument_rules_and_combined_limit(self):
        invalid = (
            {"sequential": "auto", "out_dir": "group"},
            {"sequential": "auto", "max_images": 2, "out_dir": "group", "out": "x.jpeg"},
            {"max_images": 2},
            {"out_dir": "group"},
            {
                "sequential": "auto", "max_images": 2, "out_dir": "group",
                "image": ["https://example.com/a.png"] * 14,
            },
        )
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(SystemExit):
                image_gen.validate_args(self.make_args(**override))

        image_gen.validate_args(self.make_args(sequential="auto", max_images=2))
        image_gen.validate_args(
            self.make_args(
                sequential="auto", max_images=1, out_dir="group",
                image=["https://example.com/a.png"] * 14,
            )
        )

    def test_prompt_length_warns_but_succeeds(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            prompt = image_gen.read_prompt("汉" * 301, None)
        self.assertEqual(301, len(prompt))
        self.assertIn("Warning", stderr.getvalue())

    def test_prompt_file_preserves_quotes_unicode_and_dash(self):
        expected = '模型 falsely "sees" 一个对象——保持原文。'
        with TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.txt"
            path.write_text(expected, encoding="utf-8")
            self.assertEqual(expected, image_gen.read_prompt(None, str(path)))

    def test_malformed_or_uppercase_data_uri_is_rejected(self):
        values = (
            "data:image/png;base64,NOT-BASE64",
            "data:image/PNG;base64,AAAA",
            "data:text/plain;base64,AAAA",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(SystemExit):
                image_gen.image_to_api_value(value)

    def test_oversized_data_uri_is_rejected_before_decode(self):
        with mock.patch.object(image_gen, "MAX_INPUT_BYTES", 3):
            with mock.patch("base64.b64decode") as decode, self.assertRaises(SystemExit):
                image_gen.image_to_api_value("data:image/png;base64,AAAAAAAA")
        decode.assert_not_called()

    def test_remote_url_validation_rejects_unsafe_forms(self):
        invalid = (
            "https://example.com/a b.png",
            "https://user:pass@example.com/a.png",
            "https://example.com:bad/a.png",
            "file:///tmp/a.png",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SystemExit):
                image_gen.image_to_api_value(value)

    def test_dry_run_redacts_remote_and_base64_images(self):
        payload = {
            "image": [
                "https://example.com/private.png?token=secret",
                "data:image/png;base64,AAAA",
            ]
        }
        preview = image_gen.preview_payload(payload)
        raw = json.dumps(preview)
        self.assertNotIn("token=secret", raw)
        self.assertNotIn("AAAA", raw)
        self.assertEqual("<remote image URL>", preview["image"][0])

    def test_dry_run_preserves_single_image_payload_shape(self):
        preview = image_gen.preview_payload(
            {"image": "data:image/png;base64,AAAA"}
        )
        self.assertIsInstance(preview["image"], str)

    def test_recursive_dry_run_scrubber_removes_known_secrets_and_sensitive_fields(self):
        secret = "fake-secret-key"
        preview = image_gen.preview_payload(
            {
                "prompt": f"keep text but hide {secret}",
                "tools": [{"token": "nested-token", "url": "https://example.com/x?sig=1"}],
            },
            secrets=(secret,),
        )
        raw = json.dumps(preview)
        self.assertNotIn(secret, raw)
        self.assertNotIn("nested-token", raw)
        self.assertNotIn("sig=1", raw)
        self.assertIn("keep text", raw)

    def test_aggregate_input_limit_precedes_base64_encoding(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for index in range(2):
                path = root / f"input-{index}.png"
                path.write_bytes(self.image_bytes("PNG", size=(32, 32)))
                paths.append(str(path))
            args = self.make_args(image=paths)
            image_gen.validate_args(args)
            total = sum(Path(path).stat().st_size for path in paths)
            with mock.patch.object(image_gen, "MAX_TOTAL_INPUT_BYTES", total - 1):
                with mock.patch("base64.b64encode") as encode, self.assertRaises(SystemExit):
                    image_gen.build_payload(args)
            encode.assert_not_called()

    def test_all_supported_local_image_formats(self):
        formats = {
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".webp": "WEBP",
            ".bmp": "BMP",
            ".tiff": "TIFF",
            ".gif": "GIF",
            ".heic": "HEIF",
            ".heif": "HEIF",
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for suffix, image_format in formats.items():
                with self.subTest(suffix=suffix):
                    path = root / f"input{suffix}"
                    Image.new("RGB", (32, 32), (1, 2, 3)).save(path, format=image_format)
                    value = image_gen.image_to_api_value(str(path))
                    self.assertTrue(value.startswith("data:image/"))

    def test_fake_extension_and_corrupt_image_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "fake.png"
            fake.write_bytes(self.image_bytes("JPEG"))
            broken = root / "broken.png"
            broken.write_bytes(b"not an image")
            for path in (fake, broken):
                with self.subTest(path=path), self.assertRaises(SystemExit):
                    image_gen.image_to_api_value(str(path))

    def test_input_dimensions_are_enforced(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tiny.png"
            path.write_bytes(self.image_bytes(size=(14, 32)))
            with self.assertRaises(SystemExit):
                image_gen.image_to_api_value(str(path))

    def test_input_size_limit_is_enforced_before_decode(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            with path.open("wb") as handle:
                handle.truncate(image_gen.MAX_INPUT_BYTES + 1)
            with self.assertRaises(SystemExit):
                image_gen.image_to_api_value(str(path))

    def test_output_extension_must_match_format(self):
        with self.assertRaises(SystemExit):
            image_gen.output_path(self.make_args(output_format="jpeg", out="result.png"))
        with self.assertRaises(SystemExit):
            image_gen.output_path(self.make_args(output_format="png", out="result.jpeg"))

    def test_output_conflict_is_detected_before_api_call(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "exists.png"
            path.write_bytes(b"existing")
            args = self.make_args(out=str(path), dry_run=False)
            with mock.patch.object(image_gen, "api_request") as request:
                with self.assertRaises(SystemExit):
                    image_gen.run(args)
                request.assert_not_called()

    def test_dry_run_reports_output_conflict_without_calling_api(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "exists.png"
            path.write_bytes(b"existing")
            stdout = StringIO()
            with mock.patch.object(image_gen, "api_request") as request, mock.patch(
                "sys.stdout", stdout
            ):
                image_gen.run(self.make_args(out=str(path), dry_run=True))
            request.assert_not_called()
            result = json.loads(stdout.getvalue())
            self.assertEqual([str(path)], result["preflight"]["output_conflicts"])

    def test_group_output_plan_and_conflict_preflight(self):
        with TemporaryDirectory() as directory:
            out_dir = Path(directory) / "group"
            args = self.make_args(
                sequential="auto", max_images=3, out_dir=str(out_dir),
                output_format="png",
            )
            image_gen.validate_args(args)
            plan = image_gen.build_output_plan(args)
            self.assertTrue(plan.group)
            self.assertEqual(
                ("image-01.png", "image-02.png", "image-03.png"),
                tuple(path.name for path in plan.targets),
            )
            self.assertEqual(out_dir / ".seedream-request.json", plan.state_path)
            out_dir.mkdir()
            plan.targets[1].write_bytes(b"existing")
            with self.assertRaises(SystemExit):
                image_gen.build_output_plan(args)
            args.force = True
            plan.targets[2].mkdir()
            with self.assertRaises(SystemExit):
                image_gen.build_output_plan(args)

    def test_default_group_states_are_scoped_to_the_prompt(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(image_gen, "DEFAULT_GROUP_OUTPUT_DIRECTORY", root):
                first = self.make_args(sequential="auto", max_images=2, prompt="同一森林")
                second = self.make_args(sequential="auto", max_images=2, prompt="同一海洋")
                image_gen.validate_args(first)
                image_gen.validate_args(second)
                first_plan = image_gen.build_output_plan(first)
                second_plan = image_gen.build_output_plan(second)
                self.assertNotEqual(first_plan.state_path, second_plan.state_path)
                self.assertTrue(first_plan.state_path.name.startswith(".同一森林-"))
                first_plan.state_path.write_text('{"status":"ambiguous"}', encoding="utf-8")
                with self.assertRaises(SystemExit):
                    image_gen._ensure_no_request_state(first_plan)
                image_gen._ensure_no_request_state(second_plan)

    def test_nonstream_group_saves_multiple_images(self):
        with TemporaryDirectory() as directory:
            args = self.make_args(
                sequential="auto", max_images=3, out_dir=directory,
                output_format="png", response_format="b64_json",
            )
            image_gen.validate_args(args)
            plan = image_gen.build_output_plan(args)
            content = self.image_bytes("PNG")
            encoded = base64.b64encode(content).decode("ascii")
            saved = image_gen.save_response(
                {"data": [{"b64_json": encoded}, {"b64_json": encoded}]}, args, plan
            )
            self.assertEqual(2, len(saved))
            self.assertEqual(content, plan.targets[0].read_bytes())
            self.assertEqual(content, plan.targets[1].read_bytes())
            for bad_count in (0, 4):
                with self.subTest(bad_count=bad_count), self.assertRaises(SystemExit):
                    image_gen.save_response(
                        {"data": [{"b64_json": encoded}] * bad_count}, args, plan
                    )

    def test_group_partial_save_failure_preserves_completed_file(self):
        with TemporaryDirectory() as directory:
            args = self.make_args(
                sequential="auto", max_images=2, out_dir=directory,
                output_format="png", response_format="b64_json",
            )
            image_gen.validate_args(args)
            plan = image_gen.build_output_plan(args)
            encoded = base64.b64encode(self.image_bytes("PNG")).decode("ascii")
            with self.assertRaises(SystemExit):
                image_gen.save_response(
                    {"data": [{"b64_json": encoded}, {"b64_json": "invalid"}]},
                    args,
                    plan,
                )
            self.assertTrue(plan.targets[0].is_file())
            self.assertFalse(plan.targets[1].exists())

    def test_save_valid_base64_image_atomically(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            content = self.image_bytes("PNG")
            result = {"data": [{"b64_json": base64.b64encode(content).decode("ascii")}]}
            args = self.make_args(output_format="png", response_format="b64_json")
            image_gen.save_response(result, args, self.single_plan(path))
            self.assertEqual(content, path.read_bytes())
            self.assertEqual([], list(path.parent.glob("*.tmp")))

    def test_invalid_or_multiple_response_items_are_rejected(self):
        args = self.make_args(output_format="png")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            bad_results = (
                {},
                {"data": []},
                {"data": [{}, {}]},
                {"data": ["bad"]},
                {"data": [{"b64_json": "NOT-BASE64"}]},
            )
            for result in bad_results:
                with self.subTest(result=result), self.assertRaises(SystemExit):
                    image_gen.save_response(result, args, self.single_plan(path))

    def test_oversized_or_non_string_response_base64_is_rejected(self):
        args = self.make_args(output_format="png")
        with TemporaryDirectory() as directory, mock.patch.object(
            image_gen, "MAX_OUTPUT_BYTES", 3
        ):
            path = Path(directory) / "result.png"
            for value in ("AAAAAAAA", 123):
                with self.subTest(value=value), self.assertRaises(SystemExit):
                    image_gen.save_response(
                        {"data": [{"b64_json": value}]},
                        args,
                        self.single_plan(path),
                    )

    def test_generated_format_mismatch_is_rejected(self):
        content = self.image_bytes("JPEG")
        result = {"data": [{"b64_json": base64.b64encode(content).decode("ascii")}]}
        with TemporaryDirectory() as directory, self.assertRaises(SystemExit):
            path = Path(directory) / "x.png"
            image_gen.save_response(
                result,
                self.make_args(output_format="png"),
                self.single_plan(path),
            )

    def test_generated_custom_dimension_mismatch_is_rejected(self):
        content = self.image_bytes("PNG", size=(1920, 1920))
        result = {"data": [{"b64_json": base64.b64encode(content).decode("ascii")}]}
        with TemporaryDirectory() as directory, self.assertRaises(SystemExit):
            path = Path(directory) / "x.png"
            image_gen.save_response(
                result,
                self.make_args(size="2048x2048", output_format="png"),
                self.single_plan(path),
            )

    def test_generated_named_tier_mismatch_is_rejected(self):
        content = self.image_bytes("PNG", size=(1920, 1920))
        args = self.make_args(size="4K", output_format="png")
        image_gen.validate_args(args)
        with self.assertRaises(SystemExit):
            image_gen._validate_generated_image(content, args)

    def test_generated_named_2k_tier_accepts_1920_square(self):
        content = self.image_bytes("PNG", size=(1920, 1920))
        args = self.make_args(size="2K", output_format="png")
        image_gen.validate_args(args)
        image_gen._validate_generated_image(content, args)

    def test_sse_decoder_handles_frames_done_and_invalid_json(self):
        lines = [
            b': keepalive\n',
            b'data: {"type":"image_generation.partial_image"}\n',
            b'\n',
            b'data: {"type":"image_generation.completed",\n',
            b'data: "usage":{"generated_images":1}}\n',
            b'\n',
            b'data: [DONE]\n',
            b'\n',
        ]
        events = list(image_gen._decode_sse_events(lines))
        self.assertEqual(2, len(events))
        self.assertEqual("image_generation.completed", events[1]["type"])
        with self.assertRaises(image_gen.ArkRequestError):
            list(image_gen._decode_sse_events([b"data: not-json\n", b"\n"]))

    def test_stream_success_ignores_preview_and_duplicate(self):
        with TemporaryDirectory() as directory:
            args = self.make_args(
                sequential="auto", max_images=2, out_dir=directory,
                output_format="png", response_format="b64_json", stream=True,
            )
            image_gen.validate_args(args)
            plan = image_gen.build_output_plan(args)
            encoded = base64.b64encode(self.image_bytes("PNG")).decode("ascii")
            succeeded = {
                "type": "image_generation.partial_succeeded",
                "id": "same-image",
                "b64_json": encoded,
            }
            events = [
                {"type": "image_generation.partial_image", "b64_json": "preview"},
                succeeded,
                dict(succeeded),
                {"type": "image_generation.completed", "usage": {"generated_images": 1}},
            ]
            saved = image_gen.save_stream_response(events, args, plan)
            self.assertEqual([plan.targets[0]], saved)
            self.assertTrue(plan.targets[0].is_file())
            self.assertFalse(plan.targets[1].exists())

    def test_stream_does_not_collapse_distinct_images_with_same_event_id(self):
        with TemporaryDirectory() as directory:
            args = self.make_args(
                sequential="auto", max_images=2, out_dir=directory,
                output_format="png", response_format="b64_json", stream=True,
            )
            image_gen.validate_args(args)
            plan = image_gen.build_output_plan(args)
            images = [
                base64.b64encode(self.image_bytes("PNG", color=color)).decode("ascii")
                for color in ((255, 0, 0), (0, 0, 255))
            ]
            events = [
                {"type": "image_generation.partial_succeeded", "id": "request", "b64_json": value}
                for value in images
            ] + [{"type": "image_generation.completed"}]
            saved = image_gen.save_stream_response(events, args, plan)
            self.assertEqual(list(plan.targets), saved)

    def test_stream_requires_completed_and_handles_internal_failure(self):
        with TemporaryDirectory() as directory:
            args = self.make_args(
                sequential="auto", max_images=1, out_dir=directory,
                output_format="png", response_format="b64_json", stream=True,
            )
            image_gen.validate_args(args)
            plan = image_gen.build_output_plan(args)
            encoded = base64.b64encode(self.image_bytes("PNG")).decode("ascii")
            with self.assertRaises(image_gen.ArkRequestError) as missing_completed:
                image_gen.save_stream_response(
                    [{"type": "image_generation.partial_succeeded", "b64_json": encoded}],
                    args,
                    plan,
                )
            self.assertTrue(missing_completed.exception.ambiguous)
            with self.assertRaises(image_gen.ArkRequestError) as failed:
                image_gen.save_stream_response(
                    [{
                        "type": "image_generation.partial_failed",
                        "error": {"code": "InternalServiceError", "message": "failed"},
                    }],
                    args,
                    plan,
                )
            self.assertTrue(failed.exception.ambiguous)

    def test_stream_interruption_preserves_image_and_blocks_retry(self):
        with TemporaryDirectory() as directory:
            out_dir = Path(directory) / "group"
            args = self.make_args(
                sequential="auto", max_images=2, out_dir=str(out_dir),
                output_format="png", response_format="b64_json", stream=True,
                dry_run=False,
            )
            encoded = base64.b64encode(self.image_bytes("PNG")).decode("ascii")

            def interrupted_events():
                yield {
                    "type": "image_generation.partial_succeeded",
                    "id": "one",
                    "b64_json": encoded,
                }
                raise image_gen.ArkRequestError("断流", ambiguous=True)

            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(image_gen, "api_stream", return_value=interrupted_events()):
                    with self.assertRaises(SystemExit):
                        image_gen.run(args)
            self.assertTrue((out_dir / "image-01.png").is_file())
            state_path = out_dir / ".seedream-request.json"
            self.assertEqual("ambiguous", json.loads(state_path.read_text(encoding="utf-8"))["status"])
            stdout = StringIO()
            with mock.patch.object(image_gen, "api_stream") as request, mock.patch(
                "sys.stdout", stdout
            ):
                image_gen.run(self.make_args(
                    sequential="auto", max_images=2, out_dir=str(out_dir),
                    output_format="png", stream=True,
                ))
            request.assert_not_called()
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["preflight"]["billable_request_blocked"])
            self.assertTrue(result["preflight"]["output_conflicts"])

    def test_sensitive_error_content_is_redacted(self):
        key = "secret-key-value"
        raw = f"{key} https://example.com/signed?token=abc data:image/png;base64,AAAA"
        redacted = image_gen._redact_message(raw, key)
        self.assertNotIn(key, redacted)
        self.assertNotIn("token=abc", redacted)
        self.assertNotIn("AAAA", redacted)

    def test_http_error_does_not_expose_key_or_signed_url(self):
        key = "test-secret-key"
        body = (
            b'{"error":{"code":"BadRequest","message":'
            b'"failed https://example.com/signed?token=secret","request_id":"req-1"}}'
        )
        error = __import__("urllib.error").error.HTTPError(
            "https://ark.example/api", 400, "bad", {}, BytesIO(body)
        )
        stderr = StringIO()
        with mock.patch.dict(os.environ, {"ARK_API_KEY": key}, clear=False):
            with mock.patch("urllib.request.urlopen", side_effect=error):
                with redirect_stderr(stderr), self.assertRaises(image_gen.ArkRequestError) as raised:
                    image_gen.api_request({"prompt": "x"}, 1)
        message = str(raised.exception)
        self.assertNotIn(key, message)
        self.assertNotIn("token=secret", message)
        self.assertIn("request_id=req-1", message)
        self.assertFalse(raised.exception.ambiguous)

    def test_http_submission_outcome_uses_conservative_allowlist(self):
        cases = (
            (400, "BadRequest", False),
            (400, "InvalidParameter", False),
            (400, "UnknownArkCode", True),
            (408, "RequestTimeout", True),
            (429, "RateLimitExceeded", True),
            (500, "InternalServiceError", True),
            (503, "ServiceUnavailable", True),
        )
        for status, ark_code, expected_ambiguous in cases:
            with self.subTest(status=status, ark_code=ark_code):
                body = json.dumps(
                    {"error": {"code": ark_code, "message": "test failure"}}
                ).encode("utf-8")
                error = __import__("urllib.error").error.HTTPError(
                    "https://ark.example/api", status, "failed", {}, BytesIO(body)
                )
                with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                    with mock.patch("urllib.request.urlopen", side_effect=error):
                        with self.assertRaises(image_gen.ArkRequestError) as raised:
                            image_gen.api_request({"prompt": "x"}, 1)
                self.assertEqual(expected_ambiguous, raised.exception.ambiguous)

    def test_unknown_http_error_without_ark_code_is_ambiguous(self):
        error = __import__("urllib.error").error.HTTPError(
            "https://ark.example/api", 418, "failed", {}, BytesIO(b"unknown")
        )
        with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
            with mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(image_gen.ArkRequestError) as raised:
                    image_gen.api_request({"prompt": "x"}, 1)
        self.assertTrue(raised.exception.ambiguous)

    def test_api_response_uses_separate_aggregate_limit(self):
        class Response(BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False), mock.patch.object(
            image_gen, "MAX_RESPONSE_BYTES", 3
        ), mock.patch("urllib.request.urlopen", return_value=Response(b"1234")):
            with self.assertRaises(image_gen.ArkRequestError) as raised:
                image_gen.api_request({"prompt": "x"}, 1)
        self.assertTrue(raised.exception.ambiguous)

    def test_pending_state_blocks_request_but_dry_run_reports_it(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            state_path = image_gen._request_state_path(path)
            state_path.write_text('{"status":"pending"}', encoding="utf-8")
            stdout = StringIO()
            with mock.patch.object(image_gen, "api_request") as request, mock.patch(
                "sys.stdout", stdout
            ):
                image_gen.run(self.make_args(out=str(path), dry_run=True))
            request.assert_not_called()
            result = json.loads(stdout.getvalue())
            self.assertEqual("present", result["preflight"]["request_state"])
            self.assertTrue(result["preflight"]["billable_request_blocked"])

            with mock.patch.object(image_gen, "api_request") as request, self.assertRaises(
                SystemExit
            ):
                image_gen.run(self.make_args(out=str(path), dry_run=False))
            request.assert_not_called()

    def test_successful_request_removes_state_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            content = self.image_bytes("PNG")
            result = {
                "data": [{"b64_json": base64.b64encode(content).decode("ascii")}]
            }
            args = self.make_args(
                out=str(path),
                dry_run=False,
                output_format="png",
                response_format="b64_json",
            )
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(image_gen, "api_request", return_value=result):
                    image_gen.run(args)
            self.assertTrue(path.is_file())
            self.assertFalse(image_gen._request_state_path(path).exists())

    def test_successful_request_cleans_explicitly_owned_prompt_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_file = root / ".seedream-prompt-abc123.txt"
            prompt_file.write_text("临时 prompt", encoding="utf-8")
            output = root / "result.png"
            content = self.image_bytes("PNG")
            result = {
                "data": [{"b64_json": base64.b64encode(content).decode("ascii")}]
            }
            args = self.make_args(
                prompt=None,
                prompt_file=str(prompt_file),
                cleanup_prompt_file=True,
                out=str(output),
                dry_run=False,
                response_format="b64_json",
                project_dir=str(root),
            )
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(image_gen, "api_request", return_value=result):
                    image_gen.run(args)
            self.assertTrue(output.is_file())
            self.assertFalse(prompt_file.exists())

    def test_ambiguous_request_cleans_prompt_but_keeps_state_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_file = root / ".seedream-prompt-abc123.txt"
            prompt_file.write_text("临时 prompt", encoding="utf-8")
            args = self.make_args(
                prompt=None,
                prompt_file=str(prompt_file),
                cleanup_prompt_file=True,
                out=str(root / "result.png"),
                dry_run=False,
                project_dir=str(root),
            )
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(
                    image_gen, "api_request", side_effect=image_gen.ArkRequestError("timeout", ambiguous=True)
                ):
                    with self.assertRaises(SystemExit):
                        image_gen.run(args)
            self.assertFalse(prompt_file.exists())
            state_path = image_gen._request_state_path(root / "result.png")
            self.assertTrue(state_path.is_file())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("ambiguous", state["status"])

    def test_dry_run_keeps_owned_root_prompt_for_real_request(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_file = root / ".seedream-prompt-abc123.txt"
            prompt_file.write_text("临时 prompt", encoding="utf-8")
            args = self.make_args(
                prompt=None,
                prompt_file=str(prompt_file),
                cleanup_prompt_file=True,
                out=str(root / "result.png"),
                dry_run=True,
                project_dir=str(root),
            )
            with mock.patch("sys.stdout", StringIO()):
                image_gen.run(args)
            self.assertTrue(prompt_file.is_file())

    def test_cleanup_prompt_file_outside_owned_root_is_rejected_before_request(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_file = root / "user-prompt.txt"
            prompt_file.write_text("用户文件", encoding="utf-8")
            args = self.make_args(
                prompt=None,
                prompt_file=str(prompt_file),
                cleanup_prompt_file=True,
                project_dir=str(root),
            )
            with mock.patch.object(image_gen, "api_request") as request:
                with self.assertRaises(SystemExit):
                    image_gen.run(args)
            request.assert_not_called()
            self.assertTrue(prompt_file.exists())

    def test_cleanup_prompt_file_symlink_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_file = root / ".seedream-prompt-abc123.txt"
            prompt_file.write_text("临时", encoding="utf-8")
            args = self.make_args(
                prompt=None,
                prompt_file=str(prompt_file),
                cleanup_prompt_file=True,
                project_dir=str(root),
            )
            with mock.patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaises(SystemExit):
                    image_gen.validate_args(args)

    def test_cleanup_prompt_file_stops_at_resolved_project_dir(self):
        """Regression: system symlinks above project_dir must not break cleanup validation.

        On macOS, ``/var`` is a symlink to ``/private/var``.  ``TemporaryDirectory``
        returns a path under ``/var``, while ``_project_directory`` resolves it to
        ``/private/var``.  The validation loop must stop at the resolved project_dir
        instead of continuing upward and treating ``/var`` as an unsafe symlink.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_file = root / ".seedream-prompt-abc123.txt"
            prompt_file.write_text("临时 prompt", encoding="utf-8")
            args = self.make_args(
                prompt=None,
                prompt_file=str(prompt_file),
                cleanup_prompt_file=True,
                project_dir=str(root),
            )
            # Simulate /var -> /private/var: project_dir resolves to a different
            # path, and the parent of root looks like a symlink.
            real_root = Path("/private") / root.relative_to(root.anchor)
            original_resolve = Path.resolve
            original_is_symlink = Path.is_symlink

            def fake_resolve(self, strict=False):
                absolute = self.absolute()
                if absolute == root or absolute.is_relative_to(root):
                    return real_root / absolute.relative_to(root)
                return original_resolve(self, strict=strict)

            def fake_is_symlink(self):
                if self.absolute() == root.parent:
                    return True
                return original_is_symlink(self)

            with mock.patch.object(Path, "resolve", fake_resolve):
                with mock.patch.object(Path, "is_symlink", fake_is_symlink):
                    resolved = image_gen._validate_prompt_cleanup_path(args)
            self.assertEqual(resolved, real_root / prompt_file.name)

    def test_windows_reserved_output_name_is_rejected_on_all_platforms(self):
        with TemporaryDirectory() as directory:
            for relative in ("CON.png", "CON.extra.png", "bad:name.png", "bad./result.png"):
                with self.subTest(relative=relative):
                    args = self.make_args(out=str(Path(directory) / relative))
                    image_gen.validate_args(args)
                    with self.assertRaises(SystemExit):
                        image_gen.build_output_plan(args)

    def test_atomic_write_no_clobber_preserves_concurrent_output(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "output.png"
            output.write_bytes(b"existing")
            with self.assertRaises(SystemExit):
                image_gen._atomic_write(output, b"replacement", force=False)
            self.assertEqual(b"existing", output.read_bytes())

    def test_atomic_write_interrupt_cleans_temporary_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output.png"
            with mock.patch.object(image_gen.os, "link", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    image_gen._atomic_write(output, b"data", force=False)
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(".output.png.*.tmp")))

    def test_request_state_interrupt_cleans_temporary_file_and_preserves_old_state(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / ".state.json"
            state_path.write_text('{"status":"old"}', encoding="utf-8")
            with mock.patch.object(image_gen.os, "replace", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    image_gen._write_request_state(state_path, {"status": "new"})
            self.assertEqual('{"status":"old"}', state_path.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob("..state.json.*.tmp")))

    def test_request_state_contains_hash_but_no_payload_or_key(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            payload = {"prompt": "private prompt", "image": "data:image/png;base64,AAAA"}
            state_path, state = image_gen._new_request_state(self.single_plan(path), payload)
            raw = state_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            self.assertEqual(state["payload_sha256"], parsed["payload_sha256"])
            self.assertNotIn("private prompt", raw)
            self.assertNotIn("AAAA", raw)
            self.assertNotIn("ARK_API_KEY", raw)

    def test_ambiguous_state_reason_redacts_injected_skill_local_key(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            state_path = image_gen._request_state_path(path)
            state = {"status": "pending"}
            secret = "skill-local-secret"
            image_gen._mark_request_ambiguous(
                state_path,
                state,
                f"failed with {secret} https://example.com/x?token=1",
                api_key=secret,
            )
            raw = state_path.read_text(encoding="utf-8")
            self.assertNotIn(secret, raw)
            self.assertNotIn("token=1", raw)

    def test_ambiguous_failure_persists_and_blocks_retry(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            args = self.make_args(out=str(path), dry_run=False)
            failure = image_gen.ArkRequestError("timeout", ambiguous=True)
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(image_gen, "api_request", side_effect=failure):
                    with self.assertRaises(SystemExit):
                        image_gen.run(args)
            state_path = image_gen._request_state_path(path)
            self.assertEqual("ambiguous", json.loads(state_path.read_text(encoding="utf-8"))["status"])
            stdout = StringIO()
            with mock.patch.object(image_gen, "api_request") as request, mock.patch(
                "sys.stdout", stdout
            ):
                image_gen.run(self.make_args(out=str(path), dry_run=True))
            request.assert_not_called()
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["preflight"]["billable_request_blocked"])

    def test_known_http_failure_removes_state(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            args = self.make_args(out=str(path), dry_run=False)
            failure = image_gen.ArkRequestError("HTTP 400", ambiguous=False)
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(image_gen, "api_request", side_effect=failure):
                    with self.assertRaises(SystemExit):
                        image_gen.run(args)
            self.assertFalse(image_gen._request_state_path(path).exists())

    def test_http_503_keeps_ambiguous_request_state(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            args = self.make_args(out=str(path), dry_run=False)
            body = b'{"error":{"code":"ServiceUnavailable","message":"later"}}'
            error = __import__("urllib.error").error.HTTPError(
                "https://ark.example/api", 503, "failed", {}, BytesIO(body)
            )
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch("urllib.request.urlopen", side_effect=error):
                    with self.assertRaises(SystemExit):
                        image_gen.run(args)
            state_path = image_gen._request_state_path(path)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("ambiguous", state["status"])
            self.assertIn("HTTP 503", state["reason"])

    def test_failure_after_api_response_is_ambiguous(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            args = self.make_args(out=str(path), dry_run=False)
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(image_gen, "api_request", return_value={"data": []}):
                    with self.assertRaises(SystemExit):
                        image_gen.run(args)
            state = json.loads(
                image_gen._request_state_path(path).read_text(encoding="utf-8")
            )
            self.assertEqual("ambiguous", state["status"])

    def test_keyboard_interrupt_is_ambiguous(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.png"
            args = self.make_args(out=str(path), dry_run=False)
            with mock.patch.dict(os.environ, {"ARK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(image_gen, "api_request", side_effect=KeyboardInterrupt):
                    with self.assertRaises(SystemExit) as raised:
                        image_gen.run(args)
            self.assertEqual(130, raised.exception.code)
            state = json.loads(
                image_gen._request_state_path(path).read_text(encoding="utf-8")
            )
            self.assertEqual("ambiguous", state["status"])

    def test_download_reads_url_response(self):
        content = self.image_bytes("PNG")
        response = BytesIO(content)
        response.headers = {"Content-Length": str(len(content))}
        with mock.patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(content, image_gen.download_bytes("https://example.com/image.png", 1))


if __name__ == "__main__":
    unittest.main()
