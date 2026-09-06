import logging
from pathlib import Path
from typing import Optional
import asyncpg
from server.config import DATABASE_URL, BASE_DIR

logger = logging.getLogger("telemetryvault.db")

pool: Optional[asyncpg.Pool] = None

async def init_db() -> asyncpg.Pool:
    global pool
    if pool is None:
        logger.info("Initializing database connection pool...")
        pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=10)
        await run_migrations()
    return pool

async def close_db():
    global pool
    if pool is not None:
        logger.info("Closing database connection pool...")
        await pool.close()
        pool = None

async def run_migrations():
    """Applies all .sql migration files from migrations/ idempotently."""
    global pool
    if pool is None:
        raise RuntimeError("Database pool not initialized")
    
    migrations_dir = BASE_DIR / "migrations"
    if not migrations_dir.exists():
        logger.warning(f"Migrations directory {migrations_dir} does not exist.")
        return

    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        logger.info("No migration files found.")
        return

    async with pool.acquire() as conn:
        # Ensure schema_migrations table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(64) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        applied_rows = await conn.fetch("SELECT version FROM schema_migrations;")
        applied = {row["version"] for row in applied_rows}

        for file_path in migration_files:
            version = file_path.name
            if version in applied:
                continue
            
            logger.info(f"Applying migration: {version}")
            sql_content = file_path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql_content)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1);",
                    version
                )
            logger.info(f"Migration {version} applied successfully.")

async def get_db_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        return await init_db()
    return pool
