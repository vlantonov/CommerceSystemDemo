# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Enhanced search with full-text indexing support
- Bulk import/export endpoints for products and categories
- Rate limiting and request throttling
- Advanced filtering options for product search
- Product images storage optimization

## [0.1.4] - 2026-03-22

### Changed

- Replaced O(n) per-level ancestor walks in `category_depth` and `validate_no_cycles` with single recursive CTE queries
- Category depth validation now executes one SQL statement instead of up to 100 sequential fetches
- Cycle detection now uses a single `EXISTS` query over a recursive ancestor CTE

### Added

- Integration benchmark test for category validation on PostgreSQL testcontainers (`test_category_service_benchmark.py`)
- Opt-in `performance` pytest marker to separate benchmarks from the default fast test suite
- Dedicated `performance-tests` CI job triggered via `workflow_dispatch` with `run_performance=true`
- Documentation in README and AGENTS.md for running performance benchmarks locally and in CI

## [0.1.3] - 2026-03-20

### Added

- Health check endpoint now verifies database connectivity via `SELECT 1` probe
- Retry fallback policy for health check database connection with configurable retries and timeout
- New settings `health_check_db_retries` (default 3) and `health_check_db_timeout` (default 2.0s)
- OpenTelemetry metrics for health checks: `commerce_health_check_total` counter and `commerce_health_check_duration_seconds` histogram
- Integration tests for health check success, DB failure with retries, recovery on retry, and metrics recording

## [0.1.2] - 2026-03-20

### Added

- Unit tests for API handler branches covering success paths and edge cases (test_api_unit.py)
- Service-level tests for category depth limit and cycle detection logic (test_category_service.py)
- Unit tests for observability middleware and metrics emission paths (test_observability.py)
- Concurrent access integration tests for race conditions on SKU and category constraints (test_concurrency.py)

## [0.1.1] - 2026-03-19

### Fixed

- Reject whitespace-only product titles, product descriptions, and category names during schema validation
- Normalize valid text inputs by trimming leading and trailing whitespace before persistence
- Apply the same validation behavior to both create and update operations
- Prevent non-deterministic list and search ordering by sorting category, product, and search results by id

### Changed

- Moved category whitespace normalization from API handlers into Pydantic schemas for a single validation path
- Expanded API regression coverage for whitespace-only inputs and trimmed valid payloads

## [0.1.0] - 2024-03-19

### Added

- Initial release of Commerce System Demo
- Product CRUD operations (Create, Read, Update, Delete)
  - Product title, description, SKU, price, and category assignment
  - SKU normalization (automatic uppercase conversion)
  - Unique SKU constraint at database level
- Category management with hierarchical support
  - Category hierarchy with parent-child relationships
  - Depth limit validation (max 5 levels)
  - Automatic cascading delete of child categories
- Product search functionality
  - Full-text search by product title
  - Exact SKU search with normalization
  - Price range filtering (min/max)
  - Category subtree filtering
  - Pagination support (limit, offset)
- Basic input validation and whitespace normalization foundations
- RESTful API with standardized error handling
  - HTTP status codes: 201 (Created), 400 (Bad Request), 404 (Not Found), 409 (Conflict), 422 (Unprocessable Entity)
  - Structured error responses with detailed messages
- Comprehensive test suite
  - 39 integration tests covering CRUD operations
  - Space-only name validation tests
  - Search functionality tests
  - Database constraint validation tests
  - Test fixtures with real PostgreSQL via testcontainers
- Observability and monitoring
  - OpenTelemetry instrumentation for metrics and tracing
  - Custom metrics for mutation operations and search requests
  - Structured logging with contextual data
  - Prometheus metrics export
  - Grafana dashboards for monitoring
  - Distributed tracing support
  - Loki log aggregation
  - Alerting rules for critical issues
- Docker support
  - Dockerfile for containerized deployment
  - Docker Compose orchestration (app, PostgreSQL, monitoring stack)
  - Migration service for database schema setup
- FastAPI with async/await
  - Async SQLAlchemy 2.0+ integration
  - Asynchronous database queries
  - Async context managers for proper resource cleanup
- Project documentation
  - Comprehensive README with architecture and design details
  - API conventions and endpoint specifications
  - Non-functional requirements documentation

### Security Considerations

- Database: Uses parameterized queries via SQLAlchemy ORM (SQL injection protection)
- Input validation: All user inputs validated via Pydantic before processing
- CORS: Not currently enabled (configure in fastapi.middleware.cors if needed)
- Rate limiting: Not yet implemented (recommended for production)

### Version Information

**Semantic Version**: 0.1.0
- Major: 0 (initial development phase)
- Minor: 1 (includes functional features)
- Patch: 0 (no bug fixes in this version, only features and bug fix for space-only names)

This is an early development release. The public API may change in subsequent releases.

---

## Version History Reference

| Version | Release Date | Status | Notes |
|---------|-------------|--------|-------|
| [0.1.1](#011---2026-03-19) | 2026-03-19 | Current | Patch release for whitespace validation and deterministic ordering |
| [0.1.0](#010---2024-03-19) | 2024-03-19 | Previous | Initial release with core functionality |
| [Unreleased](#unreleased) | - | In Progress | Upcoming features and improvements |

---

## Guidelines for Maintainers

### When to Update Versions

- **PATCH version** (0.1.X): Bug fixes, performance improvements, non-breaking changes
  - Example: Fixing another bug after this release (0.1.1 → 0.1.2)
- **MINOR version** (0.X.0): New features, backward-compatible additions
  - Example: Adding new search filters (0.1.1 → 0.2.0)
- **MAJOR version** (X.0.0): Breaking API changes, major restructuring
  - Example: Changing endpoint paths (0.1.1 → 1.0.0)

### Updating Version References

When releasing a new version, update all occurrences:

1. `pyproject.toml`: `version = "X.Y.Z"`
2. `app/main.py`: `version="X.Y.Z"`
3. `app/observability/metrics.py`: `version="X.Y.Z"`
4. `app/observability/setup.py`: `"service.version": "X.Y.Z"`
5. `Dockerfile`: Update image tags in build commands
6. `CHANGELOG.md`: Add new version section with changes

### Changelog Format

For each release:

1. Create section with `## [X.Y.Z] - YYYY-MM-DD`
2. Use subsections: Added, Changed, Fixed, Deprecated, Removed, Security
3. List items as bullet points
4. Include reference links at bottom for easy diff generation
5. Keep unreleased section for tracking in-progress work

### Release Checklist

- [ ] All tests pass: `pytest -v`
- [ ] Code formatted and linted
- [ ] Version numbers updated in all files (see list above)
- [ ] CHANGELOG.md updated with new version section
- [ ] Git tag created: `git tag v0.1.1`
- [ ] Release notes added to GitHub

---

## How to Contribute

See [README.md](README.md) for development setup and contribution guidelines.

For detailed agent-specific guidance, see [AGENTS.md](AGENTS.md).
