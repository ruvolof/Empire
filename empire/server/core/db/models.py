import base64
import enum
import os
from datetime import datetime
from pathlib import Path

import sqlalchemy
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import (
    JSON,
    Column,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Sequence,
    String,
    Table,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from empire.server.core.config.config_manager import (
    PluginAutoExecuteConfig,
    empire_config,
)
from empire.server.core.db.utc_datetime import UtcDateTime, utcnow
from empire.server.core.module_models import EmpireAuthor
from empire.server.utils.datetime_util import is_stale


class Base(DeclarativeBase):
    pass


database_config = empire_config.database
use = os.environ.get("DATABASE_USE", database_config.use)
database_config.use = use
database_config = database_config[use.lower()]


def get_database_config():
    return use, database_config


agent_task_download_assc = Table(
    "agent_task_download_assc",
    Base.metadata,
    Column("agent_task_id", Integer),
    Column("agent_id", String(255)),
    Column("download_id", Integer, ForeignKey("downloads.id")),
    ForeignKeyConstraint(
        ("agent_task_id", "agent_id"), ("agent_tasks.id", "agent_tasks.agent_id")
    ),
)

plugin_task_download_assc = Table(
    "plugin_task_download_assc",
    Base.metadata,
    Column("plugin_task_id", Integer, ForeignKey("plugin_tasks.id")),
    Column("download_id", Integer, ForeignKey("downloads.id")),
    ForeignKeyConstraint(("plugin_task_id",), ("plugin_tasks.id",)),
)

agent_file_download_assc = Table(
    "agent_file_download_assc",
    Base.metadata,
    Column("agent_file_id", Integer, ForeignKey("agent_files.id", ondelete="CASCADE")),
    Column("download_id", Integer, ForeignKey("downloads.id")),
)

stager_download_assc = Table(
    "stager_download_assc",
    Base.metadata,
    Column("stager_id", Integer, ForeignKey("stagers.id")),
    Column("download_id", Integer, ForeignKey("downloads.id")),
)

# this doesn't actually join to anything atm, but is used for the filtering in api/v2/downloads
upload_download_assc = Table(
    "upload_download_assc",
    Base.metadata,
    Column("download_id", Integer, ForeignKey("downloads.id")),
)

listener_tag_assc = Table(
    "listener_tag_assc",
    Base.metadata,
    Column("listener_id", Integer, ForeignKey("listeners.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)

agent_tag_assc = Table(
    "agent_tag_assc",
    Base.metadata,
    Column("agent_id", String(255), ForeignKey("agents.session_id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)

agent_task_tag_assc = Table(
    "agent_task_tag_assc",
    Base.metadata,
    Column("agent_task_id", Integer),
    Column("agent_id", String(255)),
    Column("tag_id", Integer, ForeignKey("tags.id")),
    ForeignKeyConstraint(
        ("agent_task_id", "agent_id"), ("agent_tasks.id", "agent_tasks.agent_id")
    ),
)

plugin_task_tag_assc = Table(
    "plugin_task_tag_assc",
    Base.metadata,
    Column("plugin_task_id", Integer, ForeignKey("plugin_tasks.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)

credential_tag_assc = Table(
    "credential_tag_assc",
    Base.metadata,
    Column("credential_id", Integer, ForeignKey("credentials.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)

download_tag_assc = Table(
    "download_tag_assc",
    Base.metadata,
    Column("download_id", Integer, ForeignKey("downloads.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)


# https://roman.pt/posts/pydantic-in-sqlalchemy-fields/
class PydanticType(sqlalchemy.types.TypeDecorator):
    """Pydantic type.
    SAVING:
    - Uses SQLAlchemy JSON type under the hood.
    - Acceps the pydantic model and converts it to a dict on save.
    - SQLAlchemy engine JSON-encodes the dict to a string.
    RETRIEVING:
    - Pulls the string from the database.
    - SQLAlchemy engine JSON-decodes the string to a dict.
    - Uses the dict to create a pydantic model.
    """

    # If you work with PostgreSQL, you can consider using
    # sqlalchemy.dialects.postgresql.JSONB instead of a
    # generic sa.types.JSON
    #
    # Ref: https://www.postgresql.org/docs/13/datatype-json.html
    impl = sqlalchemy.types.JSON

    def __init__(self, pydantic_type):
        super().__init__()
        self.pydantic_type = pydantic_type

    def load_dialect_impl(self, dialect):
        # Use JSONB for PostgreSQL and JSON for other databases.
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(sqlalchemy.JSON())

    def process_bind_param(self, value, dialect):
        return jsonable_encoder(value) if value else None

    def process_result_value(self, value, dialect):
        if self.pydantic_type and value:
            return self.pydantic_type.model_validate(value)

        return None


class PluginInfo(BaseModel):
    id: str | None = None  # Get's set after the class is loaded from the yaml file
    name: str
    authors: list[EmpireAuthor] = []
    readme: str | None = ""
    software: str | None = ""
    techniques: list[str] | None = []
    tactics: list[str] | None = []
    auto_start: bool = True
    auto_execute: PluginAutoExecuteConfig | None = None
    main: str
    python_deps: list[str] | None = []


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Sequence("user_id_seq"), primary_key=True)
    # Indexed for the per-request login lookup in jwt_auth.get_user
    # and user_service.get_by_name.
    username: Mapped[str] = mapped_column(String(255), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    api_token: Mapped[str | None] = mapped_column(String(50))
    enabled: Mapped[bool]
    admin: Mapped[bool]
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )
    avatar: Mapped["Download | None"] = relationship()
    avatar_id: Mapped[int | None] = mapped_column(ForeignKey("downloads.id"))

    def __repr__(self):
        return f"<User(username='{self.username}')>"


class Listener(Base):
    __tablename__ = "listeners"
    id: Mapped[int] = mapped_column(Sequence("listener_id_seq"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    module: Mapped[str] = mapped_column(String(255))
    listener_type: Mapped[str | None] = mapped_column(String(255))
    listener_category: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool]
    host_address: Mapped[str | None] = mapped_column(String(255))
    options: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    tags: Mapped[list["Tag"]] = relationship(secondary=listener_tag_assc)
    autorun_tasks: Mapped[list | None] = mapped_column(JSON)

    def __repr__(self):
        return f"<Listener(name='{self.name}')>"


class Host(Base):
    __tablename__ = "hosts"
    id: Mapped[int] = mapped_column(Sequence("host_id_seq"), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    internal_ip: Mapped[str | None] = mapped_column(Text)

    # unique check handled differently in mysql and sqlite
    # In base.py, a unique constraint is added for sqlite
    # and a generated column is added for mysql


class AgentCheckIn(Base):
    """
    Agents check in periodically. Every time they do, a new AgentCheckIn is created.
    This is used to calculate the stale status of an agent and is used to
    """

    __tablename__ = "agent_checkins"
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    checkin_time: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), index=True, primary_key=True
    )


class Agent(Base):
    __tablename__ = "agents"
    # Covers AgentService.get_for_listener (listener + archived filter,
    # called on every per-listener active-agents fetch).
    __table_args__ = (Index("ix_agents_listener_archived", "listener", "archived"),)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    host_id: Mapped[int | None] = mapped_column(ForeignKey("hosts.id"))
    # `host` defaults to lazy="select"; the hot path
    # (agent_communication_service) only reads `agent.host_id` and never
    # the `.host` object, so the previous `lazy="joined"` was wasting a
    # LEFT JOIN on every Agent PK lookup. Where the host object IS
    # needed (e.g. agent task DTO), the caller adds an explicit
    # `joinedload(Agent.host)`.
    host: Mapped["Host | None"] = relationship()
    listener: Mapped[str] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(255))
    language_version: Mapped[str | None] = mapped_column(String(255))
    delay: Mapped[int | None]
    jitter: Mapped[float | None]
    external_ip: Mapped[str | None] = mapped_column(String(255))
    internal_ip: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    high_integrity: Mapped[bool | None]
    process_name: Mapped[str | None] = mapped_column(Text)
    process_id: Mapped[int | None]
    hostname: Mapped[str | None] = mapped_column(String(255))
    os_details: Mapped[str | None] = mapped_column(String(255))
    session_key: Mapped[str | None] = mapped_column(String(255))
    nonce: Mapped[str | None] = mapped_column(String(255))
    firstseen_time: Mapped[datetime | None] = mapped_column(
        UtcDateTime, default=utcnow()
    )
    checkins: Mapped[list[AgentCheckIn]] = relationship(
        "AgentCheckIn",
        order_by="desc(AgentCheckIn.checkin_time)",
        lazy="dynamic",
        cascade="all, delete",
    )
    parent: Mapped[str | None] = mapped_column(String(255))
    children: Mapped[str | None] = mapped_column(String(255))
    servers: Mapped[str | None] = mapped_column(String(255))
    profile: Mapped[str | None] = mapped_column(Text)
    functions: Mapped[str | None] = mapped_column(String(255))
    kill_date: Mapped[str | None] = mapped_column(String(255))
    working_hours: Mapped[str | None] = mapped_column(String(255))
    lost_limit: Mapped[int | None]
    notes: Mapped[str | None] = mapped_column(Text)
    architecture: Mapped[str | None] = mapped_column(String(255))
    archived: Mapped[bool]
    socks: Mapped[bool | None]
    socks_port: Mapped[int | None]
    tags: Mapped[list["Tag"]] = relationship(secondary=agent_tag_assc)

    @hybrid_property
    def lastseen_time(self):
        return self.checkins[0].checkin_time

    #  https://stackoverflow.com/questions/72096054/sqlalchemy-limit-the-joinedloaded-results
    @lastseen_time.inplace.expression
    @classmethod
    def _lastseen_time_expression(cls):
        return (
            select(AgentCheckIn.checkin_time)
            .filter(AgentCheckIn.agent_id == cls.session_id)
            .order_by(AgentCheckIn.checkin_time.desc())
            .limit(1)
            .label("lastseen_time")
        )

    @hybrid_property
    def stale(self):
        return is_stale(self.lastseen_time, self.delay, self.jitter)

    @stale.inplace.expression
    @classmethod
    def _stale_expression(cls):
        if get_database_config()[0] == "sqlite":
            threshold = 30 + cls.delay + cls.delay * cls.jitter
            seconds_elapsed = (
                func.julianday(utcnow()) - func.julianday(cls.lastseen_time)
            ) * 86400.0
            return seconds_elapsed > threshold

        diff = func.timestampdiff(
            text("SECOND"), cls.lastseen_time, func.utc_timestamp()
        )
        threshold = 30 + cls.delay + cls.delay * cls.jitter
        return diff > threshold

    def __repr__(self):
        return f"<Agent(name='{self.name}')>"

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value


class AgentFile(Base):
    __tablename__ = "agent_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Indexed for AgentFileService / AgentCommunicationService lookups
    # by agent session_id (file-tree navigation + download wiring).
    session_id: Mapped[str | None] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    is_file: Mapped[bool]
    # Indexed for the parent_id == ? child-listing filter in
    # agent_file_service / agent_communication_service.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_files.id", ondelete="CASCADE"), index=True
    )
    downloads: Mapped[list["Download"]] = relationship(
        secondary=agent_file_download_assc
    )


class HostProcess(Base):
    __tablename__ = "host_processes"
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id"), primary_key=True)
    process_id: Mapped[int] = mapped_column(primary_key=True)
    process_name: Mapped[str | None] = mapped_column(Text)
    architecture: Mapped[str | None] = mapped_column(String(255))
    user: Mapped[str | None] = mapped_column(String(255))
    stale: Mapped[bool | None] = mapped_column(default=False)
    agent: Mapped["Agent | None"] = relationship(
        lazy="joined",
        primaryjoin="and_(Agent.process_id==foreign(HostProcess.process_id), Agent.host_id==foreign(HostProcess.host_id), Agent.archived == False)",
    )


class Config(Base):
    __tablename__ = "config"
    staging_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    jwt_secret_key: Mapped[str] = mapped_column(Text)
    ip_filtering: Mapped[bool]

    def __repr__(self):
        return f"<Config(staging_key='{self.staging_key}')>"

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value


class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[int] = mapped_column(Sequence("credential_id_seq"), primary_key=True)
    credtype: Mapped[str | None] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    password: Mapped[str | None] = mapped_column(Text)
    host: Mapped[str | None] = mapped_column(Text)
    os: Mapped[str | None] = mapped_column(String(255))
    sid: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=credential_tag_assc)

    def __repr__(self):
        return f"<Credential(id='{self.id}')>"

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value


class Download(Base):
    __tablename__ = "downloads"
    id: Mapped[int] = mapped_column(Sequence("download_seq"), primary_key=True)
    location: Mapped[str] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(Text)
    size: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=download_tag_assc)

    def get_base64_file(self):
        return base64.b64encode(self.get_bytes_file()).decode("utf-8")

    def get_bytes_file(self):
        return Path(self.location).read_bytes()


class AgentTaskStatus(enum.StrEnum):
    queued = "queued"
    pulled = "pulled"
    completed = "completed"
    error = "error"
    continuous = "continuous"


class AgentTask(Base):
    __tablename__ = "agent_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    agent: Mapped["Agent"] = relationship(lazy="joined", innerjoin=True)
    input: Mapped[str | None] = mapped_column(Text)
    input_full: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql.LONGTEXT, "mysql"), deferred=True
    )
    output: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql.LONGTEXT, "mysql"), deferred=True
    )
    # In most cases, this isn't needed and will match output.
    #  However, with the filter feature, we want to store
    # a copy of the original output if it gets modified by a filter.
    original_output: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql.LONGTEXT, "mysql"), deferred=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    user: Mapped["User | None"] = relationship()
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )
    module_name: Mapped[str | None] = mapped_column(Text)
    module_options: Mapped[dict | None] = mapped_column(JSON)
    task_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AgentTaskStatus | None] = mapped_column(
        Enum(AgentTaskStatus), index=True
    )
    downloads: Mapped[list["Download"]] = relationship(
        secondary=agent_task_download_assc
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=agent_task_tag_assc)

    def __repr__(self):
        return f"<AgentTask(id='{self.id}')>"

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value


class Plugin(Base):
    __tablename__ = "plugins"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool]
    settings: Mapped[dict | None] = mapped_column(JSON)
    settings_initialized: Mapped[bool] = mapped_column(default=False)
    internal_state: Mapped[dict | None] = mapped_column(JSON)
    info: Mapped[PluginInfo] = mapped_column(PydanticType(PluginInfo))
    load_error: Mapped[str | None] = mapped_column(Text)
    installed_version: Mapped[str] = mapped_column(String(255), default="unknown")


class PluginTaskStatus(enum.StrEnum):
    queued = "queued"
    started = "started"
    completed = "completed"
    error = "error"
    continuous = "continuous"


class PluginTask(Base):
    __tablename__ = "plugin_tasks"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id"))
    input: Mapped[str | None] = mapped_column(Text)
    input_full: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql.LONGTEXT, "mysql"), deferred=True
    )
    output: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql.LONGTEXT, "mysql"), deferred=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    user: Mapped["User | None"] = relationship()
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )
    plugin_options: Mapped[dict | None] = mapped_column(JSON)
    task_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PluginTaskStatus | None] = mapped_column(
        Enum(PluginTaskStatus), index=True
    )
    downloads: Mapped[list["Download"]] = relationship(
        secondary=plugin_task_download_assc
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=plugin_task_tag_assc)

    def __repr__(self):
        return f"<PluginTask(id='{self.id}')>"


class PluginRegistry(Base):
    __tablename__ = "plugin_registry"
    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    location: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON)


class Keyword(Base):
    __tablename__ = "keywords"
    id: Mapped[int] = mapped_column(Sequence("keyword_seq"), primary_key=True)
    keyword: Mapped[str | None] = mapped_column(String(255), unique=True)
    replacement: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )

    def __repr__(self):
        return f"<KeywordReplacement(id='{self.id}')>"


class Module(Base):
    __tablename__ = "modules"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool]
    technique: Mapped[list | None] = mapped_column(JSON)
    tactic: Mapped[list | None] = mapped_column(JSON)
    software: Mapped[list | None] = mapped_column(JSON)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(Sequence("profile_seq"), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), unique=True)
    file_path: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )


class Bypass(Base):
    __tablename__ = "bypasses"
    id: Mapped[int] = mapped_column(Sequence("bypass_seq"), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), unique=True)
    authors: Mapped[list | None] = mapped_column(JSON)
    code: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )


class Stager(Base):
    __tablename__ = "stagers"
    id: Mapped[int] = mapped_column(Sequence("stager_seq"), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), unique=True)
    module: Mapped[str | None] = mapped_column(String(255))
    options: Mapped[dict | None] = mapped_column(JSON)
    downloads: Mapped[list["Download"]] = relationship(secondary=stager_download_assc)
    one_liner: Mapped[bool | None]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow(), onupdate=utcnow()
    )


class ObfuscationConfig(Base):
    __tablename__ = "obfuscation_config"
    language: Mapped[str] = mapped_column(String(255), primary_key=True)
    command: Mapped[str | None] = mapped_column(Text)
    module: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool | None]
    preobfuscatable: Mapped[bool | None]


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(Sequence("tag_seq"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(String(255))
    color: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, onupdate=utcnow(), default=utcnow()
    )


class IpList(enum.StrEnum):
    allow = "allow"
    deny = "deny"


class IP(Base):
    __tablename__ = "ips"
    id: Mapped[int] = mapped_column(Sequence("ip_seq"), primary_key=True)
    ip_address: Mapped[str] = mapped_column(String(255))
    list: Mapped[IpList] = mapped_column(Enum(IpList))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, onupdate=utcnow(), default=utcnow()
    )
