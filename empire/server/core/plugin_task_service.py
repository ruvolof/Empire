import logging
import typing
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, undefer

from empire.server.api.v2.plugin.plugin_task_dto import PluginTaskOrderOptions
from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import AgentTaskStatus

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class PluginTaskService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu
        self.plugin_service = main_menu.pluginsv2

    @staticmethod
    def get_tasks(  # noqa: PLR0913 PLR0912
        db: Session,
        plugins: list[str] | None = None,
        users: list[int] | None = None,
        tags: list[str] | None = None,
        limit: int = -1,
        offset: int = 0,
        include_full_input: bool = False,
        include_output: bool = True,
        since: datetime | None = None,
        order_by: PluginTaskOrderOptions = PluginTaskOrderOptions.id,
        order_direction: OrderDirection = OrderDirection.desc,
        status: AgentTaskStatus | None = None,
        q: str | None = None,
    ):
        stmt = select(
            models.PluginTask, func.count(models.PluginTask.id).over().label("total")
        )

        if plugins:
            stmt = stmt.where(models.PluginTask.plugin_id.in_(plugins))

        if users:
            user_filters = [models.PluginTask.user_id.in_(users)]
            if 0 in users:
                user_filters.append(models.PluginTask.user_id.is_(None))
            stmt = stmt.where(or_(*user_filters))

        if tags:
            tags_split = [tag.split(":", 1) for tag in tags]
            stmt = stmt.join(models.PluginTask.tags).where(
                and_(
                    models.Tag.name.in_([tag[0] for tag in tags_split]),
                    models.Tag.value.in_([tag[1] for tag in tags_split]),
                )
            )

        query_options = [
            joinedload(models.PluginTask.user),
        ]

        if include_full_input:
            query_options.append(undefer(models.PluginTask.input_full))
        if include_output:
            query_options.append(undefer(models.PluginTask.output))
        stmt = stmt.options(*query_options)

        if since:
            stmt = stmt.where(models.PluginTask.updated_at > since)

        if status:
            stmt = stmt.where(models.AgentTask.status == status)

        if q:
            stmt = stmt.where(
                or_(
                    models.PluginTask.input.like(f"%{q}%"),
                    models.PluginTask.output.like(f"%{q}%"),
                )
            )

        if order_by == PluginTaskOrderOptions.status:
            order_by_prop = models.PluginTask.status
        elif order_by == PluginTaskOrderOptions.updated_at:
            order_by_prop = models.PluginTask.updated_at
        elif order_by == PluginTaskOrderOptions.plugin:
            order_by_prop = models.PluginTask.plugin_id
        else:
            order_by_prop = models.PluginTask.id

        if order_direction == OrderDirection.asc:
            stmt = stmt.order_by(order_by_prop.asc())
        else:
            stmt = stmt.order_by(order_by_prop.desc())

        if limit > 0:
            stmt = stmt.limit(limit).offset(offset)

        results = db.execute(stmt).all()

        total = 0 if not results else results[0].total
        results = [x[0] for x in results]

        return results, total

    def get_task(self, db: SessionLocal, plugin_id: str, task_id: int):
        # TODO: Check all the uses of get_by_id
        plugin = self.plugin_service.get_by_id(db, plugin_id)
        if plugin:
            task = db.scalars(
                select(models.PluginTask).where(models.PluginTask.id == task_id)
            ).first()
            if task:
                return task

        return None
