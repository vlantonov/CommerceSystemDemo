# Commerce System Demo

## Table of Contents

* [1. Task description](#1-task-description)
* [2. Functional requirements](#2-functional-requirements)
   * [2.1. Models](#21-models)
      * [2.1.1 Product model](#211-product-model)
      * [2.1.2 Category model](#212-category-model)
   * [2.2. Operations](#22-operations)
* [3. Non-Functional Requirements](#3-non-functional-requirements)
* [4. Requirements Refinement Decisions](#4-requirements-refinement-decisions)
   * [4.1. FastAPI or Django framework](#41-fastapi-or-django-framework)
   * [4.2. Constraints to text fields according to the established practices in existing systems](#42-constraints-to-text-fields-according-to-the-established-practices-in-existing-systems)
   * [4.3. The format and the storage of the image is to be chosen following the established practices in existing systems](#43-the-format-and-the-storage-of-the-image-is-to-be-chosen-following-the-established-practices-in-existing-systems)
   * [4.4. The format for the unique product identifier (SKU) is to be chosen following the established practices in existing systems](#44-the-format-for-the-unique-product-identifier-sku-is-to-be-chosen-following-the-established-practices-in-existing-systems)
   * [4.5. The name of the category constraints](#45-the-name-of-the-category-constraints)
   * [4.6. The parent field of the category](#46-the-parent-field-of-the-category)
   * [4.7. Pagination of the returned results](#47-pagination-of-the-returned-results)
   * [4.8. Database to store products, categories and images](#48-database-to-store-products-categories-and-images)
   * [4.9. Unit test for real database or for mock database](#49-unit-test-for-real-database-or-for-mock-database)
* [5. High-Level Design](#5-high-level-design)
   * [5.1. Architecture Notes](#51-architecture-notes)
* [6. Database Design](#6-database-design)
   * [6.1. Entity Relationship Diagram](#61-entity-relationship-diagram)
   * [6.2. Schema Notes](#62-schema-notes)
   * [6.3. Constraints and Indexes](#63-constraints-and-indexes)
* [7. API Design](#7-api-design)
   * [7.1. API Conventions](#71-api-conventions)
   * [7.2. Category Endpoints](#72-category-endpoints)
   * [7.3. Product Endpoints](#73-product-endpoints)
   * [7.4. Search Endpoint](#74-search-endpoint)
   * [7.5. Request and Response Schemas](#75-request-and-response-schemas)
* [8. Run and Test](#8-run-and-test)
   * [8.1. Setup](#81-setup)
   * [8.2. Development Server](#82-development-server)
   * [8.3. Testing](#83-testing)
* [9. Observability](#9-observability)
   * [9.1. What is instrumented](#91-what-is-instrumented)
   * [9.2. Telemetry flow](#92-telemetry-flow)
   * [9.3. Local stack](#93-local-stack)
   * [9.4. Grafana dashboards](#94-grafana-dashboards)
   * [9.5. Alerting rules (P1)](#95-alerting-rules-p1)
   * [9.6. How to exercise the dashboards](#96-how-to-exercise-the-dashboards)
* [10. Implemented Improvements](#10-implemented-improvements)
   * [10.1. Application and Runtime](#101-application-and-runtime)
   * [10.2. Database and Query Path](#102-database-and-query-path)
   * [10.3. Logging and Metrics Path](#103-logging-and-metrics-path)
   * [10.4. Validation and Benchmarks](#104-validation-and-benchmarks)
* [11. Investigation Conclusions on 200ms Target](#11-investigation-conclusions-on-200ms-target)

## 1. Task description
Create a service which handles operations on products in an E-commerce system.

## 2. Functional requirements

### 2.1. Models
* There should be two models - Product and Category.
* Text fields should be able to support short text input, which may not be in English/Bulgarian only.
* Text fields the established practices in existing systems.
* Additional fields may be added to models in the future.

#### 2.1.1 Product model
* title - text field
* description - text field
* image
* unique product identifier (SKU)
* price. Should not lose precision when rounded.
* category - link to a category model. Can be empty.

#### 2.1.2 Category model
* name - text field
* parent - link to category model. Maximum depth of nesting of children under parent is 100.

### 2.2. Operations
* CRUD operations for both models.
* API endpoint to search and filter all products matching:
    * certain name/SKU
    * within a price range
    * under a certain category.
    * additional filters may be added
* Range borders are inclusive.
* Returned results do not need to be sorted.
* Search for a certain category should return child categories results too.
* On deletion of the category all linked to it products are to be unlinked. 
* On deletion of the parent category the children categories are to be deleted and all linked products are to be unlinked.

## 3. Non-Functional Requirements
* Use FastAPI or Django frameworks
* Unit tests for the search functionality
* The expectation is that endpoints return results within 200ms. If there are technical difficulties in achieving such latency, the reasons should be justified.
* Expected number of products: tens of thousands
* Expected number of categories: thousands
* Users per day: thousands
* No need for user authorization
* Multiple parallel connections to service

## 4. Requirements Refinement Decisions

### 4.1. FastAPI or Django framework
The **FastAPI** was chosen:
* Supports `async/await` throughout, enabling parallel DB queries and concurrent connections without threading overhead - according to the requirements for `low latency` and `multiple parallel connections`
* Built-in validation via [Pydantic](https://docs.pydantic.dev/latest/) to be used for input data contraints
* Auto-generated docs via OpenAPI/Swagger UI out of the box ([FastAPI docs](https://fastapi.tiangolo.com/features/))
* Easier to pick up compared to Django with great example-driven documentation.
* Django would be preferable if ORM ecosystem, admin panel, or auth are required.
* References:
   * [Django vs. FastAPI: A Comparison](https://blog.jetbrains.com/pycharm/2023/12/django-vs-fastapi-which-is-the-best-python-web-framework/#django-vs.-fastapi-a-comparison)
   * [A Close Look at a FastAPI Example Application](https://realpython.com/fastapi-python-web-apis/)
   * [Get Started With Django: Build a Portfolio App](https://realpython.com/get-started-with-django-1/)

### 4.2. Constraints to text fields according to the established practices in existing systems
* Use [UTF-8 encoding](https://en.wikipedia.org/wiki/UTF-8) capable of representing all Unicode characters
* `Product.title` : 255 chars (`VARCHAR(255)`)
* `Product.description` : 10000 chars (`TEXT`)
* `Category.name`: 255 chars (`VARCHAR(255)`)
* References:
   * [Shopify Product description](https://shopify.dev/docs/api/admin-graphql/latest/objects/Product#field-Product.fields.description)
   * [Shopify Product Description Length: Best Practices for SEO and Conversions](https://lettercounter.org/blog/shopify-product-description-length/)

### 4.3. The format and the storage of the image is to be chosen following the established practices in existing systems
* Store a URL string (`VARCHAR(2083)`)
* Storing binary image data in the database worsens query performance, increases backup sizes and traffic.
* Accepted formats: JPEG (universal), PNG (universal), WebP (modern optimized delivery).
* References:
   * [Shopify Product Image resource](https://shopify.dev/docs/api/admin-rest/2024-01/resources/product-image)
   * [What is the Best URL Length Limit for SEO: Maximum URL Length Characters](https://serpstat.com/blog/how-long-should-be-the-page-url-length-for-seo/)

### 4.4. The format for the unique product identifier (SKU) is to be chosen following the established practices in existing systems
* Alphanumeric string (`VARCHAR(100)`)
* Must be unique per system (`UNIQUE` constraint in DB)
* Must be present (`NOT NULL` constraint in DB)
* Normalized to upper-case on write to prevent duplicates
* Validation regex: `^[A-Z0-9_-]{1,100}$` (enforce at the API layer via Pydantic)
* References:
   * [Understanding SKU formats](https://support.ecwid.com/hc/en-us/articles/360011125640-Understanding-SKU-formats)
   * [Shopify SKU guidance](https://help.shopify.com/en/manual/products/details/sku)
   * [What is a SKU - and how does it help ecommerce sellers?](https://sell.amazon.com/es/blog/sku-definition-guide)

### 4.5. The name of the category constraints
* Use [UTF-8 encoding](https://en.wikipedia.org/wiki/UTF-8) capable of representing all Unicode characters
* String 255 chars (`VARCHAR(255)`)
* Must be present (`NOT NULL` constraint in DB) and not empty (enforce `min_length=1` in Pydantic)
* Must be unique per same parent (composite unique constraint on `(parent_id, name)`)
* References:
   * [Shopify Product Category](https://shopify.dev/docs/api/admin-graphql/latest/objects/ProductCategory)
   * [Magento categories query](https://developer.adobe.com/commerce/webapi/graphql/schema/products/queries/categories/)

### 4.6. The parent field of the category
* Adjacency List with recursive CTE (Common Table Expression) queries. Self-referencing foreign key, nullable.
* DB column - `parent_id INTEGER REFERENCES category(id) ON DELETE CASCADE`
* Root categories - `parent_id IS NULL`
* Max depth: 100 (validated at the application layer before insert/update)
* Subtree queries: PostgreSQL **recursive CTEs** (`WITH RECURSIVE`)
* Cascade delete: `ON DELETE CASCADE` at DB level — deleting a parent removes all descendants. Product unlinking handled via `ON DELETE SET NULL` on `product.category_id`.
* For the "search returns child results too" requirement, the recursive CTE fetches all descendant category IDs first, then filters products with `WHERE category_id IN (...)`.
* Why Adjacency List over Materialized Path or Nested Sets?
   * Simplest model; category count is in the `thousands` — recursive CTEs on PostgreSQL handle this efficiently.
   * Writes (add/move/delete categories) are O(1) — no tree rebalancing needed.
   * Max depth of 100 is enforceable at the application layer during writes
   * Schema: `parent_id = ForeignKey('self', null=True, on_delete=SET_NULL)` — but given the requirement that deleting a parent deletes all children, use `on_delete=CASCADE` for the FK constraint
* References:
   * [PostgreSQL recursive CTE docs](https://www.postgresql.org/docs/current/queries-with.html#QUERIES-WITH-RECURSIVE)

### 4.7. Pagination of the returned results
* With tens of thousands of products, pagination is mandatory for the search endpoint
* Decision: Offset-based pagination with `limit` / `offset` query parameters
* Dataset is tens of thousands of products — offset/limit with proper indexes performs well within 200 ms.
* Simpler for clients to implement (random page access).
* `total` count is cheap with proper indexes on the filtered columns.
* Trade-off: Results do not need to be sorted (per requirements), so cursor pagination has no anchor advantage.
* Trade-off: Offset pagination (`LIMIT x OFFSET y`) degrades at large offsets — the DB must scan and discard rows. Avoid for deep pages.
* Trade-off: Cursor-based (keyset) pagination uses a stable pointer (e.g., `?cursor=<last_id>`) and is `O(1)` regardless of page depth.
* Trade-off: Cursor-based is production standard when dataset is millions
* References:
   * [FastAPI pagination patterns](https://fastapi.tiangolo.com/tutorial/query-params/)
   * [Stripe API pagination](https://stripe.com/docs/api/pagination)
   * [Shopify REST API pagination](https://shopify.dev/docs/api/usage/pagination-rest)

### 4.8. Database to store products, categories and images
* PostgreSQL with `asyncpg` (via SQLAlchemy 2.0 async) gives the best combination of correctness (exact decimals, recursive CTEs, cascading deletes) and performance (async I/O, rich indexing).
* Supports: Recursive CTEs , `DECIMAL` precision, full UTF-8, concurrent writes, async driver for FastAPI and index types
* SQLite has limited decimal precision, no support of concurrent writes and no index types
* MySQL requires explicit config for UTF-8 and has limited index types
* Key indexes:
   * `product.sku` — unique B-tree
   * `product.category_id` — B-tree (for category filter + cascade unlink)
   * `product.price` — B-tree (for range queries)
   * `product.title` — GIN trigram index (`pg_trgm`) for partial-match search
   * `category.parent_id` — B-tree (for recursive CTE traversal)
* References:
   * [PostgreSQL numeric](https://www.postgresql.org/docs/current/datatype-numeric.html)
   * [asyncpg — fast PostgreSQL driver](https://github.com/MagicStack/asyncpg)
   * [SQLAlchemy 2.0 async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

### 4.9. Unit test for real database or for mock database
* Decision: Real database (PostgreSQL) via test containers or an in-process test database.
* Mock DB is fast, but doesn't test real SQL, recursive CTEs, cascades, indexes
* Real DB (test container) - tests actual queries, constraints, cascade behavior. However it is slower (~seconds startup)

## 5. High-Level Design

The service is best modeled as a layered API application. The API layer handles transport concerns, Pydantic enforces request and response contracts, application services own business rules, and the persistence layer isolates database access. PostgreSQL remains the system of record for products and categories, while product images are stored externally and referenced by URL.

```mermaid
flowchart TB
   client[Clients<br/>Web UI / Admin UI / External Systems]
   docs[OpenAPI / Swagger UI]

   client --> api
   docs --> api

   subgraph service[Commerce Service]
      direction TB

      api[FastAPI Routers<br/>Products / Categories / Search]
      schemas[Pydantic Schemas<br/>Validation / Normalization / Serialization]
      app[Application Services<br/>CRUD / Search / Category Tree Rules]
      repo[Persistence Layer<br/>SQLAlchemy 2.0 Async Repositories]
      search[Search Composition<br/>Name or SKU / Price Range / Category Subtree / Pagination]

      api --> schemas
      schemas --> app
      app --> repo
      app --> search
      search --> repo
   end

   subgraph data[Data Platform]
      direction LR

      db[(PostgreSQL)]
      images[(Object Storage or CDN<br/>Image files)]
      idx[Index Strategy<br/>SKU unique / price / category_id / parent_id / trigram title]
      tree[Category Hierarchy<br/>Adjacency list + recursive CTE]
      integrity[Referential Integrity<br/>category.parent_id ON DELETE CASCADE<br/>product.category_id ON DELETE SET NULL]

      db --- idx
      db --- tree
      db --- integrity
   end

   repo --> db
   repo --> images

   tests[Integration Tests<br/>pytest + real PostgreSQL test DB] --> api
```

### 5.1. Architecture Notes
* Layered design keeps request validation, business logic, and persistence concerns separate.
* PostgreSQL is the source of truth for products, categories, prices, and relational constraints.
* Product image binaries should live outside the relational database; only image URLs and metadata belong in the service data model.
* Category subtree search is implemented through recursive CTE queries over an adjacency-list category structure.
* Search performance relies on targeted indexes and offset-based pagination for the current scale of tens of thousands of products.

## 6. Database Design

The database design uses PostgreSQL as the primary transactional store. The schema keeps the core model deliberately small: categories are stored as a self-referencing hierarchy, products reference categories optionally, and image assets are represented as URLs rather than binary blobs. This keeps writes simple, supports recursive category traversal efficiently, and preserves room for future fields without redesigning the core relationships.

### 6.1. Entity Relationship Diagram

```mermaid
erDiagram
   CATEGORY ||--o{ CATEGORY : parent_of
   CATEGORY o|--o{ PRODUCT : classifies

   CATEGORY {
      bigint id PK
      varchar_255 name
      bigint parent_id FK
      timestamptz created_at
      timestamptz updated_at
   }

   PRODUCT {
      bigint id PK
      varchar_255 title
      text description
      varchar_2083 image_url
      varchar_100 sku UK
      numeric_12_2 price
      bigint category_id FK
      timestamptz created_at
      timestamptz updated_at
   }
```

### 6.2. Schema Notes
* `category.id` and `product.id` should be surrogate primary keys generated by PostgreSQL identity columns.
* `category.parent_id` is nullable so root categories can exist without a parent.
* `product.category_id` is nullable because a product may remain in the system after its category is deleted.
* `product.sku` is the external business identifier; it should be normalized to uppercase before persistence.
* `product.price` should use `NUMERIC(12,2)` so prices are stored exactly and do not lose precision.
* `image_url` stores the external object location only; binaries stay in object storage or a CDN-backed asset store.
* `created_at` and `updated_at` timestamps are recommended on both tables for auditability and operational debugging.

Example logical DDL:

```sql
CREATE TABLE category (
   id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
   name VARCHAR(255) NOT NULL,
   parent_id BIGINT REFERENCES category(id) ON DELETE CASCADE,
   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
   updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
   CONSTRAINT uq_category_parent_name UNIQUE (parent_id, name)
);

CREATE TABLE product (
   id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
   title VARCHAR(255) NOT NULL,
   description TEXT NOT NULL,
   image_url VARCHAR(2083),
   sku VARCHAR(100) NOT NULL,
   price NUMERIC(12,2) NOT NULL,
   category_id BIGINT REFERENCES category(id) ON DELETE SET NULL,
   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
   updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
   CONSTRAINT uq_product_sku UNIQUE (sku),
   CONSTRAINT chk_product_price_non_negative CHECK (price >= 0)
);
```

### 6.3. Constraints and Indexes
* `UNIQUE (sku)` prevents duplicate products under the same business identifier.
* `UNIQUE (parent_id, name)` prevents duplicate sibling category names while still allowing the same name in different branches.
* `ON DELETE CASCADE` on `category.parent_id` deletes child categories automatically when a parent category is removed.
* `ON DELETE SET NULL` on `product.category_id` preserves products while unlinking them from deleted categories, matching the functional requirements.
* `CHECK (price >= 0)` blocks invalid negative product prices at the database layer.
* A B-tree index on `product.category_id` supports category filtering and unlink operations.
* A B-tree index on `product.price` supports inclusive range queries.
* A unique B-tree index on `product.sku` supports exact SKU lookups and uniqueness enforcement.
* A B-tree index on `category.parent_id` supports recursive hierarchy traversal.
* A trigram GIN index on `product.title` is recommended for partial title search in PostgreSQL.

Recommended indexes:

```sql
CREATE INDEX idx_product_category_id ON product(category_id);
CREATE INDEX idx_product_price ON product(price);
CREATE INDEX idx_category_parent_id ON category(parent_id);

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_product_title_trgm ON product USING gin (title gin_trgm_ops);
```

## 7. API Design

The API follows REST conventions over JSON and is designed for low-latency filtering at scale. Validation is handled by Pydantic, and the generated OpenAPI document is the contract source for clients.

### 7.1. API Conventions
* Base path: `/api/v1`
* Content type: `application/json`
* No authentication layer is required in this task.
* Timestamps use ISO-8601 UTC format (example: `2026-03-12T10:20:30Z`).
* All list/search responses are wrapped in a paginated envelope.
* Validation errors return HTTP `422`; missing resources return HTTP `404`; uniqueness conflicts return HTTP `409`.

### 7.2. Category Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/categories` | Create a category |
| `GET` | `/api/v1/categories/{category_id}` | Get category by id |
| `PATCH` | `/api/v1/categories/{category_id}` | Update category name and or parent |
| `DELETE` | `/api/v1/categories/{category_id}` | Delete category subtree |
| `GET` | `/api/v1/categories` | List categories with pagination |

### 7.3. Product Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/products` | Create a product |
| `GET` | `/api/v1/products/{product_id}` | Get product by id |
| `PATCH` | `/api/v1/products/{product_id}` | Update product fields |
| `DELETE` | `/api/v1/products/{product_id}` | Delete product |
| `GET` | `/api/v1/products` | List products with pagination |

### 7.4. Search Endpoint

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/products/search` | Filter products by name or SKU, price range, and category subtree |

Query parameters:
* `q`: optional string for partial title match or exact SKU match.
* `min_price`: optional decimal, inclusive lower bound.
* `max_price`: optional decimal, inclusive upper bound.
* `category_id`: optional integer category filter; includes all descendants.
* `limit`: integer, default `20`, max `100`.
* `offset`: integer, default `0`.

### 7.5. Request and Response Schemas

Category create request:

```json
{
   "name": "Laptops",
   "parent_id": 12
}
```

Category response:

```json
{
   "id": 34,
   "name": "Laptops",
   "parent_id": 12,
   "created_at": "2026-03-12T10:20:30Z",
   "updated_at": "2026-03-12T10:20:30Z"
}
```

Product create request:

```json
{
   "title": "Ultrabook X13",
   "description": "13-inch ultrabook with 16GB RAM",
   "image_url": "https://cdn.example.com/products/x13.webp",
   "sku": "UBX13-16-512",
   "price": "1299.99",
   "category_id": 34
}
```

Product response:

```json
{
   "id": 501,
   "title": "Ultrabook X13",
   "description": "13-inch ultrabook with 16GB RAM",
   "image_url": "https://cdn.example.com/products/x13.webp",
   "sku": "UBX13-16-512",
   "price": "1299.99",
   "category_id": 34,
   "created_at": "2026-03-12T10:21:00Z",
   "updated_at": "2026-03-12T10:21:00Z"
}
```

Search response:

```json
{
   "items": [
      {
         "id": 501,
         "title": "Ultrabook X13",
         "description": "13-inch ultrabook with 16GB RAM",
         "image_url": "https://cdn.example.com/products/x13.webp",
         "sku": "UBX13-16-512",
         "price": "1299.99",
         "category_id": 34,
         "created_at": "2026-03-12T10:21:00Z",
         "updated_at": "2026-03-12T10:21:00Z"
      }
   ],
   "total": 1,
   "limit": 20,
   "offset": 0
}
```

Validation error response:

```json
{
   "detail": [
      {
         "loc": ["body", "sku"],
         "msg": "String should match pattern '^[A-Z0-9_-]{1,100}$'",
         "type": "string_pattern_mismatch"
      }
   ]
}
```

## 8. Run and Test

### 8.1. Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -e '.[dev]'
```

3. Copy environment config and adjust DB credentials if needed:

```bash
cp .env.example .env
```

### 8.2. Development Server

#### Option A: Run full stack with Docker Compose (recommended)

Build and start the full stack (API, PostgreSQL, OpenTelemetry Collector, Tempo, Prometheus, Grafana):

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up --build -d
```

Note:
* Compose now includes a one-shot `migrate-indexes` service that runs `scripts/migrate_indexes.py` after PostgreSQL becomes healthy.
* The `app` service waits for this migration to complete successfully before starting.
* On a fresh database, `migrate-indexes` now creates the base schema first, then applies indexes, so `docker compose up -d` succeeds on first boot.
* Optional: set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in your shell or `.env` before `docker compose up` to override the default local database credentials.

#### Option B: Run observability locally against a remote app and database

Use the remote compose file when the API service and PostgreSQL already run on another host and you only want the local monitoring stack.

1. Create a dedicated env file for the remote target:

```bash
cp .env.remote.example .env.remote
```

2. Set the remote host and, if needed, the exposed app port:

```bash
REMOTE_SERVER_ADDRESS=api.example.com
REMOTE_APP_SCHEME=https
REMOTE_APP_PORT=8000
REMOTE_METRICS_PATH=/metrics
```

Example for this deployed site (`https://commercesystemdemo.onrender.com/`):

```bash
REMOTE_SERVER_ADDRESS=commercesystemdemo.onrender.com
REMOTE_APP_SCHEME=https
REMOTE_APP_PORT=443
REMOTE_METRICS_PATH=/metrics
```

3. Start the remote-targeted observability stack:

```bash
docker compose -f docker-compose.remote.yml --env-file .env.remote up -d
```

This stack does not start the `app`, `migrate-indexes`, or `db` services locally. Prometheus scrapes `REMOTE_APP_SCHEME://REMOTE_SERVER_ADDRESS:REMOTE_APP_PORT${REMOTE_METRICS_PATH}`, while Grafana, Tempo, Loki, and the OpenTelemetry Collector continue to run locally.

Quick verification for the Render example:

```bash
curl -sS https://commercesystemdemo.onrender.com/metrics | grep '^commerce_' | head || true
```

Then open local dashboards:
* Grafana: `http://127.0.0.1:3000`
* Prometheus targets: `http://127.0.0.1:9090/targets`

Remote limitations:
* Metrics work immediately as long as the remote app exposes `/metrics` publicly or over a reachable private network.
* Traces appear only if the remote app is configured to send OTLP traffic to a collector endpoint reachable from that remote host.
* Logs require a separate `promtail` agent on the remote Docker host because the local stack can only scrape local container log files.

Optional server-side log shipping:

1. On the remote Docker host, create a log shipper env file:

```bash
cp .env.server-logs.example .env.server-logs
```

2. Point it to a Loki endpoint reachable from that server:

```bash
REMOTE_LOKI_PUSH_URL=https://logs.example.com/loki/api/v1/push
REMOTE_LOG_HOST=commerce-prod-01
REMOTE_LOG_JOB=commerce-remote
```

3. Start the remote log shipper on that server:

```bash
docker compose -f docker-compose.server-logs.yml --env-file .env.server-logs up -d
```

This ships Docker JSON logs from the remote host into Loki. If Loki runs on your workstation, expose it through a tunnel or reverse proxy first because the remote server must be able to reach `REMOTE_LOKI_PUSH_URL` directly.

Stop services:

```bash
docker compose down
```

Stop services and remove the PostgreSQL volume:

```bash
docker compose down -v
```

#### Option C: Run app locally against PostgreSQL

Before starting the server, ensure PostgreSQL is running. You can use Docker for the database only:

```bash
docker run -d \
   --name commerce-postgres \
   -e POSTGRES_USER=postgres \
   -e POSTGRES_PASSWORD=postgres \
   -e POSTGRES_DB=commerce_demo \
   -p 5432:5432 \
   postgres:16
```

Or configure connection to an existing PostgreSQL instance by updating `.env`:

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database
LOG_LEVEL=INFO
```

If the service is deployed on a remote host (for example Render), set these environment variables in the host's service settings (do not rely only on local `.env`):

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database
DATABASE_POOL_PRE_PING=false
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=5
LOG_LEVEL=INFO
```

Notes:
* `DATABASE_POOL_PRE_PING=false` avoids an extra connection-check round trip on each checkout.
* `DATABASE_POOL_SIZE=20` and `DATABASE_MAX_OVERFLOW=5` are the tuned defaults used for concurrent load.
* After changing remote environment variables, trigger a redeploy/restart so the running container picks up the new values.

#### Render Checklist (Remote Runtime Verification)

Use this checklist after every Render deploy to confirm that the running instance matches the expected config.

1. In Render Dashboard -> `Environment`, confirm:
   * `DATABASE_POOL_PRE_PING=false`
   * `DATABASE_POOL_SIZE=20`
   * `DATABASE_MAX_OVERFLOW=5`

2. In Render Dashboard -> `Deploys`, confirm the active deploy is the expected commit.

#### Render Postgres Notes (Latency Tuning)

If you still observe a persistent `~100ms` DB latency tier or occasional near-`200ms` mutation paths on Render, apply these checks in order:

1. Region and network:
   * Keep the web service and Render Postgres in the same region.
   * Use the private/internal database hostname when available.

2. Database plan sizing:
   * Upgrade Render Postgres plan (CPU and I/O headroom) if DB metrics show pressure.
   * Re-run the same load scenario after each plan change for apples-to-apples comparison.

3. Connection settings (service env vars):
   * `DATABASE_POOL_PRE_PING=false`
   * `DATABASE_POOL_SIZE=20`
   * `DATABASE_MAX_OVERFLOW=5`

4. Maintenance:
   * Run `VACUUM (ANALYZE)` on frequently updated tables.
   * Keep indexes from `scripts/migrate_indexes.py` applied in production.

Important limitation:
* Render managed Postgres does not expose all low-level server tuning knobs typical in self-managed Postgres.
* The `db_time` undercount mismatch seen in some search requests is typically instrumentation-path timing (outside query execute hooks), not a direct Postgres parameter issue.

Start the server locally:

```bash
uvicorn app.main:app --reload
```

Browse the interactive API:
* Swagger UI: `http://127.0.0.1:8000/docs`
* ReDoc: `http://127.0.0.1:8000/redoc`
* Health endpoint: `http://127.0.0.1:8000/health`
* Metrics endpoint: `http://127.0.0.1:8000/metrics`
* Grafana: `http://127.0.0.1:3000` (`admin` / `admin`)
* Prometheus: `http://127.0.0.1:9090`

**Troubleshooting: `ConnectionRefusedError`**

If you see `Connection refused [Errno 111]`, PostgreSQL is not accessible. Verify:
* Compose services are running: `docker compose ps`
* Docker container is running: `docker ps | grep commerce-postgres`
* Connection string in `.env` is correct
* Firewall/network allows connection to database port (5432)

### 8.3. Testing

The test suite includes **35 integration tests** covering:

**Service Layer Tests (4 tests)** — `tests/test_search.py`
* Category subtree filtering with descendants
* Inclusive price range filtering
* Title and exact SKU matching
* Pagination with proper totals

**Endpoint Integration Tests (31 tests)** — `tests/test_api.py`
* CRUD operations for categories and products
* SKU normalization and validation
* Category hierarchy and cascade delete
* Advanced search with filters and pagination
* Error handling (404, 409, 422 responses)

**Note:** Tests automatically provision a PostgreSQL container via testcontainers — no manual database setup required.

Run all tests:

```bash
pytest -q
```

Expected output: `35 passed`

Run specific test file:

```bash
pytest tests/test_search.py -q    # Service layer tests
pytest tests/test_api.py -q       # Endpoint integration tests
```

Run opt-in performance benchmarks:

```bash
pytest -m performance -q
```

The default test run excludes performance benchmarks to keep CI fast.
To run benchmarks in GitHub Actions, start the `Python application` workflow
manually and set `run_performance` to `true`.

Run with coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

**Troubleshooting: Test Container Issues**

If tests fail to start PostgreSQL container:
* Ensure Docker is running: `docker ps`
* Grant permission: `sudo usermod -aG docker $USER` (then log out/in)
* Check internet: testcontainers will download PostgreSQL image on first run (~100MB)

## 9. Observability

### 9.1. What is instrumented

The service is instrumented with OpenTelemetry traces and metrics, plus structured JSON logs.

Traces:
* Incoming FastAPI requests (automatic instrumentation)
* SQLAlchemy database operations (automatic instrumentation)

Logs:
* Request completion events with method, route, status code, duration, payload size, and client IP
* Product and category mutation events for create, update, and delete outcomes
* Search summary events including filter presence and result totals
* Error and validation failure events at warning/error levels
* Log-to-trace correlation via `trace_id` and `span_id` fields in every log record
* Configurable minimum log level via `LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)

Metrics:
* `commerce_http_request_duration_seconds` - request latency
* `commerce_http_response_payload_size_bytes` - response payload size
* `commerce_http_processing_duration_seconds` - route handler processing time
* `commerce_http_queue_wait_duration_seconds` - queue wait before handler processing
* `commerce_db_query_duration_seconds` - database query duration
* `commerce_http_requests_total` - request throughput
* `commerce_http_requests_in_flight` - in-flight requests
* `commerce_http_errors_total` - HTTP error responses with status class and type
* `commerce_http_exceptions_total` - unhandled exception count by class
* `commerce_db_pool_in_use_connections` - DB connections checked out from pool
* `commerce_search_requests_total` - search request throughput
* `commerce_search_result_count` - search result count distribution
* `commerce_search_zero_results_total` - zero-result search count
* `commerce_product_mutations_total` - product create update delete outcomes
* `commerce_category_mutations_total` - category create update delete outcomes
* `commerce_category_validation_failures_total` - category validation failures by reason

### 9.2. Telemetry flow

Observability is wired end to end through the local Docker stack:

* The FastAPI application emits structured JSON logs to stdout.
* Promtail scrapes Docker container log files and pushes logs to Loki.
* The FastAPI application exposes Prometheus metrics on `/metrics` through the OpenTelemetry Prometheus exporter.
* The application also emits OTLP traces to the OpenTelemetry Collector at `otel-collector:4317`.
* The collector forwards traces to Tempo and exposes its own runtime metrics on port `8888`.
* Prometheus scrapes the application metrics endpoint and the collector metrics endpoint every 5 seconds.
* Grafana reads metrics from Prometheus, traces from Tempo, and logs from Loki through provisioned datasources.

Telemetry path summary:

```text
FastAPI app
   |- structured JSON logs -> stdout -> Promtail -> Loki -> Grafana
   |- /metrics -> Prometheus
   '- OTLP traces -> OpenTelemetry Collector -> Tempo -> Grafana
```

### 9.3. Local stack

`docker-compose.yml` runs an observability stack:
* `otel-collector` receives OTLP traces from the API and forwards to Tempo
* `tempo` stores traces
* `loki` stores logs
* `promtail` ships container logs to Loki
* `prometheus` scrapes `app:8000/metrics`
* `grafana` is pre-provisioned with Prometheus, Tempo, and Loki datasources

Useful endpoints:
* API: `http://127.0.0.1:8000`
* Metrics: `http://127.0.0.1:8000/metrics`
* Grafana: `http://127.0.0.1:3000`
* Prometheus: `http://127.0.0.1:9090`
* Tempo API: `http://127.0.0.1:3200`
* Loki API: `http://127.0.0.1:3100`

For a remote-hosted API and database, use `docker-compose.remote.yml` instead. It keeps Grafana, Prometheus, Tempo, Loki, and the collector local, but scrapes the application metrics endpoint from `REMOTE_SERVER_ADDRESS:REMOTE_APP_PORT` configured through `.env.remote`.

To ingest logs from that remote host as well, run `docker-compose.server-logs.yml` on the remote Docker server with `REMOTE_LOKI_PUSH_URL` set to a Loki endpoint the server can reach.

Relevant configuration files:
* `app/observability/logging.py` configures structured JSON logging and trace/span correlation fields
* `app/observability/setup.py` initializes tracing, metrics, middleware, and the `/metrics` endpoint
* `app/observability/middleware.py` records request lifecycle metrics and error classifications
* `app/observability/db.py` instruments SQLAlchemy and DB pool usage
* `observability/otel-collector-config.yaml` configures OTLP ingestion and exporter pipeline
* `observability/loki-config.yaml` configures Loki storage and ingestion
* `observability/promtail-config.yaml` configures container log scraping and shipping to Loki
* `observability/promtail.remote.yml.tmpl` configures the remote-server Promtail agent for Loki shipping
* `observability/prometheus.yml` configures scrape jobs and alert rule loading
* `observability/grafana/provisioning` provisions Grafana datasources and dashboards

### 9.4. Grafana dashboards

A ready-to-use dashboard set is provisioned from:
* `observability/grafana/dashboards/commerce-observability.json` (P1 reliability)
* `observability/grafana/dashboards/commerce-observability-p2.json` (P2 domain)
* `observability/grafana/dashboards/commerce-observability-p3.json` (P3 diagnostics)

Priority split:
* **P1 Reliability**: request rate, in-flight requests, error rate, exception rate, p95 request latency, p95 DB query duration, DB pool pressure, recent traces
* **P2 Domain**: search traffic and quality, mutation outcomes for products and categories, category validation failures
* **P3 Diagnostics**: latency decomposition, payload sizes, DB query duration by operation, HTTP error type breakdown, prebuilt Loki log panels for `commerce-app` warnings/errors, and request latency buckets derived from structured logs

### 9.5. Alerting rules (P1)

Prometheus alert rules are defined in:
* `observability/prometheus-alerts/commerce-alerts.yml`

Prometheus is configured to load alert rule files from:
* `observability/prometheus.yml` via `rule_files: /etc/prometheus/alerts/*.yml`

Compose mounts the alert rules directory into the Prometheus container:
* `docker-compose.yml` maps `./observability/prometheus-alerts` to `/etc/prometheus/alerts`

Configured P1 alerts:
* `CommerceHigh5xxRate` - 5xx ratio above 5% for 5 minutes
* `CommerceHighP95RequestLatency` - global p95 latency above 350 ms for 10 minutes
* `CommerceEndpointP95Over200ms` - per-endpoint p95 latency above 200 ms for 10 minutes (non-functional requirement)
* `CommerceSustainedHighInFlightRequests` - in-flight requests above 50 for 10 minutes
* `CommerceDbPoolPressure` - DB pool in-use connections above 12 for 10 minutes

### 9.6. How to exercise the dashboards

The dashboards stay sparse until the service receives traffic. For a quick local smoke test:

1. Start the full stack:

```bash
docker compose up --build -d
```

2. Generate load against the API:

```bash
.venv/bin/python scripts/load_test.py --duration 60 --workers 8
```

If the catalog is already seeded, skip the initial setup phase:

```bash
.venv/bin/python scripts/load_test.py --skip-seed --duration 60 --workers 8
```

3. Open the tools:
* Grafana: `http://127.0.0.1:3000`
* Prometheus: `http://127.0.0.1:9090`
* Metrics endpoint: `http://127.0.0.1:8000/metrics`
* Loki ready check: `http://127.0.0.1:3100/ready`

4. Verify that custom application metrics are present:

```bash
curl -s http://127.0.0.1:8000/metrics | grep '^commerce_' || true
```

5. Verify that logs are queryable in Loki:

```bash
curl -G -s "http://127.0.0.1:3100/loki/api/v1/query_range" \
   --data-urlencode 'query={container="commerce-app"}' \
   --data-urlencode 'limit=20'
```

Notes:
* After instrumentation changes, rebuild the application container so the running service exposes the new metrics.
* Some counters appear only after the first matching event is observed. Until then, Prometheus and Grafana can show no data for that series.
* The load test intentionally produces successful traffic and controlled 4xx scenarios so the P1, P2, and P3 dashboards all receive data.

## 10. Implemented Improvements

This section summarizes the concrete improvements implemented to reduce latency and improve observability for concurrent traffic.

### 10.1. Application and Runtime

* Enabled multi-worker app execution in [Dockerfile](Dockerfile) using `WEB_CONCURRENCY=2` so requests are not serialized through a single worker.
* Applied `route_class=ObservabilityRoute` consistently to API routers in `app/api` so queue-wait and handler timing is captured for all endpoints.
* Added request lifecycle diagnostics in [app/observability/middleware.py](app/observability/middleware.py):
   * `duration_ms`, `queue_wait_ms`, `handler_ms`
   * `in_flight_requests`, `response_size_bytes`, and request context fields
* Added structured request slow-path logging (`request_slow`) for rapid triage when requests exceed the target threshold.

### 10.2. Database and Query Path

* Wired SQLAlchemy async pool settings in [app/db/session.py](app/db/session.py) and exposed tuning in [app/core/config.py](app/core/config.py):
   * `database_pool_size = 20`
   * `database_max_overflow = 5`
   * `database_pool_timeout = 5`
   * `database_pool_pre_ping = False`
* Refactored search execution in [app/services/product_service.py](app/services/product_service.py) to release the data-query connection before optional `COUNT(*)` execution.
* Added `COUNT(*)` skip optimization on first-page short results (`offset == 0 and len(records) < limit`) to avoid unnecessary aggregate scans.
* Added migration helper [scripts/migrate_indexes.py](scripts/migrate_indexes.py) to backfill performance indexes for existing databases, including `pg_trgm` + GIN trigram index for `ILIKE` search on `product.title`.
* Added DB observability in [app/observability/db.py](app/observability/db.py): query duration metrics, slow-query logs, and pool in-use tracking.
* Added application-level DB wall-time instrumentation in [app/observability/db_timing.py](app/observability/db_timing.py) and applied it across search, products, and categories paths:
   * connection acquire timing (`db_acquire_ms`)
   * execute and fetch wall timing (`db_execute_fetch_ms`)
   * wrapper helpers for `get`, scalar, and list query patterns

### 10.3. Logging and Metrics Path

* Migrated logging to asynchronous queue-based handling in [app/observability/logging.py](app/observability/logging.py):
   * `QueueHandler` on request path
   * `QueueListener` background thread for I/O
   * startup/shutdown wiring in [app/main.py](app/main.py)
* Moved HTTP metric recording off the event-loop critical path in [app/observability/middleware.py](app/observability/middleware.py) by dispatching histogram/counter updates to the thread pool via `run_in_executor`.
* Preserved synchronous in-flight counter updates to keep active-request gauges accurate while offloading heavier metric updates.
* Extended request logs with DB timing decomposition fields in [app/observability/middleware.py](app/observability/middleware.py):
   * `db_acquire_ms`
   * `db_execute_fetch_ms`
   * `db_time_gap_ms` (`db_execute_fetch_ms - db_time_ms`, clamped at zero)
* This decomposition makes DB-time undercount mismatches visible in production logs and distinguishes true DB latency from instrumentation-scope gaps.

### 10.4. Validation and Benchmarks

* Migration status: [scripts/migrate_indexes.py](scripts/migrate_indexes.py) executed successfully against local `commerce_demo` (all index statements applied).
* Test suite status after migration: `35 passed` (`python -m pytest tests/ -q`).
* Local mixed-load validation with [scripts/load_test.py](scripts/load_test.py):
   * `workers=8`, `duration=30s`: ~103 RPS, no functional errors.
   * `workers=16`, `duration=60s`: ~69 RPS sustained, all requests completed successfully.
* Direct client-side latency sample after DB migration (`1000` requests, concurrency `16`) showed:
   * average ~102 ms
   * p50 ~89 ms
   * p95 ~196 ms
   * p99 ~373 ms
   * max ~387 ms
* Post-deployment remote log validation confirms DB timing decomposition is active and useful for diagnosis:
   * most requests now show a small `db_time_gap_ms` (typically ~0-1 ms)
   * occasional endpoint-specific outliers remain identifiable for targeted follow-up

These results indicate the service remains stable under heavier concurrent local traffic, with p95 staying near the 200 ms target and tail-latency behavior visible under stress for continued tuning.

## 11. Investigation Conclusions on 200ms Target

The findings below are based on observed load-test runs, production-like remote logs, and the added DB timing decomposition (`db_acquire_ms`, `db_execute_fetch_ms`, `db_time_gap_ms`).

The 200ms target remains the default expectation, but the following scenarios can legitimately exceed it.

* Search requests that require both data retrieval and `COUNT(*)` (for example price-range searches with non-trivial result sets) may exceed 200ms because they execute two DB-heavy phases.
* Mutation endpoints (`POST`, `PATCH`, `DELETE`) can exceed 200ms under concurrent load because they include validation reads plus write/commit phases in one request.
* Database slow-tier events (observed as ~90-100ms query durations) can push otherwise normal requests above 200ms, especially when multiple queries occur in the same request.
* Burst concurrency can temporarily increase queue wait and in-flight pressure, which raises end-to-end latency even when individual SQL statements are healthy.
* Remote-host conditions (cross-region app/DB placement, undersized managed DB plan, or noisy-neighbor CPU/IO effects) can increase p95/p99 latency.
* Cold-start and warmup windows after deploy/restart may produce transient latency spikes before caches and pools stabilize.

Mitigation is tracked in the observability dashboards and logs (`request_slow`, DB timing decomposition fields, pool usage), and tuning guidance is documented in the remote service configuration section.
