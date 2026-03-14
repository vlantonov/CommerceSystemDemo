#!/usr/bin/env python3
"""
Database index migration for Commerce System Demo.

Creates performance indexes not managed by SQLAlchemy's create_all (GIN/trigram)
and ensures all model-declared B-tree indexes exist in the running database.

Safe to run multiple times — all statements use IF NOT EXISTS.

Usage (from project root):
    python scripts/migrate_indexes.py [--database-url URL]

DATABASE_URL from the environment / .env is used when --database-url is omitted.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import asyncpg

# ---------------------------------------------------------------------------
# Index definitions
# Each entry: (human description, DDL statement)
# Statements run outside any transaction so CONCURRENTLY is always safe.
# ---------------------------------------------------------------------------
_MIGRATIONS: list[tuple[str, str]] = [
    # pg_trgm must exist before the GIN index can be created.
    (
        "extension pg_trgm",
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    ),
    # B-tree indexes declared in the SQLAlchemy models.
    # create_all creates these for new databases; this backfills existing ones.
    (
        "ix_product_price  (B-tree, price range queries / COUNT skip)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_product_price"
        " ON product(price)",
    ),
    (
        "ix_product_category_id  (B-tree, category filter join)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_product_category_id"
        " ON product(category_id)",
    ),
    (
        "ix_category_parent_id  (B-tree, recursive CTE join)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_category_parent_id"
        " ON category(parent_id)",
    ),
    # New GIN trigram index — enables index-accelerated ILIKE '%text%' search.
    (
        "ix_product_title_trgm  (GIN trigram, ILIKE title search)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_product_title_trgm"
        " ON product USING GIN (title gin_trgm_ops)",
    ),
]


def _asyncpg_url(database_url: str) -> str:
    """Remove the SQLAlchemy dialect prefix so asyncpg can use the DSN directly."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _run(database_url: str) -> None:
    url = _asyncpg_url(database_url)
    # Mask password in printed output.
    safe_url = url.split("@", 1)[-1] if "@" in url else url
    print(f"Connecting to {safe_url} …")

    # asyncpg operates in autocommit mode by default (no BEGIN/COMMIT wrapper),
    # which is required for CREATE INDEX CONCURRENTLY.
    conn = await asyncpg.connect(url)
    try:
        errors: list[str] = []
        for description, sql in _MIGRATIONS:
            print(f"  {description} … ", end="", flush=True)
            try:
                await conn.execute(sql)
                print("ok")
            except asyncpg.exceptions.UniqueViolationError:
                print("already exists")
            except Exception as exc:
                print(f"FAILED\n    {exc}")
                errors.append(description)

        print()
        if errors:
            print(f"Completed with {len(errors)} error(s):", file=sys.stderr)
            for name in errors:
                print(f"  - {name}", file=sys.stderr)
            sys.exit(1)
        else:
            print("All migrations applied successfully.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--database-url",
        metavar="URL",
        help="postgresql+asyncpg:// or postgresql:// DSN (overrides DATABASE_URL / .env)",
    )
    args = parser.parse_args()

    if args.database_url:
        database_url = args.database_url
    else:
        try:
            from app.core.config import get_settings  # noqa: PLC0415

            database_url = get_settings().database_url
        except Exception as exc:
            print(f"Could not load app settings: {exc}", file=sys.stderr)
            print("Pass --database-url or set DATABASE_URL.", file=sys.stderr)
            sys.exit(1)

    asyncio.run(_run(database_url))


if __name__ == "__main__":
    main()
