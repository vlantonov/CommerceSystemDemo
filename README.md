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
   * [4.8. Databse to store products, categories and images](#48-databse-to-store-products-categories-and-images)
   * [4.9. Unit test for real database or for mock database](#49-unit-test-for-real-database-or-for-mock-database)
* [5. High-Level Design](#5-high-level-design)
   * [5.1. Architecture Notes](#51-architecture-notes)
* [6. Database Design](#6-database-design)
   * [6.1. Entity Relationship Diagram](#61-entity-relationship-diagram)
   * [6.2. Schema Notes](#62-schema-notes)
   * [6.3. Constraints and Indexes](#63-constraints-and-indexes)

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

### 4.8. Databse to store products, categories and images
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
