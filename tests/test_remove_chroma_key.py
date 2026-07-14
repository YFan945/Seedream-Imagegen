from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image

from skills.imagegen.scripts import remove_chroma_key


class RemoveChromaKeyTests(unittest.TestCase):
    @staticmethod
    def parse_args(source: Path, output: Path, *extra: str):
        return remove_chroma_key._build_parser().parse_args(
            ["--input", str(source), "--out", str(output), *extra]
        )

    def test_despill_does_not_recolor_fully_opaque_subject(self):
        image = Image.new("RGBA", (3, 1))
        image.putdata([(0, 255, 0, 255), (20, 220, 20, 255), (255, 0, 0, 255)])
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=True,
            soft_matte=False,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        pixels = [image.getpixel((x, 0)) for x in range(3)]
        self.assertEqual((0, 0, 0, 0), pixels[0])
        self.assertEqual((20, 220, 20, 255), pixels[1])
        self.assertEqual((255, 0, 0, 255), pixels[2])

    def test_soft_matte_recovers_white_foreground_alpha_monotonically(self):
        expected_alphas = (32, 64, 95, 96, 97, 128, 192, 224)
        image = Image.new("RGBA", (len(expected_alphas), 1))
        image.putdata([(alpha, 255, alpha, 255) for alpha in expected_alphas])
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=True,
            soft_matte=True,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        actual_alphas = [image.getpixel((x, 0))[3] for x in range(image.width)]
        for expected, actual in zip(expected_alphas, actual_alphas):
            self.assertLessEqual(abs(expected - actual), 2)
        self.assertEqual(sorted(actual_alphas), actual_alphas)
        for x in range(image.width):
            self.assertEqual((255, 255, 255), image.getpixel((x, 0))[:3])

    def test_soft_matte_synthetic_alpha_matrix(self):
        cases = {
            (0, 255, 0): ((0, 0, 0), (128, 128, 128), (255, 255, 255), (255, 0, 0), (0, 0, 255)),
            (255, 0, 255): ((0, 0, 0), (128, 128, 128), (255, 255, 255), (255, 0, 0), (0, 0, 255)),
            # Red-on-cyan versus gray-on-cyan is underdetermined from one composite pixel.
            (0, 255, 255): ((0, 0, 0), (255, 255, 255), (0, 0, 255)),
            (0, 0, 255): ((0, 0, 0), (128, 128, 128), (255, 255, 255), (255, 0, 0)),
        }
        expected_alphas = (32, 64, 96, 128, 192, 224)
        for key, foregrounds in cases.items():
            for foreground in foregrounds:
                with self.subTest(key=key, foreground=foreground):
                    composites = [
                        tuple(
                            round(alpha * channel / 255 + (255 - alpha) * key_channel / 255)
                            for channel, key_channel in zip(foreground, key)
                        )
                        for alpha in expected_alphas
                    ]
                    image = Image.new("RGBA", (len(composites), 1))
                    image.putdata([(*rgb, 255) for rgb in composites])
                    remove_chroma_key._apply_alpha_to_image(
                        image,
                        key=key,
                        tolerance=12,
                        spill_cleanup=True,
                        soft_matte=True,
                        transparent_threshold=12,
                        opaque_threshold=96,
                    )
                    actual = [image.getpixel((x, 0))[3] for x in range(image.width)]
                    self.assertLessEqual(
                        max(abs(expected - observed) for expected, observed in zip(expected_alphas, actual)),
                        2,
                    )

    def test_feather_never_revives_fully_transparent_source_pixels(self):
        image = Image.new("RGBA", (3, 1))
        image.putdata([(0, 0, 0, 0), (255, 0, 0, 255), (0, 0, 0, 0)])
        remove_chroma_key._transform_alpha(image, contract=0, feather=1)
        self.assertEqual(
            [0, 255, 0],
            [image.getpixel((x, 0))[3] for x in range(image.width)],
        )

    def test_feather_only_softens_inside_chroma_matte(self):
        image = Image.new("RGBA", (3, 1))
        image.putdata([(0, 255, 0, 255), (255, 0, 0, 255), (0, 255, 0, 255)])
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=False,
            soft_matte=False,
            transparent_threshold=12,
            opaque_threshold=96,
            edge_feather=1,
        )
        alphas = [image.getpixel((x, 0))[3] for x in range(image.width)]
        self.assertEqual(0, alphas[0])
        self.assertGreater(alphas[1], 0)
        self.assertLess(alphas[1], 255)
        self.assertEqual(0, alphas[2])

    def test_despill_protects_non_key_yellow_subject(self):
        image = Image.new("RGBA", (1, 1), (140, 140, 0, 255))
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=True,
            soft_matte=True,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        self.assertEqual((140, 140, 0, 255), image.getpixel((0, 0)))

    def test_soft_matte_creates_partial_alpha(self):
        image = Image.new("RGBA", (1, 1), (20, 220, 20, 255))
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=True,
            soft_matte=True,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        self.assertGreater(image.getpixel((0, 0))[3], 0)
        self.assertLess(image.getpixel((0, 0))[3], 255)

    def test_existing_alpha_is_preserved(self):
        image = Image.new("RGBA", (1, 1), (255, 0, 0, 128))
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=True,
            soft_matte=False,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        self.assertEqual((255, 0, 0, 128), image.getpixel((0, 0)))

    def test_source_low_alpha_is_not_removed_by_matte_noise_floor(self):
        source_alphas = (1, 8, 9, 128, 254)
        image = Image.new("RGBA", (len(source_alphas), 1))
        image.putdata([(255, 0, 0, alpha) for alpha in source_alphas])
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=True,
            soft_matte=False,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        self.assertEqual(
            list(source_alphas),
            [image.getpixel((x, 0))[3] for x in range(image.width)],
        )

    def test_chroma_stats_separate_source_key_and_final_alpha(self):
        image = Image.new("RGBA", (4, 1))
        image.putdata(
            [
                (255, 0, 0, 0),
                (0, 255, 0, 255),
                (255, 0, 0, 128),
                (255, 0, 0, 255),
            ]
        )
        stats = remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=False,
            soft_matte=False,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        self.assertEqual(
            remove_chroma_key.ChromaStats(
                total=4,
                source_transparent=1,
                key_matched=1,
                final_transparent=2,
                partial=1,
            ),
            stats,
        )

    def test_border_connected_preserves_isolated_key_colored_hole(self):
        image = Image.new("RGBA", (7, 7), (0, 255, 0, 255))
        for y in range(1, 6):
            for x in range(1, 6):
                image.putpixel((x, y), (255, 0, 0, 255))
        image.putpixel((3, 3), (0, 255, 0, 255))
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=False,
            soft_matte=False,
            transparent_threshold=12,
            opaque_threshold=96,
            border_connected=True,
        )
        self.assertEqual(0, image.getpixel((0, 0))[3])
        self.assertEqual((0, 255, 0, 255), image.getpixel((3, 3)))

    def test_auto_border_key_and_png_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            image = Image.new("RGB", (32, 32), (0, 255, 0))
            for y in range(10, 22):
                for x in range(10, 22):
                    image.putpixel((x, y), (255, 0, 0))
            image.save(source)
            args = remove_chroma_key._build_parser().parse_args(
                [
                    "--input",
                    str(source),
                    "--out",
                    str(output),
                    "--auto-key",
                    "border",
                    "--soft-matte",
                    "--despill",
                ]
            )
            remove_chroma_key._validate_args(args)
            remove_chroma_key._remove_chroma_key(args)
            with Image.open(output) as result:
                self.assertEqual("RGBA", result.mode)
                self.assertEqual(0, result.getpixel((0, 0))[3])
                self.assertEqual(255, result.getpixel((16, 16))[3])

    def test_auto_key_ignores_fully_transparent_border_pixels(self):
        image = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
        for x in range(4):
            image.putpixel((x, 0), (0, 255, 0, 255))
        self.assertEqual((0, 255, 0), remove_chroma_key._sample_border_key(image, "border"))

    def test_auto_key_rejects_equal_multimodal_border_without_writing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            image = Image.new("RGBA", (32, 32), (255, 0, 255, 255))
            for y in range(32):
                for x in range(16):
                    image.putpixel((x, y), (0, 255, 0, 255))
            image.save(source)
            args = self.parse_args(source, output, "--auto-key", "border")
            remove_chroma_key._validate_args(args)
            with self.assertRaises(SystemExit):
                remove_chroma_key._remove_chroma_key(args)
            self.assertFalse(output.exists())

    def test_auto_key_returns_a_real_sample_from_dominant_cluster(self):
        image = Image.new("RGBA", (16, 16), (0, 252, 2, 255))
        image.putpixel((0, 0), (1, 255, 0, 255))
        image.putpixel((15, 15), (0, 250, 4, 255))
        samples = {pixel[:3] for pixel in remove_chroma_key._iter_border_pixels(image, "border")}
        key = remove_chroma_key._sample_border_key(image, "border")
        self.assertIn(key, samples)

    def test_auto_key_rejects_disagreeing_corner(self):
        image = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        for y in range(8):
            for x in range(24, 32):
                image.putpixel((x, y), (255, 0, 255, 255))
        with self.assertRaises(SystemExit):
            remove_chroma_key._sample_border_key(image, "border")

    def test_input_and_output_same_path_is_rejected(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGB", (4, 4), (0, 255, 0)).save(source)
            args = self.parse_args(source, source, "--force")
            with self.assertRaises(SystemExit):
                remove_chroma_key._validate_args(args)
            with Image.open(source) as preserved:
                self.assertEqual((0, 255, 0), preserved.getpixel((0, 0)))

    def test_atomic_no_clobber_preserves_concurrent_output(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "output.png"
            output.write_bytes(b"existing")
            with self.assertRaises(SystemExit):
                remove_chroma_key._atomic_write(output, b"replacement", force=False)
            self.assertEqual(b"existing", output.read_bytes())

    def test_exif_orientation_is_applied_before_processing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "oriented.jpg"
            output = root / "output.png"
            image = Image.new("RGB", (3, 2), (0, 255, 0))
            exif = Image.Exif()
            exif[274] = 6
            image.save(source, exif=exif)
            args = self.parse_args(source, output, "--key-color", "00ff00")
            remove_chroma_key._validate_args(args)
            remove_chroma_key._remove_chroma_key(args)
            with Image.open(output) as result:
                self.assertEqual((2, 3), result.size)

    def test_animated_input_is_rejected_without_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "animated.gif"
            output = root / "output.png"
            frames = [Image.new("RGB", (4, 4), color) for color in ((0, 255, 0), (255, 0, 0))]
            frames[0].save(source, save_all=True, append_images=frames[1:], duration=20, loop=0)
            args = self.parse_args(source, output)
            remove_chroma_key._validate_args(args)
            with self.assertRaises(SystemExit):
                remove_chroma_key._remove_chroma_key(args)
            self.assertFalse(output.exists())

    def test_pixel_limit_is_checked_before_decode(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            Image.new("RGB", (10, 10), (0, 255, 0)).save(source)
            args = self.parse_args(source, output)
            remove_chroma_key._validate_args(args)
            with mock.patch.object(remove_chroma_key, "MAX_INPUT_PIXELS", 50):
                with self.assertRaises(SystemExit):
                    remove_chroma_key._remove_chroma_key(args)
            self.assertFalse(output.exists())

    def test_encoding_failure_preserves_existing_forced_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            Image.new("RGB", (4, 4), (0, 255, 0)).save(source)
            output.write_bytes(b"existing")
            args = self.parse_args(source, output, "--force")
            remove_chroma_key._validate_args(args)
            with mock.patch.object(remove_chroma_key, "_encode_image", side_effect=OSError("disk")):
                with self.assertRaises(SystemExit):
                    remove_chroma_key._remove_chroma_key(args)
            self.assertEqual(b"existing", output.read_bytes())

    def test_atomic_write_interrupt_cleans_temporary_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output.png"
            with mock.patch.object(remove_chroma_key.os, "link", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    remove_chroma_key._atomic_write(output, b"data", force=False)
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(".output.png.*")))

    def test_heif_input_is_supported_as_static_image(self):
        from pillow_heif import from_pillow

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.heif"
            output = root / "output.png"
            from_pillow(Image.new("RGB", (8, 8), (0, 255, 0))).save(source)
            args = self.parse_args(source, output)
            remove_chroma_key._validate_args(args)
            remove_chroma_key._remove_chroma_key(args)
            with Image.open(output) as result:
                self.assertEqual((8, 8), result.size)

    def test_nan_threshold_is_rejected(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGB", (2, 2), (0, 255, 0)).save(source)
            args = SimpleNamespace(
                input=str(source),
                out=str(Path(directory) / "out.png"),
                tolerance=12,
                transparent_threshold=float("nan"),
                opaque_threshold=96,
                edge_feather=0,
                edge_contract=0,
                soft_matte=True,
                force=False,
            )
            with self.assertRaises(SystemExit):
                remove_chroma_key._validate_args(args)

    def test_low_saturation_key_rejects_soft_matte_and_despill(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGB", (4, 4), (128, 128, 128)).save(source)
            for option in ("--soft-matte", "--despill"):
                args = self.parse_args(
                    source,
                    Path(directory) / f"{option[2:]}.png",
                    "--key-color",
                    "808080",
                    option,
                )
                with self.subTest(option=option), self.assertRaises(SystemExit):
                    remove_chroma_key._validate_args(args)

    def test_16_bit_input_has_explicit_rgba8_output_contract(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            Image.new("I;16", (4, 4), 65535).save(source)
            args = self.parse_args(source, output, "--key-color", "ffffff")
            remove_chroma_key._validate_args(args)
            remove_chroma_key._remove_chroma_key(args)
            with Image.open(output) as result:
                self.assertEqual("RGBA", result.mode)

    def test_decompression_bomb_error_is_controlled_and_writes_nothing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            Image.new("RGB", (4, 4), (0, 255, 0)).save(source)
            args = self.parse_args(source, output)
            remove_chroma_key._validate_args(args)
            with mock.patch.object(
                Image,
                "open",
                side_effect=Image.DecompressionBombError("too many pixels"),
            ):
                with self.assertRaises(SystemExit):
                    remove_chroma_key._remove_chroma_key(args)
            self.assertFalse(output.exists())

    def test_webp_output_is_lossless_and_keeps_alpha(self):
        image = Image.new("RGBA", (2, 1))
        image.putdata([(12, 34, 56, 128), (200, 150, 100, 255)])
        encoded = remove_chroma_key._encode_image(image, ".webp")
        with Image.open(BytesIO(encoded)) as decoded:
            self.assertEqual("RGBA", decoded.mode)
            self.assertEqual(image.tobytes(), decoded.tobytes())


if __name__ == "__main__":
    unittest.main()
