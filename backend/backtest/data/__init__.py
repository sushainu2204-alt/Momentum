"""
Backtest Data Module

Historical data downloading and management for backtesting.
"""

from .downloader import (
    HistoricalDataDownloader,
    DataDownloadConfig,
    DownloadResult,
    DataInterval,
    DataSource
)
from .nse_downloader import NSEHistoricalDownloader
from .kite_downloader import KiteHistoricalDownloader
from .data_manager import DataManager

__all__ = [
    'HistoricalDataDownloader',
    'DataDownloadConfig',
    'DownloadResult',
    'DataInterval',
    'DataSource',
    'NSEHistoricalDownloader',
    'KiteHistoricalDownloader',
    'DataManager'
]
