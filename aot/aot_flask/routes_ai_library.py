# coding=utf-8
"""
routes_ai_library.py — AI Library Blueprint.

Provides the /ai/library page and REST API for managing AIContextSource entries.
Each source is an external data connection that periodically injects knowledge
into the AI context pipeline (AIContextRecord).
"""
import json
import logging

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user

from aot.aot_flask.extensions import db
from aot.aot_flask.utils import utils_general
from aot.databases.models import AIContextSource, Misc
from aot.ai.services.context_source_service import sync_source

logger = logging.getLogger(__name__)

# @ANCHOR: AI_LIBRARY_BLUEPRINT
ai_library_bp = Blueprint('routes_ai_library', __name__)


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

# Library presets shown in the Add dropdown.
# is_system=True  → system-provided ext clients (aot/ai/context/ext/)
# is_system=False → user-configured custom sources
LIBRARY_PRESETS = {
    # ------------------------------------------------------------------
    # System Libraries — aot/ai/context/ext/
    # ------------------------------------------------------------------
    'ext_smartfarm': {
        'label': 'SmartFarm Productivity (EXT-KR-01)',
        'description': 'RDA SmartFarm optimal setpoints: temperature, humidity, CO2, light per crop/stage.',
        'source_type': 'rest_api',
        'is_system': True,
        'ext_client': 'smartfarm_client.ExtSmartfarmClient',
        'auth_key_name': 'RDA_API_KEY',
        'sync_interval_min': 10080,  # 7 days
    },
    'ext_nongsaro': {
        'label': 'Nongsaro Cultivation Guide (EXT-KR-02)',
        'description': 'Crop cultivation guides and weekly farming calendar from Nongsaro Open API.',
        'source_type': 'rest_api',
        'is_system': True,
        'ext_client': 'nongsaro_client.NongsaroClient',
        'auth_key_name': 'NONGSARO_API_KEY',
        'sync_interval_min': 1440,  # 1 day
    },
    'ext_pest': {
        'label': 'Pest Management Alerts (EXT-KR-03)',
        'description': 'Real-time pest and disease alerts from the National Crop Protection Management System.',
        'source_type': 'rest_api',
        'is_system': True,
        'ext_client': 'pest_management_client.PestManagementClient',
        'auth_key_name': 'NCPMS_API_KEY',
        'sync_interval_min': 360,  # 6 hours
    },
    # ------------------------------------------------------------------
    # Custom Sources — user-configured
    # ------------------------------------------------------------------
    'rest_api': {
        'label': 'REST API',
        'description': 'Fetch data from any external REST API endpoint on a schedule.',
        'source_type': 'rest_api',
        'is_system': False,
    },
    'document': {
        'label': 'Document',
        'description': 'Upload a PDF, text, or markdown file and convert it to AI knowledge.',
        'source_type': 'document',
        'is_system': False,
    },
    'web_url': {
        'label': 'Web URL',
        'description': 'Scrape a web page periodically and create context records from the content.',
        'source_type': 'web_url',
        'is_system': False,
    },
    'internal_query': {
        'label': 'Internal Query',
        'description': 'Run a read-only DB query against the system and inject the result as context.',
        'source_type': 'internal_query',
        'is_system': False,
    },
}


@ai_library_bp.route('/ai/library', methods=['GET'])
@login_required
def page_ai_library():
    """AI Library page — manage external knowledge sources."""
    facility_id = _resolve_facility_id()
    sources = AIContextSource.query.filter_by(
        facility_id=facility_id, is_active=True
    ).order_by(AIContextSource.created_at.desc()).all()
    return render_template(
        'pages/ai/ai_library.html',
        sources=sources,
        facility_id=facility_id,
        active_page='ai_library',
        library_presets=LIBRARY_PRESETS,
    )


# ---------------------------------------------------------------------------
# API: List sources
# ---------------------------------------------------------------------------

@ai_library_bp.route('/api/v1/ai/library/sources', methods=['GET'])
@login_required
def api_list_sources():
    """List all active AIContextSource entries for the current facility."""
    facility_id = request.args.get('facility_id') or _resolve_facility_id()
    sources = AIContextSource.query.filter_by(
        facility_id=facility_id, is_active=True
    ).order_by(AIContextSource.created_at.desc()).all()

    return jsonify({
        'success': True,
        'sources': [_source_to_dict(s) for s in sources],
    })


# ---------------------------------------------------------------------------
# API: Quick-add source (agent-style: immediate add, configure via cog)
# ---------------------------------------------------------------------------

@ai_library_bp.route('/api/v1/ai/library/sources/quick-add', methods=['POST'])
@login_required
def api_quick_add_source():
    """Immediately create a source entry from a preset key with auto-generated defaults.

    Body: { preset_key: str, facility_id?: str }
    Returns: { success: bool, source: dict }

    The user configures the source details afterwards via the settings cog.
    """
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    body = request.get_json(silent=True) or {}
    preset_key = body.get('preset_key', '').strip()
    facility_id = body.get('facility_id') or _resolve_facility_id()

    preset = LIBRARY_PRESETS.get(preset_key)
    if not preset:
        return jsonify({'success': False, 'error': f'Unknown preset: {preset_key}'}), 400

    import uuid as _uuid
    short_id = str(_uuid.uuid4())[:8]
    source_name = preset['label']
    source_type = preset['source_type']
    parameter_name = f"{preset_key}.{short_id}"
    sync_interval_min = preset.get('sync_interval_min', 60)
    config_json = json.dumps({'preset_key': preset_key})

    try:
        source = AIContextSource(
            facility_id=facility_id,
            source_name=source_name,
            source_type=source_type,
            parameter_name=parameter_name,
            config_json=config_json,
            sync_interval_min=sync_interval_min,
            is_active=True,
        )
        db.session.add(source)
        db.session.commit()
        return jsonify({'success': True, 'source': _source_to_dict(source)}), 201

    except Exception as exc:
        logger.exception("api_quick_add_source failed")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# API: Create source
# ---------------------------------------------------------------------------

@ai_library_bp.route('/api/v1/ai/library/sources', methods=['POST'])
@login_required
def api_create_source():
    """Create a new AIContextSource from JSON body."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    body = request.get_json(silent=True) or {}
    facility_id = body.get('facility_id') or _resolve_facility_id()
    source_name = body.get('source_name', '').strip()
    source_type = body.get('source_type', '')
    parameter_name = body.get('parameter_name', '').strip()
    config_json = body.get('config_json', {})
    sync_interval_min = int(body.get('sync_interval_min', 60))

    if not source_name or not source_type or not parameter_name:
        return jsonify({'success': False, 'error': 'source_name, source_type, parameter_name are required'}), 400

    valid_types = {'rest_api', 'document', 'web_url', 'internal_query'}
    if source_type not in valid_types:
        return jsonify({'success': False, 'error': f'Invalid source_type. Must be one of: {valid_types}'}), 400

    try:
        source = AIContextSource(
            facility_id=facility_id,
            source_name=source_name,
            source_type=source_type,
            parameter_name=parameter_name,
            config_json=json.dumps(config_json) if isinstance(config_json, dict) else config_json,
            sync_interval_min=sync_interval_min,
            is_active=True,
        )
        db.session.add(source)
        db.session.commit()
        return jsonify({'success': True, 'source': _source_to_dict(source)}), 201

    except Exception as exc:
        logger.exception("api_create_source failed")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# API: Update source
# ---------------------------------------------------------------------------

@ai_library_bp.route('/api/v1/ai/library/sources/<source_id>', methods=['PATCH'])
@login_required
def api_update_source(source_id):
    """Update fields on an existing AIContextSource."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    source = AIContextSource.query.filter_by(source_id=source_id).first()
    if not source:
        return jsonify({'success': False, 'error': 'Source not found'}), 404

    body = request.get_json(silent=True) or {}
    updatable = ['source_name', 'parameter_name', 'sync_interval_min', 'config_json']
    for field in updatable:
        if field in body:
            val = body[field]
            if field == 'config_json' and isinstance(val, dict):
                val = json.dumps(val)
            setattr(source, field, val)

    try:
        db.session.commit()
        return jsonify({'success': True, 'source': _source_to_dict(source)})
    except Exception as exc:
        logger.exception("api_update_source failed")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# API: Delete source
# ---------------------------------------------------------------------------

@ai_library_bp.route('/api/v1/ai/library/sources/<source_id>', methods=['DELETE'])
@login_required
def api_delete_source(source_id):
    """Soft-delete (deactivate) an AIContextSource."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    source = AIContextSource.query.filter_by(source_id=source_id).first()
    if not source:
        return jsonify({'success': False, 'error': 'Source not found'}), 404

    try:
        source.is_active = False
        db.session.commit()
        return jsonify({'success': True, 'message': f'Source {source_id} deactivated.'})
    except Exception as exc:
        logger.exception("api_delete_source failed")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# API: Activate / Deactivate source
# ---------------------------------------------------------------------------

@ai_library_bp.route('/api/v1/ai/library/sources/<source_id>/activate', methods=['POST'])
@login_required
def api_activate_source(source_id):
    """Set is_enabled=True on an AIContextSource."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    source = AIContextSource.query.filter_by(source_id=source_id).first()
    if not source:
        return jsonify({'success': False, 'error': 'Source not found'}), 404

    try:
        source.is_enabled = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception as exc:
        logger.exception("api_activate_source failed")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


@ai_library_bp.route('/api/v1/ai/library/sources/<source_id>/deactivate', methods=['POST'])
@login_required
def api_deactivate_source(source_id):
    """Set is_enabled=False on an AIContextSource."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    source = AIContextSource.query.filter_by(source_id=source_id).first()
    if not source:
        return jsonify({'success': False, 'error': 'Source not found'}), 404

    try:
        source.is_enabled = False
        db.session.commit()
        return jsonify({'success': True})
    except Exception as exc:
        logger.exception("api_deactivate_source failed")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# API: Sync source
# ---------------------------------------------------------------------------

@ai_library_bp.route('/api/v1/ai/library/sources/<source_id>/sync', methods=['POST'])
@login_required
def api_sync_source(source_id):
    """Trigger an immediate sync for a single AIContextSource."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    source = AIContextSource.query.filter_by(source_id=source_id).first()
    if not source:
        return jsonify({'success': False, 'error': 'Source not found'}), 404

    if not source.is_enabled:
        return jsonify({
            'success': False,
            'error': 'Source is not enabled. Activate it before syncing.',
        }), 400

    messages = sync_source(source_id)
    has_error = bool(messages.get('error'))
    return jsonify({
        'success': not has_error,
        'messages': messages,
        'records_written': messages.get('records_written', 0),
    }), (200 if not has_error else 500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_facility_id():
    """Resolve facility_id from request args or Misc settings."""
    fid = request.args.get('facility_id', None)
    if not fid:
        misc = Misc.query.first()
        if misc and hasattr(misc, 'default_facility_id'):
            fid = misc.default_facility_id
    return fid or 'default'


def _source_to_dict(source):
    """Serialize AIContextSource to a JSON-safe dict."""
    return {
        'source_id': source.source_id,
        'facility_id': source.facility_id,
        'source_name': source.source_name,
        'source_type': source.source_type,
        'parameter_name': source.parameter_name,
        'config_json': source.config_json,
        'sync_interval_min': source.sync_interval_min,
        'last_synced_at': source.last_synced_at.isoformat() if source.last_synced_at else None,
        'last_sync_status': source.last_sync_status,
        'is_active': source.is_active,
        'is_enabled': source.is_enabled if source.is_enabled is not None else True,
        'created_at': source.created_at.isoformat() if source.created_at else None,
    }
