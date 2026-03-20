# AGENTS.md

Guide for AI coding agents working on the Commerce System Demo project.

## Project Overview

Commerce System Demo is a FastAPI-based commerce service that provides RESTful APIs for managing products, categories, and implementing search functionality. The project includes built-in observability with OpenTelemetry metrics, logging, and distributed tracing.

**Current Version**: 0.1.2 (following [Semantic Versioning](https://semver.org/))

## Setup Commands

### Installation and Environment Setup

- **Install dependencies**: `pip install -e ".[dev]"` (after activating Python 3.11+ venv)
- **Python version**: Requires Python 3.11+
- **Virtual environment**: Use `.venv` folder in project root
- **Activate venv**: `source .venv/bin/activate`

### Database Setup

- **PostgreSQL required**: The project uses PostgreSQL with asyncpg driver
- **Docker Compose**: Use `docker-compose.yml` to start all services (PostgreSQL, app, monitoring stack)
- **Start services**: `docker-compose up -d`
- **Run migrations**: `docker-compose run migrate-indexes` (handles database schema and indexes)
- **Database URL**: `postgresql+asyncpg://postgres:postgres@localhost:5432/commerce_demo`

### Development Server

- **Start dev server**: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **API docs**: Available at `http://localhost:8000/docs` (Swagger UI)
- **Alternative docs**: Available at `http://localhost:8000/redoc` (ReDoc)
- **Health check**: `curl http://localhost:8000/health`

## Code Organization

### Project Structure

```
app/
├── main.py                 # FastAPI application setup
├── api/                    # API endpoint implementations
│   ├── categories.py       # Category CRUD endpoints
│   ├── products.py         # Product CRUD endpoints
│   └── search.py           # Product search endpoint
├── models/                 # SQLAlchemy ORM models
│   ├── category.py         # Category model with hierarchy support
│   └── product.py          # Product model
├── schemas/                # Pydantic request/response schemas
│   ├── category.py         # Category validation schemas
│   ├── product.py          # Product validation schemas
│   └── common.py           # Shared response models
├── services/               # Business logic layer
│   ├── category_service.py # Category operations and tree queries
│   └── product_service.py  # Product search orchestration
├── db/                     # Database configuration
│   ├── base.py             # SQLAlchemy declarative base
│   ├── session.py          # Async session factory
│ └── core/                 # Configuration
│   └── config.py           # Environment and app settings
├── observability/          # OpenTelemetry instrumentation
│   ├── setup.py            # Telemetry initialization
│   ├── metrics.py          # Metrics definitions
│   ├── middleware.py       # Custom middleware
│   └── logging.py          # Logging configuration
└── templates/              # HTML templates
    └── index.html          # Project overview page
```

### Key Conventions

- **API prefix**: `/api/v1` (configurable via `API_PREFIX` env var)
- **Async/await**: All database operations are async using SQLAlchemy 2.0+ async API
- **Validation**: Pydantic v2 validators with `mode="before"` for data transformation
- **Error handling**: FastAPI HTTPException with appropriate status codes (400, 404, 409, 422)
- **Naming**: Snake_case for Python code, kebab-case for API paths and Docker services

## Testing

### Run Tests

- **All tests**: `pytest` or `pytest tests/`
- **Specific test file**: `pytest tests/test_api.py` or `pytest tests/test_search.py`
- **Specific test**: `pytest tests/test_api.py::test_create_category -v`
- **With coverage**: `pytest --cov=app --cov-report=html`
- **Watch mode**: `pytest-watch` (requires pytest-watch package)

### Test Organization

- **tests/conftest.py**: Shared fixtures (db_session, client setup)
- **tests/test_api.py**: Integration tests for CRUD operations and search endpoints
- **tests/test_search.py**: Service-level search functionality tests

### Database for Tests

- Tests use `testcontainers` to spin up real PostgreSQL instances
- Each test session gets a fresh database to avoid state leakage
- Tests run in async mode (`asyncio_mode = "auto"`)

## Building and Deployment

### Docker

- **Build image**: `docker build -t commerce-system-demo:0.1.2 .`
- **View Dockerfile**: Includes Python dependencies, migration scripts, and app code
- **Build context**: Includes `scripts/`, `app/`, and `observability/` directories

### Environment Variables

- `DATABASE_URL`: PostgreSQL connection string (required)
- `API_PREFIX`: API path prefix (default: `/api/v1`)
- `AUTO_CREATE_SCHEMA`: Auto-create tables on startup (default: `true`)
- `TELEMETRY_ENABLED`: Enable OpenTelemetry export (default: `false` for dev)
- `OTEL_SERVICE_NAME`: Service name for observability (default: `commerce-system-demo`)
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OTLP collector endpoint for data export

## Validation Rules and Constraints

### Product Validation

- **Title**: 1-255 characters, cannot be empty or whitespace-only (space-only names rejected at schema level)
- **Description**: 1-10000 characters, cannot be empty or whitespace-only
- **SKU**: 1-100 characters, uppercase letters/numbers/hyphens/underscores, unique constraint at DB level (normalized to uppercase)
- **Price**: Decimal ≥ 0, includes cents precision
- **Category ID**: Optional foreign key to category

### Category Validation

- **Name**: 1-255 characters, cannot be empty or whitespace-only (space-only names rejected at schema level)
- **Parent ID**: Optional self-referential foreign key
- **Hierarchy depth limit**: Categories cannot exceed 5 levels deep
- **Naming uniqueness**: Category names must be unique within same parent (siblings must have different names)

### Search Validation

- **Query**: Optional, 1-255 characters when provided, space-only queries filtered out at endpoint level
- **Price range**: `min_price <= max_price` (validation error if violated)
- **Category**: Optional integer ID
- **Pagination**: limit 1-100 (default 20), offset ≥ 0

## Important Patterns and Best Practices

### Error Handling

- Return 400 (Bad Request) for client validation errors (Pydantic ValidationError)
- Return 404 (Not Found) for missing resources (product_id, category_id)
- Return 409 (Conflict) for duplicate SKU or duplicate sibling category name
- Return 422 (Unprocessable Entity) for logic violations (e.g., circular category references, depth exceeded, invalid price range)

### Whitespace Handling

- **Stripping**: Product titles/descriptions and category names are automatically stripped of leading/trailing whitespace via Pydantic validators
- **Rejection**: Space-only strings are rejected with `ValueError` during schema validation before any business logic
- **Example**: A product with title "   " will be rejected with 422 error; "  Test  " becomes "Test"

### Database Queries

- Use `timed_execute_*` functions from `app.observability.db_timing` to instrument query timing
- Category hierarchy queries use CTE (Common Table Expression) for efficient tree traversal
- Search queries use `ilike` for case-insensitive title matching and exact match for normalized SKU

### Observability

- **Metrics**: Custom OpenTelemetry meters track mutations (create/update/delete) and search requests
- **Logging**: Structured logs with context data (product_id, category_id, operation, result)
- **Distributed Tracing**: FastAPI instrumentation tracks request flow through the entire stack

## Testing Strategies for Agents

When making changes:

1. **Add tests for new features** before or alongside implementation
2. **Run full test suite** after changes: `pytest -v`
3. **Check lint/formatting**: `black --check app/` (if configured) or `ruff check app/`
4. **Type checking**: `mypy app/` (if configured)
5. **Test whitespace validation**: Verify space-only inputs are rejected at schema layer
6. **Test edge cases**: Empty strings after strip, very long strings, special characters in SKU

## Versioning

This project follows [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR**: Incompatible API changes
- **MINOR**: Backward-compatible new features
- **PATCH**: Backward-compatible bug fixes

Current version is **0.1.2** (initial development). Version is defined in:
- `pyproject.toml` (project metadata)
- `app/main.py` (FastAPI version)
- `app/observability/metrics.py` (meter version)
- `app/observability/setup.py` (service version)

All version references should be kept in sync when updating.

## Automatic Version Management

When updating the project version, follow this automated workflow to ensure consistency and create proper git artifacts:

### Required Version Files (Keep in Sync)

These **4 files MUST** have identical version strings when updated:

1. `pyproject.toml` - Line: `version = "X.Y.Z"`
2. `app/main.py` - Line: `version="X.Y.Z"` (in FastAPI instantiation)
3. `app/observability/metrics.py` - Line: `version="X.Y.Z"` (in get_meter call)
4. `app/observability/setup.py` - Line: `"service.version": "X.Y.Z"` (in resource attributes)

### Automated Version Update Process

**Rule**: When any feature, fix, or release requires a version change, agents MUST:

1. **Update all 4 version files atomically** - Use regex/find-replace to update `X.Y.Z` across all files
   ```bash
   # Verify current version across all files
   grep -n "0\.1\.1" pyproject.toml app/main.py app/observability/metrics.py app/observability/setup.py
   ```

2. **Update CHANGELOG.md**
   - Move `## [Unreleased]` section content to new version section: `## [X.Y.Z] - YYYY-MM-DD`
   - Create fresh `## [Unreleased]` section at top
   - Update version references in guidelines

3. **Update AGENTS.md**
   - Change `**Current Version**: X.Y.Z` in Project Overview
   - Update Docker build command examples: `docker build -t commerce-system-demo:X.Y.Z .`
   - Update version references in Versioning section

4. **Create git artifacts**
   ```bash
   # Stage all version updates
   git add pyproject.toml app/main.py app/observability/metrics.py app/observability/setup.py CHANGELOG.md AGENTS.md
   
   # Commit with standardized message
   git commit -m "chore: release version X.Y.Z"
   
   # Create annotated git tag
   git tag -a vX.Y.Z -m "Release version X.Y.Z"
   
   # (Optional) Push to remote
   git push origin --tags
   ```

5. **Validate consistency**
   ```bash
   # Verify all 4 version files match
   grep "X\.Y\.Z" pyproject.toml app/main.py app/observability/metrics.py app/observability/setup.py
   
   # Verify CHANGELOG has new version section
   grep "## \[X\.Y\.Z\]" CHANGELOG.md
   
   # Verify git tag exists
   git tag -l vX.Y.Z
   ```

### Version Update Checklist for Agents

When asked to update the version, verify:

- [ ] All 4 version files updated to identical semantic version (X.Y.Z)
- [ ] CHANGELOG.md has `## [X.Y.Z] - YYYY-MM-DD` section
- [ ] CHANGELOG.md has fresh `## [Unreleased]` section
- [ ] AGENTS.md current version reference updated
- [ ] Docker command examples updated with new version
- [ ] All tests pass: `pytest -v`
- [ ] Consistency check passes (all files have same version)
- [ ] Git commit created: `git commit -m "chore: release version X.Y.Z"`
- [ ] Annotated git tag created: `git tag -a vX.Y.Z -m "Release version X.Y.Z"`
- [ ] git tag verified: `git tag -l vX.Y.Z`

### Example: Releasing 0.2.0

**Step 1: Update Version Files (all files get 0.2.0)**
```bash
# Before: contain 0.1.1
# After: contain 0.2.0
pyproject.toml: version = "0.2.0"
app/main.py: version="0.2.0"
app/observability/metrics.py: version="0.2.0"
app/observability/setup.py: "service.version": "0.2.0"
```

**Step 2: Update CHANGELOG.md**
```markdown
## [0.2.0] - 2024-03-20

### Added
- [Features from unreleased section]

### Changed
- [Changes from unreleased section]

### Fixed
- [Fixes from unreleased section]

## [Unreleased]

### Planned
- [Future features to be filled in later]
```

**Step 3: Update AGENTS.md**
```markdown
**Current Version**: 0.2.0 (following [Semantic Versioning](https://semver.org/))
- **Build image**: `docker build -t commerce-system-demo:0.2.0 .`
```

**Step 4: Commit and Tag**
```bash
git add pyproject.toml app/main.py app/observability/metrics.py app/observability/setup.py CHANGELOG.md AGENTS.md
git commit -m "chore: release version 0.2.0"
git tag -a v0.2.0 -m "Release version 0.2.0"
```

**Step 5: Verify**
```bash
# Should show all files with 0.2.0
grep "0\.2\.0" pyproject.toml app/main.py app/observability/metrics.py app/observability/setup.py

# Should show tag exists
git tag -l v0.2.0

# Should show 0.2.0 release section
grep "## \[0\.2\.0\]" CHANGELOG.md
```

### Critical Rules for Agents

⚠️ **MUST DO:**
- Always update ALL 4 version files atomically together (never partial updates)
- Always create CHANGELOG entry before git tag
- Always use annotated tags (`git tag -a`) with message, not lightweight tags
- Always use `vX.Y.Z` format for git tags (with leading 'v')
- Always verify consistency before completing task

⚠️ **MUST NOT:**
- Update only 1-3 version files and skip the rest
- Forget to update CHANGELOG.md before tagging
- Use lightweight tags or tags without messages
- Tag without committing version changes first
- Leave version in sync documentation out of date

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history and notable changes.

## Common Issues and Solutions

### PostgreSQL Connection Errors

- Ensure PostgreSQL is running: `docker-compose ps`
- Check DATABASE_URL environment variable is set correctly
- Verify PostgreSQL container is healthy: `docker-compose logs db`

### Migration Script Failures

- Ensure `scripts/` directory is included in Docker build context
- Check that migrate-indexes service runs before app service (docker-compose dependency)
- Review migration script output: `docker-compose logs migrate-indexes`

### Tests Failing Locally

- Ensure Docker is running (testcontainers needs Docker daemon)
- Try isolating a single test: `pytest tests/test_api.py::test_create_product -v`
- Check Python version: Must be 3.11+

### Telemetry Issues

- Verify OTEL_EXPORTER_OTLP_ENDPOINT is reachable if telemetry is enabled
- Check OpenTelemetry SDK isn't throwing exceptions in logs
- Disable telemetry for local development if observability stack isn't available

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [README.md](README.md) - Human-focused project documentation
