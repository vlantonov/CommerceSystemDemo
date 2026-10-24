FROM postgres:16-alpine

ENV POSTGRES_USER=postgres \
    POSTGRES_PASSWORD=postgres \
    POSTGRES_DB=commerce_demo

HEALTHCHECK --interval=5s --timeout=5s --retries=10 \
  CMD pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" || exit 1
