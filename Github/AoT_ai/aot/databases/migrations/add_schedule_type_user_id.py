#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: Add `schedule_type` and `user_id` columns to scheduler_jobs_meta.

schedule_type: ENUM('device','human','ai_system') — who/what created the job
user_id: nullable FK to user — which user owns human-created jobs

NOTE: This migration is also tracked in Alembic as:
  alembic_db/alembic/versions/c3d4e5f6a7b8_add_schedule_type_user_id_to_scheduler.py
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
        changed = False
        if not _has_column("scheduler_jobs_meta", "schedule_type"):
            print("  + adding schedule_type column to scheduler_jobs_meta")
            db.session.execute(text(
                "ALTER TABLE scheduler_jobs_meta "
                "ADD COLUMN schedule_type VARCHAR(20) NOT NULL DEFAULT 'ai_system'"
            ))
            db.session.execute(text(
                "UPDATE scheduler_jobs_meta "
                "SET schedule_type = 'ai_system' "
                "WHERE schedule_type IS NULL OR schedule_type = ''"
            ))
            changed = True
        else:
            print("  - scheduler_jobs_meta.schedule_type already exists")

        if not _has_column("scheduler_jobs_meta", "user_id"):
            print("  + adding user_id column to scheduler_jobs_meta")
            db.session.execute(text(
                "ALTER TABLE scheduler_jobs_meta ADD COLUMN user_id INTEGER DEFAULT NULL"
            ))
            changed = True
        else:
            print("  - scheduler_jobs_meta.user_id already exists")

        if changed:
            db.session.commit()
        print("Done.")


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
