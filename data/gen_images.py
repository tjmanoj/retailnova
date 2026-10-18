"""Generate the 72 catalog photos (and 2 sample query photos) with gemini-3.1-flash-image.

Writes WebP (longest side 768 px, <= 80 KB) to web/public/products/{sku}.webp and web/public/samples/.
Idempotent: existing files are skipped unless listed with --force. Run with `source scripts/env.sh` first.

  python data/gen_images.py                 # all missing catalog + sample images
  python data/gen_images.py --only SAR-001 MEN-004 --force
"""
from __future__ import annotations

import argparse
import io
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# data/calendar.py would shadow the stdlib `calendar` module if data/ were on sys.path: import siblings as
# the `data` package from the repo root instead.
_HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))
from data.catalog_spec import PRODUCTS  # noqa: E402

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402
from PIL import Image  # noqa: E402

MODEL = "gemini-3.1-flash-image"
ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = ROOT / "web" / "public" / "products"
SAMPLES_DIR = ROOT / "web" / "public" / "samples"
MAX_SIDE = 768
MAX_BYTES = 80 * 1024
PARALLEL = 6          # default fan-out; lower it with --parallel if the image quota returns 429s

STYLE = ("Professional studio e-commerce product photograph. Plain warm off-white seamless background, "
         "soft even diffused lighting, gentle natural shadow, product centered and fully in frame, "
         "square composition, sharp focus, true-to-life colours, consistent catalog style. "
         "Absolutely no people, no hands, no faces, no models, no text, no letters, no logos, no labels, "
         "no watermark, no price tags.")

PRESENTATION = {
    "sarees": "The saree is neatly folded into a rectangle with the decorative border and a corner of the "
              "pallu fanned out on top to show the weave and zari work.",
    "kurta_sets": "The women's kurta set is displayed on an invisible ghost mannequin (no visible body), "
                  "front view, with the matching bottoms and dupatta arranged neatly.",
    "mens_ethnic": "The men's garment is displayed on an invisible ghost mannequin (no visible body), "
                   "front view, neatly pressed.",
    "home_decor": "The decor item is arranged attractively as a tabletop product shot.",
    "gifting": "The gift is shown as a tidy tabletop product shot, packaging open just enough to show contents.",
    "footwear": "A single pair, placed side by side at a slight three-quarter angle.",
}

SAMPLES = {
    "blue-kurta": "A casual, slightly imperfect smartphone photo of a plain royal blue silk-blend men's kurta "
                  "with a mandarin collar hanging on a wooden hanger against a light painted wall at home, "
                  "natural window light. No people, no text, no watermark.",
    "maroon-saree": "A casual smartphone photo of a maroon silk saree with a gold zari border draped over the "
                    "back of a wooden chair in a living room, natural daylight. No people, no text, no watermark.",
}


def product_prompt(p: dict) -> str:
    return (f"{STYLE}\nProduct: {p['name']}. Colour: {p['color']}. Material: {p['material']}. "
            f"Details: {p['description']}\n{PRESENTATION[p['category']]}")


def to_webp(raw: bytes) -> bytes:
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    for q in (82, 76, 70, 64, 58, 52, 46, 40):
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=q, method=6)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    im.thumbnail((640, 640), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=50, method=6)
    return buf.getvalue()


def generate(client, prompt: str) -> bytes:
    cfg = types.GenerateContentConfig(response_modalities=["IMAGE"])
    last = None
    for attempt in range(9):
        try:
            r = client.models.generate_content(model=MODEL, contents=prompt, config=cfg)
            for cand in r.candidates or []:
                for part in (cand.content.parts if cand.content else []) or []:
                    if part.inline_data and part.inline_data.data:
                        return part.inline_data.data
            last = RuntimeError("no image in response")
        except Exception as e:  # 429 / 503 / transient
            last = e
        time.sleep(min(90, 6 * 2 ** attempt) * (0.75 + 0.5 * random.random()))
    raise RuntimeError(f"image generation failed: {last}")


def job(client, name: str, prompt: str, path: Path) -> tuple[str, int, int]:
    raw = generate(client, prompt)
    data = to_webp(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return name, len(data), 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="SKUs or sample names to (re)generate")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--extra", default="", help="extra prompt guidance appended (for regenerations)")
    ap.add_argument("--parallel", type=int, default=PARALLEL)
    args = ap.parse_args()

    jobs = []
    for p in PRODUCTS:
        jobs.append((p["sku"], product_prompt(p) + (f"\n{args.extra}" if args.extra else ""),
                     PRODUCTS_DIR / f"{p['sku']}.webp"))
    for name, prompt in SAMPLES.items():
        jobs.append((name, prompt + (f"\n{args.extra}" if args.extra else ""), SAMPLES_DIR / f"{name}.webp"))
    if args.only:
        jobs = [j for j in jobs if j[0] in set(args.only)]
    if not args.force:
        jobs = [j for j in jobs if not j[2].exists()]
    print(f"{len(jobs)} images to generate with {MODEL} ({args.parallel} in parallel)", flush=True)
    if not jobs:
        return
    client = genai.Client()
    calls, failed = 0, []
    with ThreadPoolExecutor(args.parallel) as ex:
        futs = {ex.submit(job, client, n, pr, pa): n for n, pr, pa in jobs}
        for f in as_completed(futs):
            try:
                name, size, c = f.result()
                calls += c
                print(f"  ok  {name:<14} {size / 1024:5.1f} KB", flush=True)
            except Exception as e:
                failed.append(futs[f])
                print(f"  FAIL {futs[f]}: {str(e)[:160]}", flush=True)
    print(f"done: {len(jobs) - len(failed)} written, {len(failed)} failed {failed}", flush=True)


if __name__ == "__main__":
    main()
