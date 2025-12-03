"""
Application settings and configuration.
Uses pydantic-settings for type-safe environment variable loading.
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings"""
    
    # Kite Connect API
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_API_SECRET: str = os.getenv("KITE_API_SECRET", "")
    KITE_REDIRECT_URL: str = os.getenv("KITE_REDIRECT_URL", "http://localhost:8000/callback")
    KITE_ACCESS_TOKEN: Optional[str] = os.getenv("KITE_ACCESS_TOKEN")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://appuser:secret@localhost:5432/appdb")
    
    # Redis Channels
    SIGNALS_CHANNEL: str = "signals"
    
    # Strategy defaults
    DEFAULT_FAST_EMA: int = 9
    DEFAULT_SLOW_EMA: int = 21
    DEFAULT_BUFFER_SIZE: int = 200
    
    # Backtesting defaults
    DEFAULT_INITIAL_CAPITAL: float = 100000.0
    DEFAULT_COMMISSION: float = 0.0003  # 0.03%
    DEFAULT_SLIPPAGE: float = 0.0001  # 0.01%
    DEFAULT_POSITION_SIZE: float = 0.95  # 95% of capital
    
    def update_access_token(self, token: str):
        """Update access token in memory and .env file"""
        self.KITE_ACCESS_TOKEN = token
        
        # Update .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
        else:
            lines = []
        
        token_found = False
        for i, line in enumerate(lines):
            if line.strip().startswith("KITE_ACCESS_TOKEN="):
                lines[i] = f"KITE_ACCESS_TOKEN={token}\n"
                token_found = True
                break
        
        if not token_found:
            lines.append(f"KITE_ACCESS_TOKEN={token}\n")
        
        with open(env_path, "w") as f:
            f.writelines(lines)


# Global settings instance
settings = Settings()
