"""手工运行的 2K 色键性能门禁；不由常规 pytest 收集。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import remove_chroma_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--max-seconds", type=float, default=7.0)
    args = parser.parse_args()

    image = Image.new("RGBA", (args.size, args.size), (64, 255, 64, 255))
    started = perf_counter()
    remove_chroma_key._apply_alpha_to_image(
        image,
        key=(0, 255, 0),
        tolerance=12,
        spill_cleanup=True,
        soft_matte=True,
        transparent_threshold=12,
        opaque_threshold=96,
    )
    elapsed = perf_counter() - started
    megapixels_per_second = (args.size * args.size / 1_000_000) / elapsed
    print(
        f"{args.size}x{args.size}: {elapsed:.3f}s, "
        f"{megapixels_per_second:.3f} MP/s（门禁 {args.max_seconds:.3f}s）"
    )
    return 0 if elapsed <= args.max_seconds else 1


if __name__ == "__main__":
    raise SystemExit(main())
