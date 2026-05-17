#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: Add `sensors` JSON column to geo_facility table.

The sensors column stores a list of sensor bindings for runtime environment
display in the 3D facility widget.

Schema per entry:
    {
        "role":           str,   # 'indoor_temp' | 'indoor_humidity' | 'indoor_co2'
                                 # 'outdoor_temp' | 'outdoor_humidity'
                                 # 'outdoor_wind' | 'outdoor_wind_dir' | 'outdoor_solar'
        "device_id":      str,   # Input.unique_id
        "measurement_id": str,   # DeviceMeasurements.unique_id
        "name":           str,   # Display label (e.g. '동쪽 온도계')
        "weight":         float  # Averaging weight (default 1.0)
    }

Multiple entries sharing the same role are combined via weighted average.
Stale or unavailable sensors are excluded from the aggregate automatically.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text

from aot.aot_flask.app import create_app
from aot.aot_flask.extensions import db


def _has_column(table: str, column: str) -> bool:
    rows = db.session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def upgrade():
    app = create_app()
    with app.app_context():
        if not _has_column("geo_facility", "sensors"):
            print("  + adding sensors column to geo_facility")
            db.session.execute(text(
                "ALTER TABLE geo_facility ADD COLUMN sensors JSON DEFAULT NULL"
            ))
            db.session.commit()
            print("Done.")
        else:
            print("  - geo_facility.sensors already exists")


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
