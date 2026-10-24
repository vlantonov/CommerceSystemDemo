# Release Notes

## v0.2.0

### Highlights

- Added product and category management APIs with validation and hierarchy rules
- Added search endpoints with price filtering, category subtree support, and safe wildcard handling
- Added observability instrumentation for metrics, tracing, logs, and dashboards
- Added rate limiting, database instrumentation, and health checks
- Added Docker and CI automation for local and GitHub Actions workflows

### Improvements

- Improved category validation using recursive CTE queries for depth and cycle detection
- Reduced redundant database work in product search and category validation paths
- Added integration and benchmark coverage for core product and category behavior
- Added structured documentation for setup, observability, and testing

### Security

- Added request throttling to protect the search endpoint
- Escaped user input used in LIKE-based search filters to prevent wildcard injection

## Next release

Planned improvements include:

- Full-text indexing for search workloads
- Bulk import/export support
- Additional product image handling
- Expanded admin and operational tooling
