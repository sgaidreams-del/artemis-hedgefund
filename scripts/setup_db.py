#!/usr/bin/env python3
"""Initialize the Artemis database. Idempotent — safe to re-run.

    python scripts/setup_db.py                 # apply scripts/init.sql
    python scripts/setup_db.py --create-role   # first create the role + database on a
                                               # local Postgres (Homebrew etc.), then apply

--create-role connects as a Postgres superuser (default: your OS username, which is
what Homebrew's postgresql sets up) and creates/updates the POSTGRES_USER role with
the password from .env. The password is composed in Python — never passed on a
command line where other processes could see it.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from src.core.config import env  # noqa: E402
from src.core.db import conn  # noqa: E402


def create_role_and_db(superuser: str) -> None:
    host = env("POSTGRES_HOST", "127.0.0.1")
    port = env("POSTGRES_PORT", "5432")
    db = env("POSTGRES_DB", "artemis")
    user = env("POSTGRES_USER", "artemis")
    password = env("POSTGRES_PASSWORD", required=True)

    try:
        admin = psycopg.connect(host=host, port=port, dbname="postgres", user=superuser, autocommit=True)
    except psycopg.OperationalError as exc:
        raise SystemExit(
            f"✗ Could not connect to Postgres at {host}:{port} as superuser '{superuser}'.\n"
            f"  Is Postgres running? (Homebrew: brew services start postgresql@16)\n"
            f"  Use --superuser NAME if your admin role is different.\n  ({exc})"
        ) from exc

    with admin, admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
        verb = "ALTER" if cur.fetchone() else "CREATE"
        cur.execute(
            sql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.SQL(verb), sql.Identifier(user), sql.Literal(password)
            )
        )
        print(f"✓ {'Updated' if verb == 'ALTER' else 'Created'} role '{user}'")

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
        if cur.fetchone():
            print(f"✓ Database '{db}' already exists")
        else:
            cur.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(db), sql.Identifier(user))
            )
            print(f"✓ Created database '{db}'")


def apply_schema() -> None:
    sql_path = ROOT / "scripts" / "init.sql"
    with conn() as c, c.cursor() as cur:
        cur.execute(sql_path.read_text())
        c.commit()
    print(f"✓ Schema applied from {sql_path.relative_to(ROOT)}")
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        )
        print(f"✓ {cur.fetchone()[0]} tables present")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--create-role", action="store_true",
                    help="create the role and database on a local Postgres first")
    ap.add_argument("--superuser", default=getpass.getuser(),
                    help="Postgres admin role for --create-role (default: your OS user)")
    args = ap.parse_args()

    if args.create_role:
        create_role_and_db(args.superuser)
    apply_schema()
    return 0


if __name__ == "__main__":
    sys.exit(main())
