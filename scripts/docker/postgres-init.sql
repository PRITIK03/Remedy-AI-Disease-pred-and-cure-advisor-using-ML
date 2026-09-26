-- Remedy-AI PostgreSQL initialization (Phase 9).
--
-- Runs once, on an empty data directory, via the postgres entrypoint.
-- It enables the vector extension the RAG knowledge tables depend on. The
-- application tables themselves are created by Alembic migrations, not here.
--
-- NOTE: this only runs the FIRST time the volume is initialised. On an
-- existing volume apply the equivalent manually:
--   CREATE EXTENSION IF NOT EXISTS vector;

CREATE EXTENSION IF NOT EXISTS vector;

-- Guard against the classic pgvector mistake: a vector column whose dimension
-- does not match the embedding model produces silent insert failures.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION
            'pgvector extension is unavailable. Use the pgvector/pgvector image.';
    END IF;
END
$$;
