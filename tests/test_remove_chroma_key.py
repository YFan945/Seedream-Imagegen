from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from PIL import Image

from scripts import remove_chroma_key


class RemoveChromaKeyTests(unittest.TestCase):
    def test_hard_mode_despill_affects_only_key_like_pixels(self):
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
        self.assertLess(pixels[1][1], 220)
        self.assertEqual((255, 0, 0, 255), pixels[2])

    def test_despill_protects_obviously_non_key_green_subject(self):
        image = Image.new("RGBA", (1, 1), (0, 140, 0, 255))
        remove_chroma_key._apply_alpha_to_image(
            image,
            key=(0, 255, 0),
            tolerance=12,
            spill_cleanup=True,
            soft_matte=True,
            transparent_threshold=12,
            opaque_threshold=96,
        )
        self.assertEqual((0, 140, 0, 255), image.getpixel((0, 0)))

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

    def test_webp_output_is_lossless_and_keeps_alpha(self):
        image = Image.new("RGBA", (2, 1))
        image.putdata([(12, 34, 56, 128), (200, 150, 100, 255)])
        encoded = remove_chroma_key._encode_image(image, ".webp")
        with Image.open(BytesIO(encoded)) as decoded:
            self.assertEqual("RGBA", decoded.mode)
            self.assertEqual(image.tobytes(), decoded.tobytes())


if __name__ == "__main__":
    unittest.main()
