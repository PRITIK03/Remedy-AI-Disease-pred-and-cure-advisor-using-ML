"""One-time pgvector enablement for a self-hosted PostgreSQL server.

The Phase 4 migration (a4f2c9d17e55) runs `CREATE EXTENSION IF NOT EXISTS
vector`, which requires the pgvector BINARY to be installed on the SERVER
first. On Windows there is no official precompiled binary; the supported
path is compiling from source with Visual Studio Build Tools.

Steps (PowerShell; steps 1-2 need an admin shell):

  1. Install build tools (once, ~2-4 GB):
       winget install Microsoft.VisualStudio.2022.BuildTools `
         --override "--wait --passive --add `
         Microsoft.VisualStudio.Workload.VCTools `
         --includeRecommended"

  2. Close and reopen the terminal so vsdevcmd.bat is resolvable, then get
     pgvector sources:
       git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
       cd pgvector

  3. Point the build at your PostgreSQL installation (this machine:
     E:/SQl/postre) and build/install from the VS 2022 dev prompt:
       set "PGROOT=E:/SQl/postre"
       nmake /F Makefile.win
       nmake /F Makefile.win install

  4. Copy nothing by hand if step 3 succeeded; otherwise the produced files
     are: vector.dll (bin), vector--*.sql + vector.control (share/extension),
     vector*.dll (lib).

  5. Restart the service (admin):
       net stop postgresql-x64-18 && net start postgresql-x64-18

  6. Enable the extension and apply the migration:
       .venv/Scripts/python scripts/enable_pgvector.py
       .venv/Scripts/python -m alembic upgrade head

Alternative: install Docker Desktop and run the provided docker-compose
stack with a pgvector-enabled postgres image (no compile step).

This script verifies the extension once installed and creates it in the
configured database. Safe to run repeatedly (idempotent).
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify + enable the pgvector extension (idempotent)."
    )
    parser.parse_args()

    from backend.app.core.config import get_settings

    settings = get_settings()
    # Parse the SQLAlchemy URL into psycopg parameters.
    import psycopg

    url = settings.database_url
    assert url.startswith("postgresql+psycopg://"), url
    dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)

    try:
        with psycopg.connect(dsn) as conn:
            row = conn.execute(
                "SELECT name, default_version, installed_version "
                "FROM pg_available_extensions WHERE name = 'vector'"
            ).fetchone()
            if row is None:
                print(
                    "pgvector is NOT installed on this server.\n"
                    "Install the server binary first — see the instructions at "
                    "the top of scripts/enable_pgvector.py."
                )
                return 1
            name, default_version, installed_version = row
            if installed_version is None:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
                print(f"Created extension 'vector' version {default_version}.")
            else:
                print(f"Extension 'vector' already installed ({installed_version}).")

            # Post-condition: vector type is usable.
            conn.execute("SELECT '[1,2,3]'::vector")
            print("OK: pgvector is ready for the RAG migration.")
            return 0
    except psycopg.OperationalError as exc:
        print(f"Cannot connect to the database ({settings.database_url}): {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
