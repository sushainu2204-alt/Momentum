# backend/models.py
"""
Domain Models - Backward Compatibility Re-export

This module re-exports models from backend.core.models for backward compatibility.
New code should import directly from backend.core.models.

Example:
    # Preferred (new code)
    from backend.core.models import Signal, Candidate, Position
    
    # Backward compatible (existing code)
    from backend.models import Signal, Candidate, Position
"""

# Re-export all models from the new location
from backend.core.models import (
    # Enums
    SignalType,
    PositionStatus,
    OrderStatus,
    OrderType,
    # Models
    Signal,
    Candidate,
    Position,
    AccessData,
)

__all__ = [
    # Enums
    "SignalType",
    "PositionStatus",
    "OrderStatus",
    "OrderType",
    # Models
    "Signal",
    "Candidate",
    "Position",
    "AccessData",
]
