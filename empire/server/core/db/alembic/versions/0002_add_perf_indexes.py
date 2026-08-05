"""add perf indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-28

Indexes for hot-path queries that landed model-only via index=True.
Idempotent: skips any index that already exists, so fresh installs
(where create_all has already made them via Base.metadata) no-op.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (index_name, table, columns) — names match SQLAlchemy auto-generation
# and the explicit Index(...) in models.Agent.__table_args__, so fresh DBs
# show no autogenerate drift.
_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_users_username", "users", ["username"]),
    ("ix_agents_listener_archived", "agents", ["listener", "archived"]),
    ("ix_agent_files_session_id", "agent_files", ["session_id"]),
    ("ix_agent_files_parent_id", "agent_files", ["parent_id"]),
)


def _existing_index_names(bind, table: str) -> set[str]:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        raise RuntimeError(
            f"Migration 0002 expected table '{table}' to exist (it should "
            f"have been created via Base.metadata or an earlier migration). "
            f"DB schema is partial — restore from backup or run "
            f"'server --clean' to reset."
        )
    # Filter out None-named indexes. SQLAlchemy's Inspector.get_indexes()
    # types `name` as Optional[str] because some backends report anonymous
    # / expression indexes. Empire never creates those, but filtering keeps
    # the set type honest and avoids `None in {...}` membership weirdness.
    return {ix["name"] for ix in insp.get_indexes(table) if ix["name"] is not None}


def upgrade() -> None:
    bind = op.get_bind()
    for name, table, columns in _INDEXES:
        if name not in _existing_index_names(bind, table):
            op.create_index(name, table, columns)


def downgrade() -> None:
    bind = op.get_bind()
    is_mysql = bind.dialect.name == "mysql"
    for name, table, _cols in _INDEXES:
        # On MySQL/InnoDB, ix_agent_files_parent_id is the index backing the
        # self-referential agent_files.parent_id -> agent_files.id foreign key.
        # InnoDB requires an index on every FK column and refuses to drop the
        # last one (ERROR 1553), so leave it in place on MySQL — the FK needs
        # it regardless of this migration. SQLite has no such rule and drops
        # it cleanly.
        if is_mysql and name == "ix_agent_files_parent_id":
            continue
        if name in _existing_index_names(bind, table):
            op.drop_index(name, table_name=table)
