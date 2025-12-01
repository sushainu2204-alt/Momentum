"""
Database Abstraction
Defines interface for database operations.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class IDatabase(ABC):
    """Interface for database operations"""
    
    @abstractmethod
    async def connect(self):
        """Connect to database"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from database"""
        pass
    
    @abstractmethod
    async def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """Execute a query"""
        pass
    
    @abstractmethod
    async def fetch_one(self, query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch single record"""
        pass
    
    @abstractmethod
    async def fetch_all(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Fetch all records"""
        pass
    
    @abstractmethod
    async def insert(self, table: str, data: Dict) -> Any:
        """Insert record"""
        pass
    
    @abstractmethod
    async def update(self, table: str, data: Dict, where: Dict) -> Any:
        """Update record"""
        pass
    
    @abstractmethod
    async def delete(self, table: str, where: Dict) -> Any:
        """Delete record"""
        pass
