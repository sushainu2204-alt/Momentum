"""
Trading signal model

This is the canonical Signal model used throughout the system.
Re-exports from backend.models for backwards compatibility.
"""
from backend.models import Signal, SignalType

__all__ = ["Signal", "SignalType"]
