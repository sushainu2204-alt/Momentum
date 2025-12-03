"""
API Models

Pydantic models for API request/response validation.
"""
from typing import Optional
from pydantic import BaseModel


class AccessData(BaseModel):
    """
    Zerodha OAuth access data from Kite authentication.
    
    Used for storing and validating Kite API credentials.
    
    Attributes:
        access_token: Kite API access token
        public_token: Public token (optional)
        user_id: User ID (optional)
    """
    access_token: str
    public_token: Optional[str] = None
    user_id: Optional[str] = None
