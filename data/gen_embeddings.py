"""Embed the 72 catalog products with gemini-embedding-2 (768-dim, RETRIEVAL_DOCUMENT).

Output: data/out/embeddings.json  ->  {"model": ..., "dim": 768, "items": {sku: {"text_hash": ..., "vector": [...]}}}
Cached: a SKU is re-embedded only when its source text changes. Run with `source scripts/env.sh` first.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# data/calendar.py would shadow the stdlib `calendar` module if data/ were on sys.path: import siblings as
# the `data` package from the repo root instead.
_HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))
from data.catalog_spec import PRODUCTS  # noqa: E402

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

MODEL = "gemini-embedding-2"
DIM = 768
OUT = Path(__file__).resolve().parent / "out" / "embeddings.json"
BATCH = 24


def embed_text(p: dict) -> str:
    return (f"{p['name']}. {p['description']} Category: {p['category'].replace('_', ' ')} "
            f"({p['subcategory'].replace('_', ' ')}). Color: {p['color']} ({p['color_family']}). "
            f"Material: {p['material']}. Occasion: {', '.join(p['occasion'])}. "
            f"Tags: {', '.join(p['tags'])}. Price: Rs {p['price_inr']}.")


def _embed(client, texts: list[str], task: str) -> list[list[float]]:
    cfg = types.EmbedContentConfig(output_dimensionality=DIM, task_type=task)
    for attempt in range(6):
        try:
            r = client.models.embed_content(model=MODEL, contents=texts, config=cfg)
            vecs = [list(e.values) for e in r.embeddings]
        except Exception as e:  # retry transient errors (429/503)
            if attempt == 5:
                raise
            wait = 2 ** attempt
            print(f"  embed retry {attempt + 1} after {type(e).__name__}: {str(e)[:120]} (sleep {wait}s)")
            time.sleep(wait)
            continue
        if len(vecs) != len(texts):  # multimodal embedder merges a list into one vector: not retryable
            raise ValueError(f"expected {len(texts)} embeddings, got {len(vecs)}")
        return vecs
    raise RuntimeError("unreachable")


def embed_many(client, texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embeds texts in parallel batches of concurrent requests.

    gemini-embedding-2 is multimodal: a list passed as `contents` is embedded as ONE item, so each text
    is sent as its own request and requests are fanned out BATCH at a time.
    """
    out: list[list[float]] = []
    with ThreadPoolExecutor(8) as ex:
        for i in range(0, len(texts), BATCH):
            out += list(ex.map(lambda t: _embed(client, [t], task)[0], texts[i:i + BATCH]))
    return out


def embed_query(client, text: str) -> list[float]:
    return _embed(client, [text], "RETRIEVAL_QUERY")[0]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(OUT.read_text()) if OUT.exists() else {"items": {}}
    items = cache.get("items", {}) if cache.get("model") in (None, MODEL) else {}
    todo = []
    for p in PRODUCTS:
        t = embed_text(p)
        h = hashlib.sha256(t.encode()).hexdigest()[:16]
        if items.get(p["sku"], {}).get("text_hash") != h:
            todo.append((p["sku"], t, h))
    print(f"{len(PRODUCTS) - len(todo)} cached, {len(todo)} to embed")
    if todo:
        client = genai.Client()
        vecs = embed_many(client, [t for _, t, _ in todo])
        for (sku, _, h), v in zip(todo, vecs):
            assert len(v) == DIM, (sku, len(v))
            items[sku] = {"text_hash": h, "vector": [round(x, 7) for x in v]}
    OUT.write_text(json.dumps({"model": MODEL, "dim": DIM, "task_type": "RETRIEVAL_DOCUMENT",
                               "items": {k: items[k] for k in sorted(items)}}))
    print(f"wrote {OUT} ({len(items)} vectors, dim {DIM})")


if __name__ == "__main__":
    main()
