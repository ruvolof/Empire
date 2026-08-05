import fnmatch
import logging
import typing

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class ProfileService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu

        with SessionLocal.begin() as db:
            self.load_malleable_profiles(db)

    def load_malleable_profiles(self, db: Session):
        """
        Load Malleable C2 Profiles to the database
        """
        malleable_path = self.main_menu.install_path / "data/profiles"
        log.info(f"v2: Loading malleable profiles from: {malleable_path}")

        # Pre-load existing profile names once instead of issuing a
        # SELECT per file (mirrors module_service.load_modules).
        db_existing_names = set(db.scalars(select(models.Profile.name)).all())
        added_in_loop: dict[str, str] = {}

        for file_path in malleable_path.rglob("*.profile"):
            filename = file_path.name

            # don't load up any of the templates
            if fnmatch.fnmatch(filename, "*template.profile"):
                continue

            malleable_split = file_path.relative_to(malleable_path).parts
            profile_category = malleable_split[0]
            profile_name = malleable_split[1]

            if profile_name in db_existing_names:
                continue
            if profile_name in added_in_loop:
                log.warning(
                    "Duplicate malleable profile name %r at %s; keeping first occurrence at %s",
                    profile_name,
                    file_path,
                    added_in_loop[profile_name],
                )
                continue

            log.debug(f"Adding malleable profile: {profile_name}")
            profile_data = file_path.read_text()
            db.add(
                models.Profile(
                    file_path=str(file_path),
                    name=profile_name,
                    category=profile_category,
                    data=profile_data,
                )
            )
            added_in_loop[profile_name] = str(file_path)

    @staticmethod
    def get_all(db: Session):
        return db.scalars(select(models.Profile)).all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.scalars(
            select(models.Profile).where(models.Profile.id == uid)
        ).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        return db.scalars(
            select(models.Profile).where(models.Profile.name == name)
        ).first()

    @staticmethod
    def delete_profile(db: Session, profile: models.Profile):
        db.delete(profile)

    def create_profile(self, db: Session, profile_req):
        if self.get_by_name(db, profile_req.name):
            return (
                None,
                f"Malleable Profile with name {profile_req.name} already exists.",
            )

        profile = models.Profile(
            name=profile_req.name, category=profile_req.category, data=profile_req.data
        )

        db.add(profile)
        db.flush()

        return profile, None

    @staticmethod
    def update_profile(db: Session, db_profile: models.Profile, profile_req):
        db_profile.data = profile_req.data
        db.flush()

        return db_profile, None

    @staticmethod
    def delete_all_profiles(db: Session):
        db.execute(delete(models.Profile))
        db.flush()
