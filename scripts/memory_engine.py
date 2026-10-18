#!/usr/bin/env python3
"""Create (idempotently) the Agent Platform Memory Bank used for shopper preference memory.

Usage (from the repo root):
    source scripts/env.sh
    .venv/bin/python scripts/memory_engine.py            # prints MEMORY_ENGINE=<resource name>
    .venv/bin/python scripts/memory_engine.py --recreate # delete the bank with this display name, then create it

The bank only extracts shopping preferences (colours, fabrics, sizes, budget, occasions, preferred
store); personal details are excluded by the topic configuration and scrubbed by the app before upload.

One-time IAM: the Reasoning Engine service agent must be able to call Gemini to generate memories:
    gcloud projects add-iam-policy-binding retailnova-ai \
      --member=serviceAccount:service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com \
      --role=roles/aiplatform.user
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "retailnova-ai")
LOCATION = os.getenv("MEMORY_LOCATION", "asia-south1")
DISPLAY_NAME = os.getenv("MEMORY_DISPLAY_NAME", "retailnova-memory")

TOPICS = [
    {
        "custom_memory_topic": {
            "label": "shopping_preferences",
            "description": (
                "The shopper's shopping preferences for Indian festive fashion, decor and gifting: favourite "
                "colours, fabrics or materials (e.g. silk, cotton), clothing and footwear sizes, typical budget "
                "in rupees, occasions they shop for (e.g. wedding, Diwali), preferred categories and preferred "
                "store. Never extract names, phone numbers, email addresses, home addresses or other personal "
                "identifiers."
            ),
        }
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true")
    args = ap.parse_args()

    import agentplatform

    client = agentplatform.Client(project=PROJECT, location=LOCATION)
    existing = [mb for mb in client.memory_banks.list() if getattr(mb, "display_name", None) == DISPLAY_NAME]
    if existing and args.recreate:
        for mb in existing:
            print(f"deleting {mb.name}", file=sys.stderr)
            client.memory_banks.delete(name=mb.name, force=True)
        existing = []
    if existing:
        name = existing[0].name
        print(f"exists: {name}", file=sys.stderr)
    else:
        mb = client.memory_banks.create(
            managed_semantic_memory_config={"unstructured_memory_configs": [{"memory_topics": TOPICS}]},
            config={"display_name": DISPLAY_NAME},
        )
        name = mb.name
        print(f"created: {name}", file=sys.stderr)
    print(f"MEMORY_ENGINE={name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
