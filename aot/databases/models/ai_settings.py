# coding=utf-8
import uuid
from aot.aot_flask.extensions import db
from aot.databases import CRUDMixin

class AIGlobalSettings(CRUDMixin, db.Model):
    """
    Singleton configuration for Global AI Behavior.
    Controls autonomy levels, model routing, constraints, and limits.

    @phase active
    @stability stable
    """
    id = db.Column(db.Integer, primary_key=True, default=1)
    unique_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Core Persona & Behavior
    from sqlalchemy.dialects.mysql import LONGTEXT
    system_prompt_template = db.Column(db.Text().with_variant(LONGTEXT, "mysql", "mariadb"), nullable=True)
    
    # Approval & Safety
    auto_approve_routine = db.Column(db.Boolean, default=False)
    max_impact_auto_approve = db.Column(db.Integer, default=30)
    blackout_start = db.Column(db.String(10), default="23:00")
    blackout_end = db.Column(db.String(10), default="06:00")
    require_feedback = db.Column(db.Boolean, default=True)
    
    # Engine Routing
    default_supervisor = db.Column(db.String(50), default="gemini-1.5-pro")
    default_worker = db.Column(db.String(50), default="gemini-1.5-flash")
    
    # Scheduling & Context
    context_hours = db.Column(db.Integer, default=24)
    max_history = db.Column(db.Integer, default=5)
    
    # Cost Management
    budget_limit_usd = db.Column(db.Float, default=10.0)
    
    # Feature Toggle
    ai_enabled = db.Column(db.Boolean, default=False, nullable=False)

    # Context Layer Toggle
    context_broadcast_enabled = db.Column(db.Boolean, default=True, nullable=True)
