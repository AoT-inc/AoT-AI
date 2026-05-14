#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: Add `model_name` column to ai_agent table.

model_name stores the specific model identifier used by the agent
(e.g. 'gemini-2.0-flash', 'gpt-4o', 'claude-3-5-sonnet').

NOTE: This migration is also tracked in Alembic as:
  alembic_db/alembic/versions/718f314963c3_add_ai_entry_agent_history_tables.py
Run this script only if Alembic is not available.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text

from aot.aot_flask.app import create_app
from aot.aot_flask.extensions import db


def _has_column(table, column):
    rows = db.session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def upgrade():
    app = create_app()
    with app.app_context():
        if not _has_column("ai_agent", "model_name"):
            print("  + adding model_name column to ai_agent")
            db.session.execute(text(
                "ALTER TABLE ai_agent ADD COLUMN model_name VARCHAR(100) DEFAULT 'gemini-2.0-flash'"
            ))
            db.session.commit()
            print("Done.")
        else:
            print("  - ai_agent.model_name already exists")


def downgrade():
    print("SQLite does not support DROP COLUMN directly — column left in place.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upgrade", "downgrade"])
    args = parser.parse_args()
    if args.action == "upgrade":
        upgrade()
    else:
        downgrade()
