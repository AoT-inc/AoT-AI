#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: Add `timezone` column to all device tables and backfill from coords.

Affected tables: input, output, controller, custom_controller, function,
conditional, trigger.

The column stores the IANA timezone name (e.g. 'Asia/Seoul') derived from the
device's latitude/longitude. Devices without coordinates leave the column NULL
and fall back through aot.utils.device_tz.get_device_tz().
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text

from aot.aot_flask.app import create_app
from aot.aot_flask.extensions import db

TARGET_TABLES = [
    "input",
    "output",
    "pid",
    "custom_controller",
    "function",
    "conditional",
    "trigger",
]


def _has_column(table, column):
    rows = db.session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def _add_column(table):
    if not _has_column(table, "timezone"):
        print(f"  + adding timezone column to {table}")
        db.session.execute(text(
            f"ALTER TABLE {table} ADD COLUMN timezone VARCHAR(64) DEFAULT NULL"
        ))
    else:
        print(f"  - {table}.timezone already exists")


def _backfill(table):
    try:
        from aot.utils.device_tz import resolve_tz_from_coords
    except Exception as exc:
        print(f"  ! timezonefinder unavailable, skipping backfill: {exc}")
        return

    rows = db.session.execute(text(
        f"SELECT id, latitude, longitude FROM {table} "
        f"WHERE timezone IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL"
    )).fetchall()

    updated = 0
    for row in rows:
        tz = resolve_tz_from_coords(row[1], row[2])
        if tz:
            db.session.execute(
                text(f"UPDATE {table} SET timezone = :tz WHERE id = :id"),
                {"tz": tz, "id": row[0]},
            )
            updated += 1
    if updated:
        print(f"  ~ backfilled timezone for {updated} rows in {table}")


def upgrade():
    app = create_app()
    with app.app_context():
        for tbl in TARGET_TABLES:
            try:
                _add_column(tbl)
            except Exception as exc:
                print(f"  ! failed to add column on {tbl}: {exc}")
        db.session.commit()

        for tbl in TARGET_TABLES:
            try:
                _backfill(tbl)
            except Exception as exc:
                print(f"  ! backfill failed for {tbl}: {exc}")
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
