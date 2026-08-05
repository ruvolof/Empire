import typing

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire.server.core.db import models

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu
    from empire.server.core.download_service import DownloadService


class UserService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu
        self.download_service: DownloadService = main_menu.downloadsv2

    @staticmethod
    def get_all(db: Session):
        return db.scalars(select(models.User)).all()

    @staticmethod
    def get_by_id(db: Session, uid: int) -> models.User:
        return db.scalars(select(models.User).where(models.User.id == uid)).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        return db.scalars(
            select(models.User).where(models.User.username == name)
        ).first()

    def create_user(
        self, db: Session, username: str, hashed_password: str, admin: bool = False
    ):
        db_user = self.get_by_name(db, username)

        if db_user:
            return None, f"A user with name {username} already exists."

        user = models.User(
            username=username,
            hashed_password=hashed_password,
            enabled=True,
            admin=admin,
        )

        db.add(user)
        db.flush()

        return user, None

    def update_user(self, db: Session, db_user: models.User, user_req):
        losing_admin_access = (
            db_user.admin
            and db_user.enabled
            and (not user_req.is_admin or not user_req.enabled)
        )
        if losing_admin_access and not _has_other_enabled_admin(db, db_user):
            return None, "Cannot disable or demote the last enabled admin."

        if user_req.username != db_user.username:
            if not self.get_by_name(db, user_req.username):
                db_user.username = user_req.username
            else:
                return None, f"A user with name {user_req.username} already exists."

        db_user.enabled = user_req.enabled
        db_user.admin = user_req.is_admin

        return db_user, None

    @staticmethod
    def update_user_password(db: Session, db_user: models.User, hashed_password: str):
        db_user.hashed_password = hashed_password
        db.flush()

        return db_user, None

    def update_user_avatar(self, db: Session, db_user: models.User, file: UploadFile):
        download = self.download_service.create_download(db, db_user, file)

        db_user.avatar = download


def _has_other_enabled_admin(db: Session, db_user: models.User) -> bool:
    # Best-effort guard: this count and the caller's subsequent mutation are not
    # under a row lock, so two concurrent update_user calls demoting different
    # admins could each pass. Acceptable for an admin-management endpoint; tighten
    # with SELECT ... FOR UPDATE if a hard guarantee is ever required.
    count = db.scalar(
        select(func.count(models.User.id)).where(
            models.User.id != db_user.id,
            models.User.admin.is_(True),
            models.User.enabled.is_(True),
        )
    )
    return count > 0
