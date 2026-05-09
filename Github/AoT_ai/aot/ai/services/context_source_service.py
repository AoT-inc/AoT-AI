# coding=utf-8
"""
utils_ai_context_source.py — Sync utilities for AIContextSource.

Dispatches sync operations by source_type and writes results into AIContextRecord.
All functions return a messages dict: {"success": [], "info": [], "warning": [], "error": []}.
"""
import json
import logging
import pathlib
from datetime import datetime

from bs4 import BeautifulSoup
from aot.aot_flask.extensions import db
from aot.databases.models import AIContextSource, AIContextRecord, AILibrarySyncLog

logger = logging.getLogger(__name__)

# @ANCHOR: EXT_CLIENT_MAP
# Maps preset_key → fully-qualified class path for ext system source clients.
# Used by _dispatch_ext_client() to dynamically load the correct client.
EXT_CLIENT_MAP = {
    'ext_smartfarm': 'aot.ai.context.ext.smartfarm_client.ExtSmartfarmClient',
    'ext_nongsaro':  'aot.ai.context.ext.nongsaro_client.NongsaroClient',
    'ext_pest':      'aot.ai.context.ext.pest_management_client.PestManagementClient',
}


# @ANCHOR: SYNC_SOURCE_DISPATCHER
def sync_source(source_id):
    """
    Load AIContextSource by source_id, dispatch to appropriate fetch handler,
    and persist results as AIContextRecord rows.

    Dispatch priority:
        1. If config_json contains a preset_key registered in EXT_CLIENT_MAP,
           route to the corresponding ext client via _dispatch_ext_client().
        2. Otherwise, dispatch by source_type (rest_api, document, web_url,
           internal_query) — unchanged behaviour.

    Returns a messages dict with keys:
        success, info, warning, error (list[str] each), records_written (int).
    """
    messages = {"success": [], "info": [], "warning": [], "error": [], "records_written": 0}
    source = None
    config = {}

    try:
        source = AIContextSource.query.filter_by(source_id=source_id, is_active=True).first()
        if not source:
            messages["error"].append(f"Source not found or inactive: {source_id}")
            return messages

        try:
            config = json.loads(source.config_json or '{}')
        except (ValueError, TypeError):
            messages["warning"].append("config_json is malformed — using empty config.")

        # Pre-check: route to ext client if preset_key is in EXT_CLIENT_MAP
        preset_key = config.get('preset_key', '')
        records = None
        err = None
        raw_payload = None

        if preset_key and preset_key in EXT_CLIENT_MAP:
            result = _dispatch_ext_client(source, config, preset_key)
            if isinstance(result, dict) and 'error' in result:
                err = result['error']
            else:
                records = result
                raw_payload = json.dumps(records)[:10000] if records else None
        else:
            # Dispatch by source_type (existing logic — unchanged)
            value = None
            if source.source_type == 'rest_api':
                value, err = _fetch_rest_api(source, config)
            elif source.source_type == 'document':
                value, err = _parse_document(source, config)
            elif source.source_type == 'web_url':
                value, err = _fetch_web_url(source, config)
            elif source.source_type == 'internal_query':
                value, err = _run_internal_query(source, config)
            else:
                err = f"Unknown source_type: {source.source_type}"
                value = None

            if not err and value is not None:
                records = [{'parameter_name': source.parameter_name, 'value': str(value)}]
                raw_payload = str(value)[:10000]

        if err:
            source.last_sync_status = 'error'
            source.last_synced_at = datetime.utcnow()
            db.session.commit()
            messages["error"].append(err)
            # @ANCHOR: SYNC_LOG_WRITE_ERROR
            _write_sync_log(
                source_id=source_id,
                source=source,
                config=config,
                raw_payload=None,
                records_written=0,
                sync_status='error',
                error_message=err[:2000],
            )
            return messages

        count = _write_context_records(source, records or [])
        messages["records_written"] = count

        source.last_synced_at = datetime.utcnow()
        source.last_sync_status = 'ok'
        db.session.commit()

        messages["success"].append(
            f"Synced source '{source.source_name}' → {count} record(s) written."
        )
        # @ANCHOR: SYNC_LOG_WRITE_SUCCESS
        _write_sync_log(
            source_id=source_id,
            source=source,
            config=config,
            raw_payload=raw_payload,
            records_written=count,
            sync_status='ok',
            error_message=None,
        )

    except Exception as exc:
        logger.exception("sync_source failed for source_id=%s", source_id)
        db.session.rollback()
        messages["error"].append(str(exc))
        # @ANCHOR: SYNC_LOG_WRITE_EXCEPTION
        _write_sync_log(
            source_id=source_id,
            source=source,
            config=config,
            raw_payload=None,
            records_written=0,
            sync_status='error',
            error_message=str(exc)[:2000],
        )

    return messages


# @ANCHOR: DISPATCH_EXT_CLIENT
def _dispatch_ext_client(source, config, preset_key):
    """
    Ext client interface contract:
        All ext clients must implement:
            def sync(self, facility_id: str, config: dict) -> list[dict]:
                Returns list of {'parameter_name': str, 'value': str} dicts.
                May return an empty list on error (log internally).

    Dynamically imports and invokes the ext client class registered in EXT_CLIENT_MAP.
    Returns list[dict] on success, or {'error': str} on import/invocation failure.
    If the client module is not yet implemented, logs a warning and returns an error dict
    so the caller can record the sync as failed without raising an exception.
    """
    import importlib

    class_path = EXT_CLIENT_MAP.get(preset_key, '')
    if not class_path:
        return {'error': f'No class mapped for preset_key: {preset_key}'}

    module_path, class_name = class_path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
        client_cls = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        logger.warning("Ext client %s not yet implemented: %s", preset_key, exc)
        return {'error': f'Ext client {preset_key} not yet implemented.'}

    try:
        client = client_cls()
        records = client.sync(facility_id=source.facility_id, config=config)
        return records if isinstance(records, list) else []
    except Exception as exc:
        logger.exception("Ext client %s sync() failed", preset_key)
        return {'error': f'Ext client {preset_key} sync() raised: {exc}'}


# @ANCHOR: WRITE_CONTEXT_RECORDS
def _write_context_records(source, records):
    """
    Upsert a list of records into AIContextRecord.

    Supports two input formats:
        - list[dict]:  [{'parameter_name': str, 'value': str}, ...]
        - list[tuple]: [(param_name, value), ...]

    For each record:
        - If a row with (facility_id, parameter_name, source) already exists: update value.
        - Otherwise: insert a new AIContextRecord.
    Commits once after all records are written.
    Returns count of records written.
    """
    if not records:
        return 0

    count = 0
    for rec in records:
        # Normalise to (param, val) regardless of input type
        if isinstance(rec, dict):
            param = rec.get('parameter_name', '')
            val = rec.get('value', '')
        elif isinstance(rec, (list, tuple)) and len(rec) >= 2:
            param = rec[0]
            val = rec[1]
        else:
            continue

        if not param:
            continue

        existing = AIContextRecord.query.filter_by(
            facility_id=source.facility_id,
            parameter_name=param,
            source=source.source_id,
        ).first()

        if existing:
            existing.value = val
        else:
            db.session.add(AIContextRecord(
                facility_id=source.facility_id,
                parameter_name=param,
                value=val,
                source=source.source_id,
                context_state='system_generated',
                created_by='sync',
            ))

        count += 1

    db.session.commit()
    return count


# @ANCHOR: FETCH_REST_API
def _fetch_rest_api(source, config):
    """
    Fetch value from an external REST API endpoint.

    config keys:
        endpoint_url (str): Target URL
        method (str): 'GET' or 'POST' (default: 'GET')
        auth_type (str): 'none', 'bearer', 'api_key' (default: 'none')
        auth_value (str): Token or key value
        json_path (str): Dot-notation path to extract from response JSON (e.g. 'data.value')
    """
    try:
        import requests

        url = config.get('endpoint_url', '')
        if not url:
            return None, "endpoint_url is required for rest_api source."

        method = config.get('method', 'GET').upper()
        auth_type = config.get('auth_type', 'none')
        auth_value = config.get('auth_value', '')
        json_path = config.get('json_path', '')

        headers = {}
        if auth_type == 'bearer':
            headers['Authorization'] = f'Bearer {auth_value}'
        elif auth_type == 'api_key':
            headers['X-API-Key'] = auth_value

        if method == 'POST':
            resp = requests.post(url, headers=headers, timeout=10)
        else:
            resp = requests.get(url, headers=headers, timeout=10)

        resp.raise_for_status()
        data = resp.json()

        # Extract value via dot-notation path
        if json_path:
            for key in json_path.split('.'):
                if isinstance(data, dict):
                    data = data.get(key)
                else:
                    data = None
                if data is None:
                    break

        return json.dumps(data), None

    except Exception as exc:
        return None, f"rest_api fetch error: {exc}"


# @ANCHOR: EXTRACT_PDF_TEXT
def _extract_pdf_text(path):
    """Extract plain text from a PDF file using pdfplumber.

    Returns extracted text on success, or a descriptive error string if
    pdfplumber is not installed or extraction fails (soft failure — caller
    stores the message as context value rather than raising).
    """
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages_text = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t.strip())
        return '\n\n'.join(pages_text)
    except ImportError:
        return f'[PDF parsing unavailable: pdfplumber not installed. File: {path.name}]'
    except Exception as exc:
        logger.warning('PDF extraction failed for %s: %s', path, exc)
        return f'[PDF extraction failed: {exc}]'


# @ANCHOR: PARSE_DOCUMENT
def _parse_document(source, config):
    """
    Extract text content from a local file path.

    config keys:
        file_path (str): Path to the file (relative paths resolved from app root)
        parse_mode (str): 'full_text', 'summary', 'key_value' (default: 'full_text')

    PDF files (.pdf) are extracted via pdfplumber. All other files are read as
    UTF-8 text with a latin-1 fallback for binary-safe decoding.
    """
    try:
        file_path = config.get('file_path', '')
        if not file_path:
            return None, "file_path is required for document source."

        path = pathlib.Path(file_path)
        if not path.exists():
            return None, f"File not found: {file_path}"

        # Route by file extension
        if path.suffix.lower() == '.pdf':
            content = _extract_pdf_text(path)
        else:
            try:
                content = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                content = path.read_text(encoding='latin-1', errors='replace')

        if not content or not content.strip():
            return None, "No text content extracted from file"

        parse_mode = config.get('parse_mode', 'full_text')
        if parse_mode == 'full_text':
            value = content
        elif parse_mode == 'key_value':
            # Simple key=value extraction
            pairs = {}
            for line in content.splitlines():
                if '=' in line:
                    k, _, v = line.partition('=')
                    pairs[k.strip()] = v.strip()
            value = json.dumps(pairs)
        else:
            # Default: return first 1000 chars as summary
            value = content[:1000]

        return value, None

    except Exception as exc:
        return None, f"document parse error: {exc}"


# @ANCHOR: FETCH_WEB_URL
def _fetch_web_url(source, config):
    """
    Scrape a web page and optionally extract content via CSS selector.

    config keys:
        url (str): Target URL
        css_selector (str): Optional CSS selector for element extraction
    """
    try:
        import requests

        url = config.get('url', '')
        if not url:
            return None, "url is required for web_url source."

        resp = requests.get(url, timeout=15, headers={'User-Agent': 'AoT-AI-Sync/1.0'})
        resp.raise_for_status()
        html = resp.text

        css_selector = config.get('css_selector', '').strip()
        soup = BeautifulSoup(html, 'html.parser')
        if css_selector:
            elements = soup.select(css_selector)
            value = ' '.join(el.get_text(strip=True) for el in elements)
        else:
            # No selector: return plain text of full page (truncated)
            value = soup.get_text(separator=' ', strip=True)[:3000]

        return value, None

    except Exception as exc:
        return None, f"web_url fetch error: {exc}"


# @ANCHOR: RUN_INTERNAL_QUERY
def _run_internal_query(source, config):
    """
    Execute a parameterized SQL query against the application database.

    config keys:
        query_template (str): SQL query (use :param_name placeholders for safety)
        params (dict): Optional parameter bindings for the query
    """
    try:
        from sqlalchemy import text

        query_template = config.get('query_template', '')
        if not query_template:
            return None, "query_template is required for internal_query source."

        params = config.get('params', {})

        with db.engine.connect() as conn:
            result = conn.execute(text(query_template), params)
            rows = [dict(row._mapping) for row in result]

        value = json.dumps(rows)
        return value, None

    except Exception as exc:
        return None, f"internal_query error: {exc}"


# @ANCHOR: WRITE_SYNC_LOG
def _write_sync_log(source_id, source, config, raw_payload,
                    records_written, sync_status, error_message):
    """
    Write one AILibrarySyncLog row for the current sync attempt.
    Silently absorbs any DB error to avoid masking the original sync result.
    Calls _prune_sync_log() after commit to retain only the most recent 20 rows.
    """
    try:
        log = AILibrarySyncLog()
        log.source_id = source_id
        log.facility_id = source.facility_id if source else ''
        log.source_type = getattr(source, 'source_type', 'unknown') if source else 'unknown'
        log.preset_key = config.get('preset_key', '') if config else ''
        log.raw_payload = raw_payload
        log.records_written = records_written
        log.sync_status = sync_status
        log.error_message = error_message
        db.session.add(log)
        db.session.commit()
        _prune_sync_log(source_id)
    except Exception as log_exc:
        logger.warning("Failed to write AILibrarySyncLog for source_id=%s: %s",
                       source_id, log_exc)
        try:
            db.session.rollback()
        except Exception:
            pass


# @ANCHOR: PRUNE_SYNC_LOG
def _prune_sync_log(source_id, keep_last=20):
    """
    Delete AILibrarySyncLog rows for source_id beyond the most recent keep_last rows.
    Silently absorbs any DB error.
    """
    try:
        rows = (
            AILibrarySyncLog.query
            .filter_by(source_id=source_id)
            .order_by(AILibrarySyncLog.synced_at.desc())
            .all()
        )
        if len(rows) > keep_last:
            for old_row in rows[keep_last:]:
                db.session.delete(old_row)
            db.session.commit()
    except Exception as prune_exc:
        logger.warning("Failed to prune AILibrarySyncLog for source_id=%s: %s",
                       source_id, prune_exc)
        try:
            db.session.rollback()
        except Exception:
            pass
