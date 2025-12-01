"""
Database Factory
Centralized database initialization - use this everywhere!
"""
from urllib.parse import urlparse
from typing import Dict, Any

from .postgres import PostgresDatabase
from backend.config.settings import settings


def get_database_config() -> Dict[str, Any]:
    """
    Parse DATABASE_URL from settings and return config dict.
    
    Returns:
        Database configuration dictionary
    """
    parsed = urlparse(settings.DATABASE_URL)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path[1:],  # Remove leading /
        "user": parsed.username,
        "password": parsed.password
    }


def create_database() -> PostgresDatabase:
    """
    Create and return a PostgresDatabase instance.
    
    Usage:
        db = create_database()
        await db.connect()
    
    Returns:
        Configured PostgresDatabase instance
    """
    config = get_database_config()
    return PostgresDatabase(config)
