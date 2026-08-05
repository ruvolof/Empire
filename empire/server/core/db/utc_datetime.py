"""tz-aware UTC DateTime column type and dialect-aware ``utcnow()`` SQL expression.

Vendored from ``sqlalchemy-utc`` (https://github.com/spoqa/sqlalchemy-utc) to
remove the runtime dependency. The library only ever shipped these two
helpers; per-dialect SQL emitted by ``utcnow()`` is byte-identical to
upstream, so the existing schema and default expressions are preserved.

Original copyright and MIT permission notice for ``sqlalchemy-utc``:

    Copyright (C) 2015-2016 by Hong Minhee <http://hongminhee.org/>

    Permission is hereby granted, free of charge, to any person obtaining a
    copy of this software and associated documentation files (the "Software"),
    to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense,
    and/or sell copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included
    in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
    OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
    TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
    SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import DateTime, TypeDecorator


class UtcDateTime(TypeDecorator):
    """``DateTime(timezone=True)`` that always round-trips tz-aware UTC values.

    Rejects naive datetimes on bind (catches a class of bugs MySQL/SQLite
    would otherwise silently swallow) and re-attaches UTC on read for
    dialects that drop tzinfo (MySQL, SQLite).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if not isinstance(value, datetime):
                raise TypeError(f"expected datetime.datetime, not {value!r}")
            if value.tzinfo is None:
                raise ValueError("naive datetime is disallowed")
            return value.astimezone(UTC)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            else:
                value = value.astimezone(UTC)
        return value


class utcnow(FunctionElement):
    """SQL expression rendering ``UTC NOW()`` per dialect.

    MySQL's ``CURRENT_TIMESTAMP`` is session-local, so it's wrapped with
    ``CONVERT_TZ`` to UTC; SQLite needs explicit ``%f`` formatting to keep
    sub-second precision. PostgreSQL/Oracle are correct by default.
    """

    type = UtcDateTime()
    inherit_cache = True


@compiles(utcnow)
def _default_sql_utcnow(element, compiler, **kw):
    return "CURRENT_TIMESTAMP"


@compiles(utcnow, "mysql")
def _mysql_sql_utcnow(element, compiler, **kw):
    return "CONVERT_TZ(CURRENT_TIMESTAMP, @@session.time_zone, '+00:00')"


@compiles(utcnow, "sqlite")
def _sqlite_sql_utcnow(element, compiler, **kw):
    return r"(STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))"


@compiles(utcnow, "mssql")
def _mssql_sql_utcnow(element, compiler, **kw):
    return "GETUTCDATE()"
