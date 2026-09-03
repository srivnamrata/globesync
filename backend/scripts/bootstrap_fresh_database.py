"""Create and stamp a brand-new GlobeSync database.

This is intentionally for an empty development database only. Historical Alembic
migrations remain the upgrade path for existing databases; this avoids replaying
the legacy metadata-driven initial migration against current ORM models.
"""

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import settings
from app.core.database import Base
from app.models import (  # noqa: F401
    export_job,
    frame_metadata,
    generated_audio,
    identity,
    lipsync_job,
    media,
    project,
    transcript,
    translation,
    voice_profile,
)


def main() -> None:
    engine = create_engine(settings.SYNC_DATABASE_URL, future=True)
    existing_tables = inspect(engine).get_table_names()
    if existing_tables:
        table_list = ", ".join(sorted(existing_tables))
        raise RuntimeError(
            "Refusing to bootstrap a non-empty database. Drop and recreate the disposable "
            f"database first. Existing tables: {table_list}"
        )

    Base.metadata.create_all(bind=engine)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URL)
    command.stamp(config, "head")
    print("Fresh database schema created and stamped at Alembic head.")


if __name__ == "__main__":
    main()
