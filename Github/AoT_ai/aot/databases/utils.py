# coding=utf-8
"""
Database connection utilities for AoT — engine caching and session scoping.

This module is NOT indexed. Keep it for human readers only.
"""
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Global cache for database engines
ENGINES = {}
# Shared sessionmaker per engine URI (avoids recreating on every session_scope call)
SESSION_FACTORIES = {}


def get_engine(db_uri):
    """Return a cached SQLAlchemy Engine for the given URI, creating one if needed.

    Uses NullPool for SQLite — pooling provides no benefit for a local file DB and
    causes QueuePool exhaustion under high daemon thread concurrency.

    @phase active
    @dependency sqlalchemy
    """
    if db_uri not in ENGINES:
        ENGINES[db_uri] = create_engine(
            f"{db_uri}?check_same_thread=False",
            poolclass=NullPool,
        )
    return ENGINES[db_uri]


def _get_session_factory(db_uri):
    if db_uri not in SESSION_FACTORIES:
        SESSION_FACTORIES[db_uri] = sessionmaker(bind=get_engine(db_uri))
    return SESSION_FACTORIES[db_uri]


@contextmanager
def session_scope(db_uri):
    """Provide a transactional scope around a series of database operations.

    Creates a Session bound to a cached engine, yields it for use in a with block,
    and automatically commits on success or rolls back on exception.
    The session is always closed in the finally block.

    @phase active
    @dependency get_engine
    """
    session = _get_session_factory(db_uri)()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.exception("Error raised in session_scope.  Session will be rolled back: "
                         "db_uri='{uri}', error='{err}'".format(uri=db_uri, err=e))
        session.rollback()
        raise
    finally:
        session.close()
