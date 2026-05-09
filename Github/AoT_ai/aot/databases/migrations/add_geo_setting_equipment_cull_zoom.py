#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: Add `equipment_cull_zoom` column to geo_setting table.

equipment_cull_zoom controls the zoom level below which equipment
markers are culled from the map view.

NOTE: This migration is also tracked in Alembic as:
  alembic_db/alembic/versions/b3c4d5e6f7a8_add_equipment_cull_zoom_to_geo_setting.py
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
        if not _has_column("geo_setting", "equipment_cull_zoom"):
            print("  + adding equipment_cull_zoom column to geo_setting")
            db.session.execute(text(
                "ALTER TABLE geo_setting ADD COLUMN equipment_cull_zoom INTEGER DEFAULT 15"
            ))
            db.session.commit()
            print("Done.")
        else:
            print("  - geo_setting.equipment_cull_zoom already exists")


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
