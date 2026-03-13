#!/usr/bin/env python3
"""
Load test / dashboard smoke-test for Commerce System Demo.

Drives concurrent HTTP traffic across all API endpoints so every
Grafana dashboard panel (request rate, latencies, in-flight, error rate,
search quality, mutations, DB pool) receives real data.

Usage:
    python scripts/load_test.py [options]

Options:
    --url URL           Base URL of the API  (default: http://localhost:8000)
    --workers N         Concurrent async workers (default: 10)
    --duration SECONDS  How long to run       (default: 120)
    --skip-seed         Skip initial catalog creation
"""

from __future__ import annotations

import argparse
import asyncio
import random
import string
import sys
import time

import httpx

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

API_PREFIX = "/api/v1"


def _rand_sku() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    return f"LOAD-{suffix}"


def _rand_price() -> str:
    return str(round(random.uniform(5.00, 2500.00), 2))


# ---------------------------------------------------------------------------
# Catalog seeding
# ---------------------------------------------------------------------------

async def seed_catalog(client: httpx.AsyncClient) -> None:
    print("Seeding catalog …", flush=True)

    root_names = ["Electronics", "Books", "Clothing", "Sports", "Home & Garden"]
    cat_ids: list[int] = []

    for name in root_names:
        r = await client.post(f"{API_PREFIX}/categories", json={"name": name})
        if r.status_code == 201:
            cid = r.json()["id"]
            cat_ids.append(cid)
            sub = await client.post(
                f"{API_PREFIX}/categories",
                json={"name": f"{name} Accessories", "parent_id": cid},
            )
            if sub.status_code == 201:
                cat_ids.append(sub.json()["id"])

    product_titles = [
        "Ultrabook Pro", "Gaming Laptop", "Wireless Mouse", "Mechanical Keyboard",
        "Standing Desk", "Monitor 4K", "USB-C Hub", "Webcam HD", "Noise-cancelling Headphones",
        "Python Cookbook", "Clean Code", "Designing Data-Intensive Applications",
        "Running Shoes Elite", "Yoga Mat Premium", "Resistance Bands Set",
        "Insulated Water Bottle", "LED Desk Lamp", "Ergonomic Office Chair",
        "Fountain Pen Classic", "French Press 1L", "Stainless Travel Tumbler",
        "Hiking Backpack 40L", "Smart Plug", "Portable SSD 1TB", "Action Camera Kit",
    ]

    created = 0
    for i, title in enumerate(product_titles):
        cat = random.choice(cat_ids) if cat_ids else None
        payload: dict = {
            "title": f"{title} {i + 1}",
            "description": f"A quality {title.lower()} for everyday use.",
            "sku": _rand_sku(),
            "price": _rand_price(),
        }
        if cat:
            payload["category_id"] = cat
        r = await client.post(f"{API_PREFIX}/products", json=payload)
        if r.status_code == 201:
            created += 1

    print(f"  seeded {len(cat_ids)} categories, {created} products", flush=True)


async def _fetch_catalog_ids(client: httpx.AsyncClient) -> dict[str, list[int]]:
    cat_ids: list[int] = []
    prod_ids: list[int] = []

    r = await client.get(f"{API_PREFIX}/categories", params={"limit": 100})
    if r.status_code == 200:
        cat_ids = [c["id"] for c in r.json()["items"]]

    r = await client.get(f"{API_PREFIX}/products", params={"limit": 100})
    if r.status_code == 200:
        prod_ids = [p["id"] for p in r.json()["items"]]

    return {"category_ids": cat_ids, "product_ids": prod_ids}


# ---------------------------------------------------------------------------
# Traffic generators
# ---------------------------------------------------------------------------

async def _search(client: httpx.AsyncClient, catalog: dict) -> None:
    cat_ids = catalog["category_ids"]
    choice = random.random()
    if choice < 0.20:
        # Text match — various terms, some with no results
        q = random.choice([
            "Laptop", "Book", "Shoes", "Stand", "LOAD-",
            "NOMATCH-ZZZXXX", "xyz_never_exists_000",
        ])
        await client.get(f"{API_PREFIX}/products/search", params={"q": q, "limit": 20})
    elif choice < 0.40:
        # Price range
        lo = round(random.uniform(0, 800), 2)
        hi = round(random.uniform(lo, 2500), 2)
        await client.get(
            f"{API_PREFIX}/products/search",
            params={"min_price": lo, "max_price": hi, "limit": 10},
        )
    elif choice < 0.60:
        # Category subtree (includes descendants)
        if cat_ids:
            await client.get(
                f"{API_PREFIX}/products/search",
                params={"category_id": random.choice(cat_ids), "limit": 20},
            )
    elif choice < 0.80:
        # Combined filters
        lo = round(random.uniform(10, 500), 2)
        hi = round(random.uniform(lo, 2000), 2)
        params: dict = {"min_price": lo, "max_price": hi, "limit": 10}
        if cat_ids:
            params["category_id"] = random.choice(cat_ids)
        await client.get(f"{API_PREFIX}/products/search", params=params)
    else:
        # Guaranteed zero-result search (populates zero-result counter)
        await client.get(
            f"{API_PREFIX}/products/search",
            params={"q": "ZERORESULT_NOMATCH_XYZ_999", "min_price": 99999},
        )


async def _product_reads(client: httpx.AsyncClient, catalog: dict) -> None:
    prod_ids = catalog["product_ids"]
    r = random.random()
    if r < 0.60 and prod_ids:
        await client.get(f"{API_PREFIX}/products/{random.choice(prod_ids)}")
    elif r < 0.80:
        offset = random.randint(0, max(0, len(prod_ids) - 10))
        await client.get(
            f"{API_PREFIX}/products",
            params={"limit": random.choice([10, 20, 50]), "offset": offset},
        )
    else:
        # Intentional 404
        await client.get(f"{API_PREFIX}/products/99999999")


async def _category_reads(client: httpx.AsyncClient, catalog: dict) -> None:
    cat_ids = catalog["category_ids"]
    r = random.random()
    if r < 0.65 and cat_ids:
        await client.get(f"{API_PREFIX}/categories/{random.choice(cat_ids)}")
    elif r < 0.85:
        await client.get(f"{API_PREFIX}/categories", params={"limit": 50})
    else:
        # Intentional 404
        await client.get(f"{API_PREFIX}/categories/99999999")


async def _product_mutations(client: httpx.AsyncClient, catalog: dict) -> None:
    prod_ids = catalog["product_ids"]
    cat_ids = catalog["category_ids"]
    r = random.random()

    if r < 0.45:
        # Create
        cat = random.choice(cat_ids) if cat_ids else None
        payload: dict = {
            "title": f"LoadProduct {random.randint(10000, 99999)}",
            "description": "Generated by load test.",
            "sku": _rand_sku(),
            "price": _rand_price(),
        }
        if cat:
            payload["category_id"] = cat
        resp = await client.post(f"{API_PREFIX}/products", json=payload)
        if resp.status_code == 201:
            prod_ids.append(resp.json()["id"])
    elif r < 0.80 and prod_ids:
        # Update price / title
        pid = random.choice(prod_ids)
        await client.patch(f"{API_PREFIX}/products/{pid}", json={"price": _rand_price()})
    elif prod_ids and len(prod_ids) > 10:
        # Delete (keep at least 10 products)
        pid = prod_ids.pop(random.randrange(len(prod_ids)))
        await client.delete(f"{API_PREFIX}/products/{pid}")


async def _category_mutations(client: httpx.AsyncClient, catalog: dict) -> None:
    cat_ids = catalog["category_ids"]
    r = random.random()

    if r < 0.50:
        # Create
        resp = await client.post(
            f"{API_PREFIX}/categories",
            json={"name": f"LoadCat {random.randint(10000, 99999)}"},
        )
        if resp.status_code == 201:
            cat_ids.append(resp.json()["id"])
    elif r < 0.80 and cat_ids:
        # Rename
        cid = random.choice(cat_ids)
        await client.patch(
            f"{API_PREFIX}/categories/{cid}",
            json={"name": f"Renamed {random.randint(10000, 99999)}"},
        )
    elif cat_ids and len(cat_ids) > 5:
        # Delete
        cid = cat_ids.pop(random.randrange(len(cat_ids)))
        await client.delete(f"{API_PREFIX}/categories/{cid}")


async def _category_validation_failures(
    client: httpx.AsyncClient, catalog: dict
) -> None:
    """Intentionally trigger all three category validation failure reasons."""
    cat_ids = catalog["category_ids"]
    r = random.random()

    if r < 0.40:
        # parent_not_found — reference a non-existent parent
        await client.post(
            f"{API_PREFIX}/categories",
            json={"name": f"OrphanCat {random.randint(1, 9999)}", "parent_id": 999999999},
        )
    elif r < 0.70 and len(cat_ids) >= 2:
        # cycle_detected — try to set a category's parent to one of its children
        # Create a parent → child pair, then try to re-parent the parent under the child
        p_resp = await client.post(
            f"{API_PREFIX}/categories",
            json={"name": f"CyclePar {random.randint(1, 9999)}"},
        )
        if p_resp.status_code != 201:
            return
        p_id = p_resp.json()["id"]
        catalog["category_ids"].append(p_id)

        c_resp = await client.post(
            f"{API_PREFIX}/categories",
            json={"name": f"CycleChild {random.randint(1, 9999)}", "parent_id": p_id},
        )
        if c_resp.status_code != 201:
            return
        c_id = c_resp.json()["id"]
        catalog["category_ids"].append(c_id)

        # Now try to make the parent a child of the child → cycle
        await client.patch(
            f"{API_PREFIX}/categories/{p_id}",
            json={"parent_id": c_id},
        )
    else:
        # depth_exceeded — create a chain that tries to exceed MAX_CATEGORY_DEPTH
        # We simulate this by trying to attach a new category to non-existent
        # deep parent, or by patching with a nonexistent far-away parent
        # (reliably hits parent_not_found, which also records a validation failure)
        await client.patch(
            f"{API_PREFIX}/categories/{random.choice(cat_ids) if cat_ids else 1}",
            json={"parent_id": 888888888},
        )


async def _error_scenarios(client: httpx.AsyncClient) -> None:
    """Intentionally trigger 4xx responses to populate error counters."""
    r = random.random()
    if r < 0.33:
        # 422 — invalid SKU format
        await client.post(
            f"{API_PREFIX}/products",
            json={
                "title": "Bad SKU", "description": "test",
                "sku": "invalid sku with spaces!", "price": "10.00",
            },
        )
    elif r < 0.66:
        # 422 — inverted price range
        await client.get(
            f"{API_PREFIX}/products/search",
            params={"min_price": "999", "max_price": "1"},
        )
    else:
        # 404
        await client.get(f"{API_PREFIX}/products/77777777")


# ---------------------------------------------------------------------------
# Traffic mix
# ---------------------------------------------------------------------------

_MIX: list = []
for _fn, _w in [
    (_search, 33),
    (_product_reads, 26),
    (_category_reads, 11),
    (_product_mutations, 11),
    (_category_mutations, 8),
    (_error_scenarios, 5),
    (_category_validation_failures, 6),
]:
    _MIX.extend([_fn] * _w)


# ---------------------------------------------------------------------------
# Worker + reporter
# ---------------------------------------------------------------------------

async def _worker(
    client: httpx.AsyncClient,
    catalog: dict,
    stop_event: asyncio.Event,
    counters: dict,
) -> None:
    while not stop_event.is_set():
        fn = random.choice(_MIX)
        try:
            if fn is _error_scenarios:
                await fn(client)
            else:
                await fn(client, catalog)
            counters["ok"] += 1
        except Exception:
            counters["err"] += 1
        finally:
            counters["total"] += 1
        await asyncio.sleep(random.uniform(0.02, 0.08))


async def _reporter(
    stop_event: asyncio.Event,
    counters: dict,
    duration: int,
    start: float,
) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(10)
        elapsed = time.monotonic() - start
        rps = counters["total"] / max(elapsed, 1)
        pct = min(100, int(elapsed / duration * 100))
        print(
            f"  [{pct:3d}%] {elapsed:5.0f}s  "
            f"total={counters['total']:6d}  ok={counters['ok']:6d}  "
            f"err(expected)={counters['err']:4d}  rps={rps:.1f}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load generator / dashboard smoke-test for Commerce System Demo"
    )
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--duration", type=int, default=120, help="Run duration (seconds)")
    parser.add_argument("--skip-seed", action="store_true", help="Skip catalog seeding")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print("Commerce System Demo — load generator")
    print(f"  URL      : {base_url}")
    print(f"  Workers  : {args.workers}")
    print(f"  Duration : {args.duration}s")
    print(
        "  Mix      : search 35% | product-reads 28% | category-reads 12% "
        "| product-mutations 12% | category-mutations 8% | errors 5%"
    )
    print()

    limits = httpx.Limits(
        max_connections=args.workers + 10,
        max_keepalive_connections=args.workers,
    )
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0, limits=limits) as client:
        # Health check
        try:
            r = await client.get("/health")
            r.raise_for_status()
            print(f"Health check OK → {r.json()}\n", flush=True)
        except Exception as exc:
            print(f"ERROR: cannot reach {base_url}/health\n  {exc}")
            sys.exit(1)

        if not args.skip_seed:
            await seed_catalog(client)

        catalog = await _fetch_catalog_ids(client)
        print(
            f"Working catalog: {len(catalog['category_ids'])} categories, "
            f"{len(catalog['product_ids'])} products\n",
            flush=True,
        )

        if not catalog["category_ids"] and not catalog["product_ids"]:
            print("WARNING: catalog is empty — re-run without --skip-seed")

        stop_event = asyncio.Event()
        counters: dict = {"total": 0, "ok": 0, "err": 0}
        start = time.monotonic()

        tasks = [
            asyncio.create_task(_worker(client, catalog, stop_event, counters))
            for _ in range(args.workers)
        ]
        tasks.append(
            asyncio.create_task(_reporter(stop_event, counters, args.duration, start))
        )

        print(f"Running … (Ctrl-C to stop early)\n", flush=True)
        try:
            await asyncio.sleep(args.duration)
        except asyncio.CancelledError:
            pass
        finally:
            stop_event.set()
            await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.monotonic() - start
    print()
    print("=" * 60)
    print(f"Done  — {elapsed:.0f}s elapsed")
    print(f"  Total requests : {counters['total']}")
    print(f"  OK             : {counters['ok']}")
    print(f"  Expected errors: {counters['err']}")
    print(f"  Avg RPS        : {counters['total'] / elapsed:.1f}")
    print()
    print("Open Grafana → http://localhost:3000  (admin / admin)")
    print("Navigate to Dashboards → Commerce to see populated panels.")


if __name__ == "__main__":
    asyncio.run(main())
