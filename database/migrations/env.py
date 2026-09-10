from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# logging.config.fileConfig is not always available in frozen PyInstaller
# builds (Python 3.13 restructured the logging package).  Guard the import
# so the app doesn't crash on startup when running as an EXE.
try:
    from logging.config import fileConfig as _fileConfig
    _HAS_FILE_CONFIG = True
except ImportError:
    _HAS_FILE_CONFIG = False

# Make the project root importable so `import app...` works when Alembic
# is invoked from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings  # noqa: E402
from app.models import Base  # noqa: E402  (imports every model)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# Only apply file-based logging config when the ini file exists AND
# logging.config is available (not always the case in frozen builds).
if _HAS_FILE_CONFIG and config.config_file_name is not None:
    try:
        _fileConfig(config.config_file_name)
    except Exception:
        pass  # Never crash the app over a logging-config failure

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
