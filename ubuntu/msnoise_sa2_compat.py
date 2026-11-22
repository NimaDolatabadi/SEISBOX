"""SQLAlchemy 2.x compatibility for MSNoise 1.6.5 (SEISBOX).

MSNoise 1.6.5 was written for SQLAlchemy 1.x. With SQLAlchemy 2 (needed by
pandas 3 and ObsPy in this environment) two old call styles fail:

  * session.execute("UPDATE ...")       -> plain SQL strings must be text("...")
  * engine.execute(stmt, params)        -> Engine.execute was removed

This module restores both, and only inside MSNoise processes: it is imported
from msnoise/__init__.py (setup.sh adds that line), so nothing else in the
geo environment is affected.
"""
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

if not getattr(sqlalchemy, "_seisbox_msnoise_compat", False):
    sqlalchemy._seisbox_msnoise_compat = True

    def _wrap(fn):
        def execute(self, statement, *args, **kwargs):
            if isinstance(statement, str):
                statement = text(statement)
            return fn(self, statement, *args, **kwargs)
        execute.__doc__ = fn.__doc__
        return execute

    Session.execute = _wrap(Session.execute)
    Connection.execute = _wrap(Connection.execute)

    def _engine_execute(self, statement, *args, **kwargs):
        """SQLAlchemy 1.x Engine.execute: run in its own transaction, commit,
        and return the rows (as mappings, so dict(row) works) when there are any."""
        if isinstance(statement, str):
            statement = text(statement)
        with self.begin() as conn:
            result = conn.execute(statement, *args, **kwargs)
            if result.returns_rows:
                return result.mappings().all()
            return result

    Engine.execute = _engine_execute
