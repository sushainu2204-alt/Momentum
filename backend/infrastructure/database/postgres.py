"""
PostgreSQL Database Implementation
Implements IDatabase interface for PostgreSQL.
"""
from typing import Optional, List, Dict, Any
import asyncpg
import logging

from .base import IDatabase

logger = logging.getLogger(__name__)


class PostgresDatabase(IDatabase):
    """
    PostgreSQL implementation of IDatabase interface.
    
    Usage:
        db = PostgresDatabase({
            "host": "localhost",
            "port": 5432,
            "database": "momentum",
            "user": "postgres",
            "password": "password"
        })
        await db.connect()
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize PostgreSQL database connection.
        
        Args:
            config: Database connection config
                - host: Database host
                - port: Database port
                - database: Database name
                - user: Username
                - password: Password
        """
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Connect to PostgreSQL database"""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.config.get("host", "localhost"),
                port=self.config.get("port", 5432),
                database=self.config["database"],
                user=self.config["user"],
                password=self.config["password"],
                min_size=1,
                max_size=10,
                ssl='disable'  # Disable SSL for local Docker connections
            )
            logger.info(f"Connected to PostgreSQL: {self.config['database']}")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from database"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection closed")
    
    async def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute a query without returning results.
        
        Args:
            query: SQL query
            params: Query parameters
        
        Returns:
            Status string
        """
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            if params:
                return await conn.execute(query, *params.values())
            else:
                return await conn.execute(query)
    
    async def fetch_one(self, query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Fetch single record.
        
        Args:
            query: SQL query
            params: Query parameters
        
        Returns:
            Dictionary with column names as keys
        """
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            if params:
                row = await conn.fetchrow(query, *params.values())
            else:
                row = await conn.fetchrow(query)
            
            return dict(row) if row else None
    
    async def fetch_all(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Fetch all records.
        
        Args:
            query: SQL query
            params: Query parameters
        
        Returns:
            List of dictionaries
        """
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            if params:
                rows = await conn.fetch(query, *params.values())
            else:
                rows = await conn.fetch(query)
            
            return [dict(row) for row in rows]
    
    async def insert(self, table: str, data: Dict) -> Any:
        """
        Insert record and return ID.
        
        Args:
            table: Table name
            data: Data to insert
        
        Returns:
            Inserted record ID
        """
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(data)))
        query = f"""
            INSERT INTO {table} ({columns})
            VALUES ({placeholders})
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *data.values())
            return row['id'] if row else None
    
    async def update(self, table: str, data: Dict, where: Dict) -> Any:
        """
        Update records.
        
        Args:
            table: Table name
            data: Data to update
            where: WHERE clause conditions
        
        Returns:
            Number of rows updated
        """
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        set_clause = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(data.keys()))
        where_clause = " AND ".join(
            f"{k} = ${i+len(data)+1}" 
            for i, k in enumerate(where.keys())
        )
        
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *data.values(), *where.values())
            # Parse "UPDATE N" to get row count
            return int(result.split()[-1]) if result else 0
    
    async def delete(self, table: str, where: Dict) -> Any:
        """
        Delete records.
        
        Args:
            table: Table name
            where: WHERE clause conditions
        
        Returns:
            Number of rows deleted
        """
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        where_clause = " AND ".join(f"{k} = ${i+1}" for i, k in enumerate(where.keys()))
        query = f"DELETE FROM {table} WHERE {where_clause}"
        
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *where.values())
            # Parse "DELETE N" to get row count
            return int(result.split()[-1]) if result else 0
