#!/usr/bin/env python3
"""
scripts/migrate_v1_to_v2.py
────────────────────────────
Data migration script: SQLite (V1) → MongoDB (V2).

Migrates all existing data from the V1 SQLite database to the new V2 MongoDB
collections using Beanie ODM.

Collections migrated:
  - llm_profiles     (LLMProfile → LLMProfileDocument)
  - agent_configs    (AgentConfig → AgentConfigDocument)
  - pipeline_runs    (PipelineRun → PipelineRunDocument)
  - pipeline_results (PipelineResult → PipelineResultDocument)

After migration, run the V2 seeder to ensure stage_configs are populated:
    python -m app.db.seed

Usage:
    # From the backend/ directory with both DBs accessible:
    python scripts/migrate_v1_to_v2.py

    # With explicit paths:
    python scripts/migrate_v1_to_v2.py \
        --sqlite-path ./auto_at.db \
        --mongo-uri mongodb://localhost:27017 \
        --mongo-db auto_at

    # Dry-run (read SQLite, do NOT write to MongoDB):
    python scripts/migrate_v1_to_v2.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("migrate_v1_to_v2")

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SQLITE_PATH = Path(__file__).parent.parent / "auto_at.db"
DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DB = "auto_at"


# ─────────────────────────────────────────────────────────────────────────────
# SQLite reader helpers
# ─────────────────────────────────────────────────────────────────────────────


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    if not path.exists():
        logger.error("SQLite database not found at: %s", path)
        sys.exit(1)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    logger.info("Connected to SQLite: %s", path)
    return conn


def _read_llm_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, name, provider, model, api_key, base_url,
               temperature, max_tokens, is_default, created_at, updated_at
        FROM llm_profiles
        ORDER BY id
        """
    )
    rows = cursor.fetchall()
    logger.info("  Found %d LLM profiles in SQLite", len(rows))
    return [dict(row) for row in rows]


def _read_agent_configs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, agent_id, display_name, stage, role, goal, backstory,
               llm_profile_id, enabled, verbose, max_iter, created_at, updated_at
        FROM agent_configs
        ORDER BY id
        """
    )
    rows = cursor.fetchall()
    logger.info("  Found %d agent configs in SQLite", len(rows))
    return [dict(row) for row in rows]


def _read_pipeline_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, document_name, document_path, llm_profile_id,
               status, agent_statuses, error, created_at, finished_at
        FROM pipeline_runs
        ORDER BY created_at
        """
    )
    rows = cursor.fetchall()
    logger.info("  Found %d pipeline runs in SQLite", len(rows))
    return [dict(row) for row in rows]


def _read_pipeline_results(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, run_id, stage, agent_id, output, created_at
        FROM pipeline_results
        ORDER BY created_at
        """
    )
    rows = cursor.fetchall()
    logger.info("  Found %d pipeline results in SQLite", len(rows))
    return [dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Data transformation helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string from SQLite into a timezone-aware datetime."""
    if not value:
        return None
    try:
        # SQLite stores datetimes without timezone info; assume UTC
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logger.warning("    Could not parse datetime value: %r — using None", value)
        return None


def _transform_llm_profile(row: dict[str, Any]) -> dict[str, Any]:
    """Transform a V1 LLMProfile row into a V2 LLMProfileDocument dict."""
    return {
        "name": row["name"],
        "provider": row["provider"],
        "model": row["model"],
        "api_key": row["api_key"],
        "base_url": row["base_url"],
        "temperature": float(row["temperature"] or 0.1),
        "max_tokens": int(row["max_tokens"] or 2048),
        "is_default": bool(row["is_default"]),
        "created_at": _parse_dt(row["created_at"]) or datetime.now(timezone.utc),
        "updated_at": _parse_dt(row["updated_at"]) or datetime.now(timezone.utc),
        # Store old SQLite ID for cross-reference during migration
        "_v1_id": int(row["id"]),
    }


def _transform_agent_config(
    row: dict[str, Any],
    profile_id_map: dict[int, str],
) -> dict[str, Any]:
    """
    Transform a V1 AgentConfig row into a V2 AgentConfigDocument dict.

    Args:
        row:            V1 AgentConfig dict from SQLite.
        profile_id_map: Mapping from V1 int profile_id → V2 MongoDB ObjectId string.
    """
    v1_profile_id = row.get("llm_profile_id")
    mongo_profile_id: Optional[str] = None
    if v1_profile_id is not None:
        mongo_profile_id = profile_id_map.get(int(v1_profile_id))
        if mongo_profile_id is None:
            logger.warning(
                "    Agent %r references missing profile id=%s — setting to None",
                row["agent_id"],
                v1_profile_id,
            )

    return {
        "agent_id": row["agent_id"],
        "display_name": row["display_name"],
        "stage": row["stage"],
        "role": row["role"],
        "goal": row["goal"],
        "backstory": row["backstory"],
        "llm_profile_id": mongo_profile_id,
        "enabled": bool(row["enabled"]),
        "verbose": bool(row["verbose"]),
        "max_iter": int(row["max_iter"] or 5),
        "is_custom": False,  # All V1 agents are treated as builtin/seeded
        "created_at": _parse_dt(row["created_at"]) or datetime.now(timezone.utc),
        "updated_at": _parse_dt(row["updated_at"]) or datetime.now(timezone.utc),
    }


def _transform_pipeline_run(
    row: dict[str, Any],
    profile_id_map: dict[int, str],
) -> dict[str, Any]:
    """Transform a V1 PipelineRun row into a V2 PipelineRunDocument dict."""
    v1_profile_id = row.get("llm_profile_id")
    mongo_profile_id: Optional[str] = None
    if v1_profile_id is not None:
        mongo_profile_id = profile_id_map.get(int(v1_profile_id))

    # Parse agent_statuses JSON blob from V1
    raw_statuses: dict[str, str] = {}
    agent_statuses_raw = row.get("agent_statuses", "{}")
    if agent_statuses_raw:
        try:
            raw_statuses = json.loads(agent_statuses_raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # Map V1 status to V2 status (V1 only had: pending, running, completed, failed)
    status = row.get("status", "completed")
    # Normalise any legacy values
    if status not in (
        "pending",
        "running",
        "paused",
        "completed",
        "failed",
        "cancelled",
    ):
        status = "completed"

    created_at = _parse_dt(row["created_at"]) or datetime.now(timezone.utc)
    finished_at = _parse_dt(row.get("finished_at"))

    return {
        "run_id": str(row["id"]),  # V1 used UUID string as PK
        "document_name": row["document_name"],
        "document_path": row["document_path"],
        "llm_profile_id": mongo_profile_id,
        "status": status,
        "current_stage": None,
        "completed_stages": [],  # Cannot reconstruct from V1 data
        "agent_statuses": raw_statuses,
        "stage_results_summary": {},
        "error": row.get("error"),
        "pause_reason": None,
        "created_at": created_at,
        "started_at": created_at,  # V1 didn't track started_at separately
        "paused_at": None,
        "resumed_at": None,
        "finished_at": finished_at,
    }


def _transform_pipeline_result(row: dict[str, Any]) -> dict[str, Any]:
    """Transform a V1 PipelineResult row into a V2 PipelineResultDocument dict."""
    # V1 stored output as JSON string; V2 stores native BSON
    raw_output = row.get("output", "")
    output: Any
    try:
        output = json.loads(raw_output) if raw_output else {}
    except (json.JSONDecodeError, TypeError):
        output = {"raw_output": str(raw_output)}

    return {
        "run_id": str(row["run_id"]),
        "stage": row["stage"],
        "agent_id": row["agent_id"],
        "output": output,
        "created_at": _parse_dt(row["created_at"]) or datetime.now(timezone.utc),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MongoDB write helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _init_mongo(uri: str, db_name: str) -> None:
    """Initialise the Beanie ODM against the target MongoDB."""
    # Add project root to sys.path so we can import app modules
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from app.config import settings
    from app.db.database import init_db

    # Override settings in-process so init_db() connects to the right DB
    object.__setattr__(settings, "MONGODB_URI", uri)
    object.__setattr__(settings, "MONGODB_DB_NAME", db_name)

    await init_db()
    logger.info("MongoDB + Beanie initialised (%s / %s)", uri, db_name)


async def _migrate_llm_profiles(
    profiles: list[dict[str, Any]],
    dry_run: bool,
) -> dict[int, str]:
    """
    Insert LLM profiles into MongoDB.

    Returns:
        Mapping from V1 int profile_id → V2 MongoDB ObjectId string.
    """
    from app.db.models import LLMProfileDocument

    id_map: dict[int, str] = {}
    skipped = 0
    inserted = 0

    for data in profiles:
        v1_id: int = data.pop("_v1_id")
        name: str = data["name"]

        # Check for duplicates
        existing = await LLMProfileDocument.find_one(LLMProfileDocument.name == name)
        if existing is not None:
            logger.info("    LLM profile %r already exists — skipping", name)
            id_map[v1_id] = str(existing.id)
            skipped += 1
            continue

        if dry_run:
            logger.info("    [DRY-RUN] Would insert LLM profile: %r", name)
            id_map[v1_id] = f"dry_run_{v1_id}"
        else:
            doc = LLMProfileDocument(**data)
            await doc.insert()
            id_map[v1_id] = str(doc.id)
            logger.debug("    Inserted LLM profile %r → %s", name, doc.id)
            inserted += 1

    logger.info(
        "  LLM profiles: %d inserted, %d skipped (already existed)",
        inserted,
        skipped,
    )
    return id_map


async def _migrate_agent_configs(
    configs: list[dict[str, Any]],
    profile_id_map: dict[int, str],
    dry_run: bool,
) -> None:
    from app.db.models import AgentConfigDocument

    skipped = 0
    inserted = 0

    for row in configs:
        data = _transform_agent_config(row, profile_id_map)
        agent_id: str = data["agent_id"]

        existing = await AgentConfigDocument.find_one(
            AgentConfigDocument.agent_id == agent_id
        )
        if existing is not None:
            logger.info("    Agent config %r already exists — skipping", agent_id)
            skipped += 1
            continue

        if dry_run:
            logger.info("    [DRY-RUN] Would insert agent config: %r", agent_id)
        else:
            doc = AgentConfigDocument(**data)
            await doc.insert()
            logger.debug("    Inserted agent config %r → %s", agent_id, doc.id)
            inserted += 1

    logger.info(
        "  Agent configs: %d inserted, %d skipped",
        inserted,
        skipped,
    )


async def _migrate_pipeline_runs(
    runs: list[dict[str, Any]],
    profile_id_map: dict[int, str],
    dry_run: bool,
) -> None:
    from app.db.models import PipelineRunDocument

    skipped = 0
    inserted = 0

    for row in runs:
        data = _transform_pipeline_run(row, profile_id_map)
        run_id: str = data["run_id"]

        existing = await PipelineRunDocument.find_one(
            PipelineRunDocument.run_id == run_id
        )
        if existing is not None:
            logger.info("    Pipeline run %r already exists — skipping", run_id[:8])
            skipped += 1
            continue

        if dry_run:
            logger.info("    [DRY-RUN] Would insert pipeline run: %r", run_id[:8])
        else:
            doc = PipelineRunDocument(**data)
            await doc.insert()
            logger.debug("    Inserted pipeline run %r → %s", run_id[:8], doc.id)
            inserted += 1

    logger.info(
        "  Pipeline runs: %d inserted, %d skipped",
        inserted,
        skipped,
    )


async def _migrate_pipeline_results(
    results: list[dict[str, Any]],
    dry_run: bool,
) -> None:
    from app.db.models import PipelineResultDocument

    skipped = 0
    inserted = 0

    for row in results:
        data = _transform_pipeline_result(row)
        run_id: str = data["run_id"]
        agent_id: str = data["agent_id"]

        # Check for duplicate (same run_id + agent_id combination)
        existing = await PipelineResultDocument.find_one(
            PipelineResultDocument.run_id == run_id,
            PipelineResultDocument.agent_id == agent_id,
        )
        if existing is not None:
            logger.debug(
                "    Pipeline result run=%r agent=%r already exists — skipping",
                run_id[:8],
                agent_id,
            )
            skipped += 1
            continue

        if dry_run:
            logger.debug(
                "    [DRY-RUN] Would insert result run=%r agent=%r",
                run_id[:8],
                agent_id,
            )
        else:
            doc = PipelineResultDocument(**data)
            await doc.insert()
            inserted += 1

    logger.info(
        "  Pipeline results: %d inserted, %d skipped",
        inserted,
        skipped,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main migration orchestrator
# ─────────────────────────────────────────────────────────────────────────────


async def migrate(
    sqlite_path: Path,
    mongo_uri: str,
    mongo_db: str,
    dry_run: bool = False,
) -> None:
    """Run the full V1 → V2 migration."""

    logger.info("=" * 60)
    logger.info("Auto-AT  V1 → V2  Data Migration")
    logger.info("  SQLite : %s", sqlite_path)
    logger.info("  MongoDB: %s / %s", mongo_uri, mongo_db)
    logger.info("  Mode   : %s", "DRY-RUN (no writes)" if dry_run else "LIVE")
    logger.info("=" * 60)

    # ── Step 1: Read all V1 data from SQLite ──────────────────────────────────
    logger.info("\n[1/5] Reading V1 data from SQLite …")
    conn = _connect_sqlite(sqlite_path)

    try:
        v1_profiles = _read_llm_profiles(conn)
        v1_agents = _read_agent_configs(conn)
        v1_runs = _read_pipeline_runs(conn)
        v1_results = _read_pipeline_results(conn)
    finally:
        conn.close()

    logger.info(
        "  Totals: %d profiles, %d agents, %d runs, %d results",
        len(v1_profiles),
        len(v1_agents),
        len(v1_runs),
        len(v1_results),
    )

    # ── Step 2: Initialise MongoDB ────────────────────────────────────────────
    logger.info("\n[2/5] Initialising MongoDB connection …")
    if not dry_run:
        await _init_mongo(mongo_uri, mongo_db)
    else:
        logger.info("  [DRY-RUN] Skipping MongoDB initialisation.")

    # ── Step 3: Migrate LLM profiles ─────────────────────────────────────────
    logger.info("\n[3/5] Migrating LLM profiles …")
    if not dry_run:
        profile_id_map = await _migrate_llm_profiles(v1_profiles, dry_run=False)
    else:
        # In dry-run, just pretend with a synthetic map
        profile_id_map = {row["id"]: f"dry_{row['id']}" for row in v1_profiles}
        for row in v1_profiles:
            logger.info("  [DRY-RUN] Would migrate profile: %r", row["name"])

    # ── Step 4: Migrate agent configs ─────────────────────────────────────────
    logger.info("\n[4/5] Migrating agent configs …")
    if not dry_run:
        await _migrate_agent_configs(v1_agents, profile_id_map, dry_run=False)
    else:
        for row in v1_agents:
            logger.info("  [DRY-RUN] Would migrate agent: %r", row["agent_id"])

    # ── Step 5: Migrate pipeline runs + results ───────────────────────────────
    logger.info("\n[5/5] Migrating pipeline runs and results …")
    if not dry_run:
        await _migrate_pipeline_runs(v1_runs, profile_id_map, dry_run=False)
        await _migrate_pipeline_results(v1_results, dry_run=False)
    else:
        for row in v1_runs:
            logger.info(
                "  [DRY-RUN] Would migrate run: %r (%s)",
                str(row["id"])[:8],
                row["status"],
            )
        logger.info(
            "  [DRY-RUN] Would migrate %d pipeline results",
            len(v1_results),
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info(
        "Migration %s", "simulation complete (DRY-RUN)" if dry_run else "complete ✓"
    )
    logger.info(
        "Next steps:\n"
        "  1. Start MongoDB and the V2 backend to verify data integrity.\n"
        "  2. Run the V2 seeder to ensure stage_configs are present:\n"
        "       python -m app.db.seed\n"
        "  3. Test the API endpoints with the migrated data.\n"
        "  4. Once validated, decommission the SQLite database file."
    )
    logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate Auto-AT data from SQLite (V1) to MongoDB (V2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help=f"Path to the V1 SQLite database file. Default: {DEFAULT_SQLITE_PATH}",
    )
    parser.add_argument(
        "--mongo-uri",
        default=DEFAULT_MONGO_URI,
        help=f"MongoDB connection URI. Default: {DEFAULT_MONGO_URI}",
    )
    parser.add_argument(
        "--mongo-db",
        default=DEFAULT_MONGO_DB,
        help=f"MongoDB database name. Default: {DEFAULT_MONGO_DB}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read SQLite and print what would be migrated, but do NOT write to MongoDB.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(
        migrate(
            sqlite_path=args.sqlite_path,
            mongo_uri=args.mongo_uri,
            mongo_db=args.mongo_db,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
