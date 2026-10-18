"""Smoke-test Firestore vector search on products.embedding (COSINE, RETRIEVAL_QUERY embeddings).

Run with `source scripts/env.sh` first:  .venv/bin/python data/verify_search.py ["your query" ...]
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_HERE = _Path(__file__).resolve().parent
_sys.path[:] = [p for p in _sys.path if _Path(p or ".").resolve() != _HERE]
_sys.path.insert(0, str(_HERE.parent))

import os  # noqa: E402

from google import genai  # noqa: E402
from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure  # noqa: E402
from google.cloud.firestore_v1.vector import Vector  # noqa: E402

from data.gen_embeddings import embed_query  # noqa: E402

QUERIES = ["maroon silk saree for Diwali", "blue kurta for men size L", "brass diyas for puja",
           "dry fruit gift box under 1000", "juttis for women"]


def main(queries: list[str]) -> None:
    client = genai.Client()
    db = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT", "retailnova-ai"))
    for q in queries:
        vq = db.collection("products").find_nearest(
            vector_field="embedding", query_vector=Vector(embed_query(client, q)),
            distance_measure=DistanceMeasure.COSINE, limit=5, distance_result_field="distance")
        print(f"\n{q}")
        for d in vq.get():
            x = d.to_dict()
            print(f"  {x['distance']:.3f}  {x['sku']}  Rs {x['price_inr']:>6,}  {x['name']}")


if __name__ == "__main__":
    main(_sys.argv[1:] or QUERIES)
