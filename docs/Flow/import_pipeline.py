"""
import_pipeline.py
──────────────────
Script import pipeline từ file JSON vào hệ thống Auto-AT qua REST API.

Cách dùng:
    python import_pipeline.py                          # dùng file mặc định pipeline-flowchart.json
    python import_pipeline.py --file custom.json       # dùng file JSON khác
    python import_pipeline.py --url http://host:8000   # base URL khác
    python import_pipeline.py --update                 # update nếu template đã tồn tại

Yêu cầu:
    pip install requests
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Cần cài requests: pip install requests")
    sys.exit(1)


# ─── Mặc định ────────────────────────────────────────────────────────────────
DEFAULT_FILE = Path(__file__).parent / "pipeline-flowchart.json"
DEFAULT_URL = "http://localhost:8000"


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def create_template(base_url: str, payload: dict) -> dict:
    url = f"{base_url}/api/v1/pipeline-templates/"
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_template(base_url: str, template_id: str, payload: dict) -> dict:
    # Chuẩn bị update payload (bỏ template_id & tags khỏi update body)
    update_payload = {
        "name": payload.get("name"),
        "description": payload.get("description"),
        "nodes": payload.get("nodes", []),
        "edges": payload.get("edges", []),
        "tags": payload.get("tags", []),
    }
    url = f"{base_url}/api/v1/pipeline-templates/{template_id}"
    resp = requests.put(url, json=update_payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_template(base_url: str, template_id: str) -> dict | None:
    url = f"{base_url}/api/v1/pipeline-templates/{template_id}"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def print_summary(result: dict) -> None:
    print(f"\n✅ Pipeline imported successfully!")
    print(f"   template_id : {result.get('template_id')}")
    print(f"   name        : {result.get('name')}")
    print(f"   version     : {result.get('version')}")
    print(f"   nodes       : {result.get('node_count')}")
    print(f"   edges       : {result.get('edge_count')}")
    print(f"   is_builtin  : {result.get('is_builtin')}")
    print(f"   id (MongoDB): {result.get('id')}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Auto-AT pipeline template")
    parser.add_argument(
        "--file", "-f",
        type=Path,
        default=DEFAULT_FILE,
        help="Path to pipeline JSON file (default: pipeline-flowchart.json)",
    )
    parser.add_argument(
        "--url", "-u",
        default=DEFAULT_URL,
        help=f"Base URL of the Auto-AT backend (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update the template if it already exists (default: error on conflict)",
    )
    args = parser.parse_args()

    # 1. Load JSON
    if not args.file.exists():
        print(f"❌ File not found: {args.file}")
        sys.exit(1)

    payload = load_json(args.file)
    template_id = payload.get("template_id")

    if not template_id:
        print("❌ JSON thiếu trường 'template_id'")
        sys.exit(1)

    print(f"📦 Importing pipeline: {template_id} ({payload.get('name')})")
    print(f"   Nodes: {len(payload.get('nodes', []))}  |  Edges: {len(payload.get('edges', []))}")
    print(f"   Target: {args.url}")

    # 2. Kiểm tra template đã tồn tại chưa
    existing = get_template(args.url, template_id)

    if existing:
        if not args.update:
            print(
                f"\n⚠️  Template '{template_id}' đã tồn tại (version {existing.get('version')}).\n"
                "   Dùng --update để ghi đè, hoặc đổi template_id trong file JSON."
            )
            sys.exit(1)
        print(f"🔄 Template đã tồn tại (v{existing.get('version')}), đang update…")
        result = update_template(args.url, template_id, payload)
        print_summary(result)
    else:
        result = create_template(args.url, payload)
        print_summary(result)


if __name__ == "__main__":
    main()
