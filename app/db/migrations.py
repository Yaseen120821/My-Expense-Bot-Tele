"""
Database migration utilities.
For production, use Alembic. This module provides a convenience
function for initial schema creation in development.
"""

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.database import init_db, close_db  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


async def run_migrations() -> None:
    """Create all tables defined in the ORM models."""
    logger.info("Running database migrations (create_all)...")
    try:
        await init_db()
        logger.info("Migrations completed successfully.")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        await close_db()


def main() -> None:
    """Entry point for running migrations from CLI: python -m app.db.migrations"""
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
