# coding=utf-8
#
#  app.py - Flask web server for AoT
#
import base64
import logging
import os
import sys

import flask_login
from flask import Flask, flash, redirect, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import event
from flask_babel import Babel, gettext
from flask_compress import Compress
from flask_limiter import Limiter
from flask_login import current_user
from flask_session import Session
from flask_talisman import Talisman

from aot.config import INSTALL_DIRECTORY, LANGUAGES, ProdConfig
from aot.databases.models import Misc, User, Widget, populate_db
from aot.databases.utils import session_scope
from aot.aot_flask import (routes_admin, routes_authentication,
                                 routes_dashboard, routes_function,
                                 routes_general, routes_input, routes_geo,
                                 routes_method, routes_output, routes_page,
                                 routes_password_reset, routes_remote_admin,
                                 routes_settings, routes_static, routes_notes_api,
                                 routes_ai_agent, routes_tab, routes_camera, routes_orch_api, routes_mcp_api,
                                 routes_ai_monitoring)
from aot.aot_flask.api import api_blueprint, init_api
from aot.aot_flask.extensions import db
from aot.aot_flask.utils.utils_general import get_ip_address
from aot.aot_flask.utils import utils_geo
from aot.utils.layouts import update_layout
from aot.utils.widgets import parse_widget_information

logger = logging.getLogger(__name__)


def create_app(config=ProdConfig):

    """
    Application factory:
        http://flask.pocoo.org/docs/0.11/patterns/appfactories/

    :param config: configuration object that holds config constants
    :returns: Flask
    """
    app = Flask(__name__)
    app.config.from_object(config)

    # Standardize JSON datetime serialization to UTC ISO 8601 with offset
    # (e.g. '2026-05-06T12:34:56+00:00'). Frontend converts to device/viewer TZ.
    try:
        from flask.json.provider import DefaultJSONProvider
        from datetime import datetime as _dt, date as _date, timezone as _tz

        class _AoTJSONProvider(DefaultJSONProvider):
            def default(self, obj):
                if isinstance(obj, _dt):
                    if obj.tzinfo is None:
                        obj = obj.replace(tzinfo=_tz.utc)
                    return obj.astimezone(_tz.utc).isoformat()
                if isinstance(obj, _date):
                    return obj.isoformat()
                return super().default(obj)

        app.json = _AoTJSONProvider(app)
    except Exception as _json_err:
        logger.warning("[json] AoT JSON provider init failed: %s", _json_err)

    # ProxyFix for Docker/Nginx environments
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
    
    # Enable template auto-reload for development
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    from sqlalchemy.pool import NullPool
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30},
        'pool_pre_ping': True,
        'poolclass': NullPool,
    }

    register_extensions(app)
    register_blueprints(app)
    register_widget_endpoints(app)

    from aot.aot_flask.cli_geo import register_geo_cli
    register_geo_cli(app)

    @app.template_filter('from_json_safe')
    def from_json_safe(value):
        import json
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}

    return app


def register_extensions(app):
    """register extensions to the app."""
    app.jinja_env.add_extension('jinja2.ext.do')  # Global values in jinja

    db.init_app(app)  # Influx db time-series database

    # Enable WAL mode for SQLite concurrent access (Flask + Daemon + APScheduler)
    with app.app_context():
        @event.listens_for(db.engine, "connect")
        def _set_sqlite_wal(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # Disable WAL mode for better compatibility with network/cloud-synced filesystems
            # cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    init_api(app)

    app = extension_babel(app)  # Language translations
    app = extension_compress(app)  # Compress app responses with gzip
    app = extension_limiter(app)  # Limit authentication blueprint requests to 200 per minute
    app = extension_login_manager(app)  # User login management
    app = extension_login_manager(app)  # User login management
    app = extension_session(app)  # Server side session
    app = extension_csrf(app) # CSRF Protection
    app = extension_cache(app)  # API response caching

    # Phase 5 EKG: register Notes post-commit signal listener (idempotent)
    try:
        from aot.ai.services.experience_knowledge_graph import EKGService
        EKGService.register_signal_listener()
    except Exception as _ekg_init_err:
        logger.warning("[EKG] Signal listener registration failed: %s", _ekg_init_err)

    # Auto-populate device.timezone from latitude/longitude on insert/update
    try:
        from aot.databases.device_tz_listeners import register_device_tz_listeners
        register_device_tz_listeners()
    except Exception as _tz_init_err:
        logger.warning("[device_tz] Listener registration failed: %s", _tz_init_err)

    # Create and populate database if it doesn't exist
    with app.app_context():
        if os.environ.get("ALEMBIC_RUNNING") != "1":
            db.create_all()
            # Database migration on startup
            from aot.databases.models import alembic_upgrade_db
            alembic_upgrade_db(app)

            populate_db()

            # Seed AI Domain Glossary (term_alias, control_intent) within app context
            try:
                from aot.ai.services.ai_agent_service import bootstrap_ai_glossary
                bootstrap_ai_glossary()
            except Exception as _bg_err:
                logger.warning("[Startup] bootstrap_ai_glossary failed: %s", _bg_err)

            # Ensure AoT system MCP server entry exists and is active on every startup
            try:
                from aot.databases.models.mcp_server import MCPServer
                _aot_mcp = (
                    MCPServer.query.filter(MCPServer.command.contains('aot_mcp_server')).first()
                    or MCPServer.query.filter(MCPServer.name.ilike('%aot%')).first()
                )
                if _aot_mcp:
                    if not _aot_mcp.is_activated:
                        _aot_mcp.is_activated = True
                        db.session.commit()
                        logger.info(f"[Startup] Re-activated AoT MCP server: '{_aot_mcp.name}'")
                    
                    # [TASK_40] v29.1: Always ensure absolute virtualenv path for the interpreter
                    aot_local_dir = os.environ.get('AOT_LOCAL_DIR')
                    _venv_python = os.path.join(INSTALL_DIRECTORY, 'env', 'bin', 'python3')
                    if aot_local_dir and os.path.exists(os.path.join(aot_local_dir, 'env', 'bin', 'python3')):
                        python_bin = os.path.join(aot_local_dir, 'env', 'bin', 'python3')
                    elif os.path.exists(_venv_python):
                        python_bin = _venv_python
                    else:
                        python_bin = sys.executable  # fallback: same interpreter running this process
                    script_path = os.path.join(INSTALL_DIRECTORY, 'aot', 'aot_mcp_server.py')
                    _aot_mcp.command = f"{python_bin} {script_path}"
                    
                    if not _aot_mcp.scope or _aot_mcp.scope != 'general':
                        _aot_mcp.scope = 'general'
                    
                    db.session.commit()
                    logger.info(f"[Startup] Synchronized AoT MCP server command: '{_aot_mcp.command}'")
                else:
                    aot_local_dir = os.environ.get('AOT_LOCAL_DIR')
                    _venv_python = os.path.join(INSTALL_DIRECTORY, 'env', 'bin', 'python3')
                    if aot_local_dir and os.path.exists(os.path.join(aot_local_dir, 'env', 'bin', 'python3')):
                        python_bin = os.path.join(aot_local_dir, 'env', 'bin', 'python3')
                    elif os.path.exists(_venv_python):
                        python_bin = _venv_python
                    else:
                        python_bin = sys.executable  # fallback: same interpreter running this process
                    script_path = os.path.join(INSTALL_DIRECTORY, 'aot', 'aot_mcp_server.py')
                    _aot_mcp = MCPServer(
                        name='AoT System Expert Server',
                        command=f"{python_bin} {script_path}",
                        scope='general',
                        is_activated=True
                    )
                    db.session.add(_aot_mcp)
                    db.session.commit()
                    logger.info(f"[Startup] Auto-created AoT MCP server: '{_aot_mcp.unique_id}'")
            except Exception as e:
                logger.warning(f"[Startup] AoT MCP server auto-setup failed: {e}")

            # Auto-activate InfluxDB MCP Server if measurement_db_password is set.
            # This removes the need for users to manually visit InfluxDB web UI to configure.
            try:
                from aot.databases.models.mcp_server import MCPServer
                from aot.databases.models.misc import Misc
                _settings = Misc.query.first()
                if _settings and _settings.measurement_db_password:
                    _influx_mcp = MCPServer.query.filter(
                        MCPServer.command.contains('influxdb-mcp-server')
                    ).first()
                    if _influx_mcp and not _influx_mcp.is_activated:
                        _influx_mcp.is_activated = True
                        db.session.commit()
                        logger.info(f"[Startup] Auto-activated InfluxDB MCP server (token found in misc): '{_influx_mcp.name}'")
            except Exception as e:
                logger.warning(f"[Startup] InfluxDB MCP auto-activation failed: {e}")

            # Cleanup orphaned MCPServers (no agent mapped)
            # 'general' scope = shared system server, exempt from orphan cleanup
            try:
                from aot.databases.models.mcp_server import MCPServer, AgentMCPAccess
                from aot.databases.models.ai import AIAgent
                for mcp in MCPServer.query.filter_by(is_activated=True).all():
                    if mcp.scope == 'general':
                        continue  # 공유 서버는 에이전트 매핑 없어도 유지
                    has_agent = db.session.query(AgentMCPAccess).join(
                        AIAgent, AgentMCPAccess.agent_unique_id == AIAgent.unique_id
                    ).filter(AgentMCPAccess.mcp_unique_id == mcp.unique_id).first()
                    if not has_agent:
                        mcp.is_activated = False
                        logger.info(f"Startup cleanup: deactivated orphaned MCPServer '{mcp.name}'")
                db.session.commit()
            except Exception as e:
                logger.warning(f"Startup MCP cleanup failed: {e}")

    # Initialize APScheduler after DB is ready
    if os.environ.get("ALEMBIC_RUNNING") != "1" and os.environ.get("AOT_SKIP_SCHEDULER") != "1":
        from aot.ai.services.ai_scheduler_service import AISchedulerService
        AISchedulerService.init_app(app)
        

    # v17.0: Memory Profiler (Phase 0 - Baseline measurement)
    # Enable via environment variable: ENABLE_MEMORY_PROFILING=1
    if os.environ.get("ENABLE_MEMORY_PROFILING") == "1":
        try:
            from aot.utils.memory_profiler import MemoryProfiler
            MemoryProfiler.start_profiling()

            # Schedule hourly snapshots
            from apscheduler.schedulers.background import BackgroundScheduler
            profiler_scheduler = BackgroundScheduler()
            profiler_scheduler.add_job(
                func=MemoryProfiler.log_snapshot,
                trigger='interval',
                hours=1,
                id='memory_profiling'
            )
            profiler_scheduler.start()
            logger.info("[MemoryProfiler] Enabled with hourly snapshots")
        except Exception as e:
            logger.warning(f"[MemoryProfiler] Failed to initialize: {e}")

    # [Security] Initialize Talisman with robust defaults
    # CSP: Using 'self' as base, keeping '*' for legacy widget compatibility
    csp = {
        'default-src': ["'self'", '*', "'unsafe-inline'", "'unsafe-eval'"],
        'img-src': ["'self'", '*', 'data:', 'blob:', 'rtsp:', 'rtsps:'],
        'style-src': ["'self'", '*', "'unsafe-inline'"],
        'script-src': ["'self'", '*', "'unsafe-inline'", "'unsafe-eval'"],
        'connect-src': ["'self'", '*', 'rtsp:', 'rtsps:'],
        'media-src': ["'self'", '*', 'data:', 'blob:', 'rtsp:', 'rtsps:'],
        'worker-src': ["'self'", '*', 'blob:']
    }

    force_https = False
    # Skip reading Misc during Alembic runs (schema may be mid-upgrade)
    if os.environ.get("ALEMBIC_RUNNING") != "1":
        # Check user option to force all web connections to use SSL
        # Fail if the URI is empty (pytest is running)
        if app.config['SQLALCHEMY_DATABASE_URI'] != 'sqlite://':
            with session_scope(app.config['SQLALCHEMY_DATABASE_URI']) as new_session:
                misc = new_session.query(Misc).first()
                if misc:
                    update_layout(misc.custom_layout)
                    force_https = misc.force_https

    # Disable force_https and adjust cookies for Docker environment
    from aot.config import DOCKER_CONTAINER
    if DOCKER_CONTAINER:
        force_https = False
        app.config['SESSION_COOKIE_SECURE'] = False
        app.config['WTF_CSRF_SSL_STRICT'] = False
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        app.config['WTF_CSRF_TIME_LIMIT'] = None

    Talisman(app, 
             content_security_policy=csp, 
             force_https=False, # Hybrid Optimization: Disable forced SSL for local/SMB accessibility
             strict_transport_security=False,
             session_cookie_secure=False,
             session_cookie_http_only=True,
             frame_options='SAMEORIGIN')


def register_blueprints(app):
    """register blueprints to the app."""
    app.register_blueprint(routes_admin.blueprint)  # register admin views
    app.register_blueprint(routes_authentication.blueprint)  # register login/logout views
    app.register_blueprint(routes_password_reset.blueprint)  # register password reset views
    app.register_blueprint(routes_dashboard.blueprint)  # register dashboard views
    app.register_blueprint(routes_function.blueprint)  # register function views
    app.register_blueprint(routes_general.blueprint)  # register general routes
    app.register_blueprint(routes_input.blueprint)  # register input routes
    app.register_blueprint(routes_method.blueprint)  # register method views
    app.register_blueprint(routes_output.blueprint)  # register output views
    app.register_blueprint(routes_page.blueprint)  # register page views
    app.register_blueprint(routes_remote_admin.blueprint)  # register remote admin views
    app.register_blueprint(routes_settings.blueprint)  # register settings views
    app.register_blueprint(routes_geo.blueprint)  # register geo views
    app.register_blueprint(routes_static.blueprint)  # register static routes
    app.register_blueprint(routes_notes_api.blueprint)  # register notes api routes
    app.register_blueprint(routes_ai_agent.blueprint)  # register ai agent routes
    app.register_blueprint(routes_tab.blueprint)  # register tab routes
    app.register_blueprint(routes_camera.blueprint)  # register camera routes
    app.register_blueprint(routes_orch_api.blueprint)  # register orch api routes
    app.register_blueprint(routes_mcp_api.blueprint)   # register mcp api routes
    app.register_blueprint(routes_ai_monitoring.ai_monitoring_bp)  # register ai monitoring routes
    from aot.aot_flask import routes_ai_api, routes_locale_api, routes_scheduler, routes_ai_context, routes_ai_portal
    app.register_blueprint(routes_ai_api.blueprint)  # register ai api routes
    app.register_blueprint(routes_ai_context.blueprint)  # register ai context routes
    app.register_blueprint(routes_ai_portal.blueprint)  # register ai portal routes
    app.register_blueprint(routes_locale_api.blueprint)  # register locale api routes
    app.register_blueprint(routes_scheduler.blueprint)  # register scheduler routes
    from aot.aot_flask.routes_ai_library import ai_library_bp
    app.register_blueprint(ai_library_bp)  # register ai library routes


def register_widget_endpoints(app):
    try:
        if app.config['TESTING']:  # TODO: Add pytest endpoint test and remove this
            return

        dict_widgets = parse_widget_information()

        with session_scope(app.config['SQLALCHEMY_DATABASE_URI']) as new_session:
            widget = new_session.query(Widget).all()
            widget_types = []
            for each_widget in widget:
                if each_widget.graph_type not in widget_types:
                    widget_types.append(each_widget.graph_type)

            for each_widget_type in widget_types:
                if each_widget_type in dict_widgets and 'endpoints' in dict_widgets[each_widget_type]:
                    for rule, endpoint, view_func, methods in dict_widgets[each_widget_type]['endpoints']:
                        if endpoint in app.view_functions:
                            logger.info(
                                "Endpoint {} ({}) already exists. Not adding.".format(
                                    endpoint, rule))
                        else:
                            logger.info(
                                "Adding endpoint {} ({}).".format(endpoint, rule))
                            app.add_url_rule(rule, endpoint, view_func, methods=methods)
    except:
        logger.exception("Adding Widget Endpoints")


def extension_babel(app):
    def get_locale():
        # Check if a user is logged in and a language is set
        try:
            user = User.query.filter(
                User.id == flask_login.current_user.id).first()
            if user and user.language != '':
                for key in LANGUAGES:
                    if key == user.language:
                        return key
        except AttributeError:  # Bypass endpoint test error "'AnonymousUserMixin' object has no attribute 'id'"
            pass

        # Check the session for a language
        try:
            from flask import session
            if session.get("language") and session['language'] in LANGUAGES:
                return session['language']
        except:
            pass

        # Check for the presence of AoT/.language with a language
        try:
            lang_path = os.path.join(INSTALL_DIRECTORY, ".language")
            if os.path.exists(lang_path):
                with open(lang_path) as f:
                    language = f.read().split(":")[0]
                    if language and language in LANGUAGES:
                        return language
        except:
            pass

        return request.accept_languages.best_match(LANGUAGES.keys())
    
    def get_timezone():
        # Check if a timezone is set in the Misc database
        try:
            from aot.databases.models import Misc
            misc = Misc.query.first()
            if misc and misc.timezone:
                return misc.timezone
        except Exception:
            pass
        return 'UTC'

    babel = Babel(app, locale_selector=get_locale, timezone_selector=get_timezone)
    return app


def extension_compress(app):
    compress = Compress()
    compress.init_app(app)
    return app


def extension_limiter(app):
    def get_key_func():
        """Custom key_func for flask-limiter to handle both logged-in and logged-out requests."""
        if get_ip_address():
            str_return = get_ip_address()
        else:
            str_return = '0.0.0.0'
        if current_user and hasattr(current_user, 'name'):
            str_return += f'/{current_user.name}'
        return str_return

    limiter = Limiter(app=app, key_func=get_key_func, headers_enabled=True)
    limiter.limit("300/hour")(routes_authentication.blueprint)
    limiter.limit("20/hour")(routes_password_reset.blueprint)
    limiter.limit("200/minute")(api_blueprint)
    return app


def extension_login_manager(app):
    login_manager = flask_login.LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def user_loader(user_id):
        user = User.query.filter(User.id == user_id).first()
        if not user:
            return
        return user

    @login_manager.request_loader
    def load_user_from_request(req):
        try:  # first, try to login using the api_key url arg
            api_key = req.args.get('api_key').replace(' ', '+')
            api_key = base64.b64decode(api_key)
            user = User.query.filter_by(api_key=api_key).first()
            if user:
                return user
        except:
            pass

        try:  # next, try to login using Basic Auth
            api_key = req.headers.get('Authorization')
            api_key = api_key.replace('Basic ', '', 1)
            api_key = base64.b64decode(api_key)
            user = User.query.filter_by(api_key=api_key).first()
            if user:
                return user
        except:
            pass

        try:  # next, try to login using X-API-KEY
            api_key = req.headers.get('X-API-KEY')
            api_key = base64.b64decode(api_key)
            user = User.query.filter_by(api_key=api_key).first()
            if user:
                return user
        except:
            pass

        # User unable to be logged in
        return

    @login_manager.unauthorized_handler
    def unauthorized():
        try:
            if str(request.url_rule).startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
        except:
            pass
        flash(gettext('Please log in to access this page'), "error")
        return redirect(url_for('routes_authentication.login_check'))

    return app


def extension_session(app):
    # TODO: Remove this code if AoT doesn't produce this issue anymore
    # If "EOFError: Ran out of input" returns, consider removing flask-session using filesystem
    # https://github.com/pallets/cachelib/issues/21
    # https://github.com/fengsp/flask-session/issues/132
    # try:
    #     # Remove flask_session directory every time flask starts
    #     import shutil
    #     shutil.rmtree('/opt/AoT/aot/flask_session')
    # except:
    #     pass

    app.config['SESSION_TYPE'] = 'filesystem'
    # Partition session files by UID to prevent PermissionError when 
    # running daemon (root) vs UI (normal user)
    session_dir = os.path.join(os.getcwd(), f'flask_session_{os.getuid()}')
    app.config['SESSION_FILE_DIR'] = session_dir
    Session(app)

    return app


def extension_csrf(app):
    from aot.aot_flask.extensions import csrf
    from aot.aot_flask.api import api_blueprint
    csrf.init_app(app)
    csrf.exempt(api_blueprint)
    return app


def extension_cache(app):
    from aot.aot_flask.extensions import cache
    cache.init_app(app)
    return app
