import logging
import typing

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.api.v2.tag.tag_dto import TagOrderOptions, TagSourceFilter
from empire.server.core.db import models
from empire.server.core.hooks import hooks

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu


log = logging.getLogger(__name__)

Taggable = (
    models.Listener
    | models.Agent
    | models.AgentTask
    | models.PluginTask
    | models.Credential
    | models.Download
)


class TagService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu

    def get_by_id(self, db: Session, tag_id: int):
        return db.scalars(select(models.Tag).where(models.Tag.id == tag_id)).first()

    def get_all(  # noqa: PLR0913 PLR0912
        self,
        db: Session,
        tag_types: list[TagSourceFilter] | None,
        q: str,
        limit: int = -1,
        offset: int = 0,
        order_by: TagOrderOptions = TagOrderOptions.updated_at,
        order_direction: OrderDirection = OrderDirection.desc,
    ):
        stmt = select(models.Tag, func.count(models.Tag.id).over().label("total"))

        tag_types = tag_types or []
        sub = []
        if TagSourceFilter.agent_task in tag_types:
            sub.append(select(models.agent_task_tag_assc.c.tag_id.label("tag_id")))
        if TagSourceFilter.plugin_task in tag_types:
            sub.append(select(models.plugin_task_tag_assc.c.tag_id.label("tag_id")))
        if TagSourceFilter.agent in tag_types:
            sub.append(select(models.agent_tag_assc.c.tag_id.label("tag_id")))
        if TagSourceFilter.listener in tag_types:
            sub.append(select(models.listener_tag_assc.c.tag_id.label("tag_id")))
        if TagSourceFilter.download in tag_types:
            sub.append(select(models.download_tag_assc.c.tag_id.label("tag_id")))
        if TagSourceFilter.credential in tag_types:
            sub.append(select(models.credential_tag_assc.c.tag_id.label("tag_id")))

        subquery = None
        if sub:
            subquery = sub[0]
            if len(sub) > 1:
                subquery = subquery.union(*sub[1:])
            subquery = subquery.subquery()

        if subquery is not None:
            stmt = stmt.join(subquery, subquery.c.tag_id == models.Tag.id)

        if q:
            stmt = stmt.where(
                or_(
                    models.Tag.name.like(f"%{q}%"),
                )
            )

        if order_by == TagOrderOptions.name:
            order_by_prop = func.lower(models.Tag.name)
        elif order_by == TagOrderOptions.created_at:
            order_by_prop = models.Tag.created_at
        else:
            order_by_prop = models.Tag.updated_at

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

    def add_tag(
        self,
        db: Session,
        taggable: Taggable,
        name: str,
        value: str,
        color: str | None = None,
    ):
        tag = models.Tag(name=name, value=value, color=color)
        taggable.tags.append(tag)
        db.flush()

        hooks.run_hooks(hooks.AFTER_TAG_CREATED_HOOK, db, tag, taggable)

        return tag

    def update_tag(
        self,
        db: Session,
        db_tag: models.Tag,
        taggable: Taggable,
        tag_req,
    ):
        db_tag.name = tag_req.name
        db_tag.value = tag_req.value
        db_tag.color = tag_req.color
        db.flush()

        hooks.run_hooks(hooks.AFTER_TAG_UPDATED_HOOK, db, db_tag, taggable)

        return db_tag

    def delete_tag(
        self,
        db: Session,
        taggable: Taggable,
        tag_id: int,
    ):
        if tag_id in [tag.id for tag in taggable.tags]:
            taggable.tags = [tag for tag in taggable.tags if tag.id != tag_id]
            db.execute(delete(models.Tag).where(models.Tag.id == tag_id))
