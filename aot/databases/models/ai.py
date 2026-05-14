# coding=utf-8
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import datetime

from aot.databases import CRUDMixin
from aot.databases import set_uuid
from aot.aot_flask.extensions import db

class AIEntry(CRUDMixin, db.Model):
    """
    Represents an AI Service Connection (Provider).
    Similar to 'Input' in AoT.

    @phase active
    @stability stable
    """
    __tablename__ = "ai_entry"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)
    name = db.Column(db.String(100), nullable=False)
    
    # Engine & Connection settings
    model_type = db.Column(db.String(50), default='gemini') # gemini, openai, ollama, etc.
    model_name = db.Column(db.String(100), default='gemini-2.0-flash')
    api_endpoint = db.Column(db.String(255), default='')
    
    # Authentication (Decoupled from persona)
    auth_type = db.Column(db.String(20), default='api_key') # api_key, account, oauth2, no_auth
    auth_id = db.Column(db.String(100), default='')
    api_key = db.Column(db.Text, default='')
    
    is_activated = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # GridStack layout positions
    position_x = db.Column(db.Integer, default=0)
    position_y = db.Column(db.Integer, default=0)
    width = db.Column(db.Integer, default=24)
    height = db.Column(db.Integer, default=1)

    def __repr__(self):
        return f"<AIEntry(name={self.name}, type={self.model_type})>"

class AIAgent(CRUDMixin, db.Model):
    """
    Represents an AI Persona/Logic.
    Uses an AIEntry as its 'Brain'.

    @phase active
    @stability stable
    @dependency AIEntry
    """
    __tablename__ = "ai_agent"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)
    name = db.Column(db.String(100), nullable=False)
    
    # Link to Service Provider (Brain)
    entry_id = db.Column(db.String(36), db.ForeignKey('ai_entry.unique_id'), nullable=True)
    
    # Persona & Behavior
    role = db.Column(db.String(20), default='worker') # supervisor, worker (legacy)
    specialty = db.Column(db.String(100), default='general')
    system_prompt = db.Column(db.Text().with_variant(LONGTEXT, "mysql", "mariadb"), default='You are a helpful assistant.')
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=2048)

    # v6 Pipeline Role & Configuration
    pipeline_role = db.Column(db.String(20), default='worker')  # router, planner, executor, synthesizer, worker
    model_tier = db.Column(db.String(20), default='standard')   # lightweight, standard, heavy
    model_name = db.Column(db.String(128), default='')           # Override entry model_name if set (from role preset)
    tool_access = db.Column(db.String(20), default='auto')      # all, none, assigned, auto
    
    # Provider-specific configuration and auth tokens
    custom_options_json = db.Column(db.Text().with_variant(LONGTEXT, "mysql", "mariadb"), default='{}')
    
    is_activated = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # GridStack layout positions
    position_x = db.Column(db.Integer, default=0)
    position_y = db.Column(db.Integer, default=0)
    width = db.Column(db.Integer, default=24)
    height = db.Column(db.Integer, default=1)

    # Relationship to Entry
    entry = db.relationship('AIEntry', backref='agents')

    def __repr__(self):
        return f"<AIAgent(name={self.name}, role={self.role})>"


class AgentRolePreset(CRUDMixin, db.Model):
    """
    DB-managed pipeline role configurations for AI Agent setup UX.

    @phase active
    @stability stable
    """
    __tablename__ = 'agent_role_preset'
    __table_args__ = {'extend_existing': True}

    pipeline_role = db.Column(db.String(32), primary_key=True)
    ai_name_unique = db.Column(db.String(64), nullable=False)
    model_value = db.Column(db.String(128), nullable=False)
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=4096)
    role_description_en = db.Column(db.Text, nullable=True)
    role_description_ko = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AgentRolePreset(pipeline_role={self.pipeline_role}, model={self.model_value})>"


class AIHistory(CRUDMixin, db.Model):
    """
    Logs every reasoning cycle.

    @phase active
    @stability stable
    @dependency AIAgent
    """
    __tablename__ = "ai_history"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, unique=True, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)
    agent_id = db.Column(db.String(36), db.ForeignKey('ai_agent.unique_id'), nullable=False)
    
    goal = db.Column(db.Text, nullable=False)
    insight = db.Column(db.Text().with_variant(LONGTEXT, "mysql", "mariadb"))
    
    actions_json = db.Column(db.Text().with_variant(LONGTEXT, "mysql", "mariadb"), default='[]')
    status = db.Column(db.String(20), default='proposed') 
    execution_result = db.Column(db.Text, default='')
    metadata_json = db.Column(db.Text().with_variant(LONGTEXT, "mysql", "mariadb"), default='{}')
    
    # v2.1: Conversation Threading
    thread_id = db.Column(db.String(36), nullable=True, index=True)
    message_type = db.Column(db.String(20), default='ai') # ai, user, system, assistant

    # v2.2: Per-user isolation (REQ-1) — nullable for backward compat with legacy records
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<AIHistory(goal={self.goal[:20]}..., status={self.status})>"


# @ANCHOR: AI_ROLE_CONFIG_MODEL
class AIRoleConfig(CRUDMixin, db.Model):
    """
    Layer 2 (Global Dynamic) — Runtime overrides for AI role system_prompt and specialty.
    Only rows that differ from YAML seed defaults (aot/config/ai_role_config.yaml) need to exist.
    Ref: SBS-002_V2_STRATEGY (layer_2_global_dynamic.tables[AIRoleConfig])

    @phase active
    @stability stable
    """
    __tablename__ = "ai_role_config"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    role_key = db.Column(db.String(50), nullable=False, unique=True)
    system_prompt = db.Column(db.Text().with_variant(LONGTEXT, "mysql", "mariadb"), nullable=True)
    specialty = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AIRoleConfig(role_key={self.role_key}, is_active={self.is_active})>"


# @ANCHOR: AI_ACTION_REGISTRY_MODEL
class AIActionRegistry(CRUDMixin, db.Model):
    """
    Layer 2 (Global Dynamic) — Runtime overrides for action routing and eligibility flags.
    Only rows that differ from YAML seed defaults (aot/config/ai_action_registry.yaml) need to exist.
    synced_from_mcp: set by REF-004 Auto-Sync Trigger (MCPBridgeService post-connect).
    Ref: SBS-002_V2_STRATEGY (layer_2_global_dynamic.tables[AIActionRegistry])

    @phase active
    @stability stable
    """
    __tablename__ = "ai_action_registry"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(80), nullable=False, unique=True)
    is_rag_eligible = db.Column(db.Boolean, default=False)
    is_immediate = db.Column(db.Boolean, default=False)
    resolver_module = db.Column(db.String(200), default='')
    is_active = db.Column(db.Boolean, default=True)
    synced_from_mcp = db.Column(db.Boolean, default=False)
    last_synced_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<AIActionRegistry(action_type={self.action_type}, is_immediate={self.is_immediate})>"
