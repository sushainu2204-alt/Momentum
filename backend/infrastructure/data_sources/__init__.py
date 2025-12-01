"""Data source abstractions and implementations"""

from .base import (
    IDataSource,
    IStockUniverse,
    IStockScreener,
    Quote,
    Instrument
)
from .zerodha import ZerodhaDataSource
from .nse import NSEDataSource, NSETopGainer
from .universes import (
    FnOUniverse,
    Nifty500Universe,
    Nifty200Universe,
    CustomUniverse
)

__all__ = [
    'IDataSource',
    'IStockUniverse',
    'IStockScreener',
    'Quote',
    'Instrument',
    'ZerodhaDataSource',
    'NSEDataSource',
    'NSETopGainer',
    'FnOUniverse',
    'Nifty500Universe',
    'Nifty200Universe',
    'CustomUniverse',
]
