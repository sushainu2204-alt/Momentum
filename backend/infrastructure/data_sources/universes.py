"""
Stock Universe Implementations

Pluggable universe definitions for different stock sets.
Loads from CSV files with hardcoded fallbacks.
"""

from typing import List
import os
import csv
from pathlib import Path
from .base import IStockUniverse, IDataSource, Instrument


class FnOUniverse(IStockUniverse):
    """
    F&O (Futures & Options) stocks universe.
    
    Most liquid stocks (~150), best for intraday strategies.
    Loads from CSV file with hardcoded fallback.
    """
    
    # Hardcoded fallback list (Top 150 F&O stocks as of Nov 2024)
    FNO_SYMBOLS_FALLBACK = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR", "ICICIBANK", 
        "KOTAKBANK", "SBIN", "BHARTIARTL", "ITC", "AXISBANK", "LT", 
        "BAJFINANCE", "ASIANPAINT", "MARUTI", "HCLTECH", "SUNPHARMA", 
        "ULTRACEMCO", "TITAN", "NESTLEIND", "WIPRO", "M&M", "BAJAJFINSV",
        "TATAMOTORS", "ONGC", "TECHM", "POWERGRID", "NTPC", "COALINDIA",
        "JSWSTEEL", "TATASTEEL", "ADANIENT", "HINDALCO", "DIVISLAB",
        "INDUSINDBK", "BAJAJ-AUTO", "DRREDDY", "EICHERMOT", "BRITANNIA",
        "APOLLOHOSP", "TATACONSUM", "CIPLA", "GRASIM", "HDFCLIFE", "SBILIFE",
        "BPCL", "LTIM", "IOC", "ADANIPORTS", "HEROMOTOCO", "UPL", "TRENT",
        "HAVELLS", "MCDOWELL-N", "AMBUJACEM", "ADANITRANS", "GODREJCP",
        "DABUR", "SIEMENS", "INDIGO", "BANDHANBNK", "ICICIGI", "PIIND",
        "ATGL", "ADANIGREEN", "ADANIPOWER", "BERGEPAINT", "COLPAL", "MARICO",
        "BOSCHLTD", "LUPIN", "VEDL", "DLF", "GAIL", "PEL", "SHREECEM",
        "NAUKRI", "ZOMATO", "BANKBARODA", "PNB", "CANBK", "UNIONBANK",
        "IDFCFIRSTB", "PAGEIND", "ACC", "TORNTPHARM", "ZYDUSLIFE", "CHOLAFIN",
        "SBICARD", "MUTHOOTFIN", "PFC", "RECLTD", "TATAPOWER", "PETRONET",
        "INDHOTEL", "ABB", "ESCORTS", "AUROPHARMA", "ALKEM", "INDUSTOWER",
        "MOTHERSON", "CONCOR", "HINDPETRO", "ASTRAL", "ABCAPITAL", "SAIL",
        "NMDC", "BEL", "HAL", "CUMMINSIND", "JINDALSTEL", "NATIONALUM",
        "VOLTAS", "IDEA", "IBULHSGFIN", "LICI", "IRCTC", "PERSISTENT",
        "COFORGE", "MPHASIS", "LTTS", "L&TFH", "POLYCAB", "DMART", "DIXON",
        "APLAPOLLO", "FEDERALBNK", "AUBANK", "IPCALAB", "BIOCON", "GLAND",
        "LALPATHLAB", "METROPOLIS", "FORTIS", "MAXHEALTH", "SYNGENE",
        "ABBOTINDIA", "PFIZER", "GLAXO", "MANAPPURAM", "BAJAJHLDNG", "SUNTV",
        "JUBLFOOD", "TATACOMM", "CROMPTON", "WHIRLPOOL", "BALKRISIND"
    ]
    
    def _load_symbols_from_csv(self) -> List[str]:
        """Load symbols from CSV file"""
        try:
            # Get path relative to this file
            current_dir = Path(__file__).parent.parent.parent
            csv_path = current_dir / "data" / "universes" / "fno_stocks.csv"
            
            # TODO: why do we need fallback? Why isnt file fetched properly?
            if not csv_path.exists():
                return self.FNO_SYMBOLS_FALLBACK
            
            symbols = []
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get('symbol', '').strip()
                    if symbol:
                        symbols.append(symbol)
            
            return symbols if symbols else self.FNO_SYMBOLS_FALLBACK
            
        except Exception as e:
            print(f"⚠️  Error loading F&O CSV: {e}, using fallback list")
            return self.FNO_SYMBOLS_FALLBACK
    
    def get_instruments(self, data_source: IDataSource) -> List[Instrument]:
        """Get F&O stocks from CSV/fallback list"""
        symbols = self._load_symbols_from_csv()
        all_instruments = data_source.get_instruments(exchange="NSE")
        
        fno_stocks = [
            inst for inst in all_instruments
            if inst.segment == "NSE" 
            and inst.instrument_type == "EQ"
            and inst.tradingsymbol in symbols
        ]
        
        return fno_stocks
    
    def get_name(self) -> str:
        return "F&O Universe (~150 stocks)"


class Nifty500Universe(IStockUniverse):
    """
    Nifty 500 index constituents.
    
    Broader universe, includes mid and small caps.
    Loads from CSV file with hardcoded fallback.
    """
    
    # Hardcoded fallback list (Top 150 liquid stocks from Nifty 500)
    NIFTY_500_SYMBOLS_FALLBACK = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR",
        "ICICIBANK", "KOTAKBANK", "SBIN", "BHARTIARTL", "ITC",
        "AXISBANK", "LT", "BAJFINANCE", "ASIANPAINT", "MARUTI",
        "HCLTECH", "SUNPHARMA", "ULTRACEMCO", "TITAN", "NESTLEIND",
        "WIPRO", "M&M", "BAJAJFINSV", "TATAMOTORS", "ONGC",
        "TECHM", "POWERGRID", "NTPC", "COALINDIA", "JSWSTEEL",
        "TATASTEEL", "ADANIENT", "HINDALCO", "DIVISLAB", "INDUSINDBK",
        "BAJAJ-AUTO", "DRREDDY", "EICHERMOT", "BRITANNIA", "APOLLOHOSP",
        "TATACONSUM", "CIPLA", "GRASIM", "HDFCLIFE", "SBILIFE",
        "BPCL", "LTIM", "IOC", "ADANIPORTS", "HEROMOTOCO",
        "UPL", "TRENT", "HAVELLS", "MCDOWELL-N", "AMBUJACEM",
        "ADANITRANS", "GODREJCP", "DABUR", "SIEMENS", "INDIGO",
        "BANDHANBNK", "ICICIGI", "PIIND", "ATGL", "ADANIGREEN",
        "ADANIPOWER", "BERGEPAINT", "COLPAL", "MARICO", "BOSCHLTD",
        "LUPIN", "VEDL", "DLF", "GAIL", "PEL",
        "SHREECEM", "NAUKRI", "ZOMATO", "BANKBARODA", "PNB",
        "CANBK", "UNIONBANK", "IDFCFIRSTB", "PAGEIND", "ACC",
        "TORNTPHARM", "ZYDUSLIFE", "CHOLAFIN", "SBICARD", "MUTHOOTFIN",
        "PFC", "RECLTD", "TATAPOWER", "PETRONET", "INDHOTEL",
        "ABB", "ESCORTS", "AUROPHARMA", "ALKEM", "INDUSTOWER",
        "MOTHERSON", "CONCOR", "HINDPETRO", "ASTRAL", "ABCAPITAL",
        "SAIL", "NMDC", "BEL", "HAL", "CUMMINSIND",
        "JINDALSTEL", "NATIONALUM", "VOLTAS", "IDEA", "IBULHSGFIN",
        "LICI", "IRCTC", "PERSISTENT", "COFORGE", "MPHASIS",
        "LTTS", "L&TFH", "POLYCAB", "DMART", "DIXON",
        "APLAPOLLO", "FEDERALBNK", "AUBANK", "IPCALAB", "BIOCON",
        "GLAND", "LALPATHLAB", "METROPOLIS", "FORTIS", "MAXHEALTH",
        "SYNGENE", "ABBOTINDIA", "PFIZER", "GLAXO", "MANAPPURAM",
        "BAJAJHLDNG", "SUNTV", "JUBLFOOD", "TATACOMM", "CROMPTON",
        "WHIRLPOOL", "BALKRISIND"
    ]
    
    def _load_symbols_from_csv(self) -> List[str]:
        """Load symbols from CSV file"""
        try:
            current_dir = Path(__file__).parent.parent.parent
            csv_path = current_dir / "data" / "universes" / "nifty500_stocks.csv"
            
            if not csv_path.exists():
                return self.NIFTY_500_SYMBOLS_FALLBACK
            
            symbols = []
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get('symbol', '').strip()
                    if symbol:
                        symbols.append(symbol)
            
            return symbols if symbols else self.NIFTY_500_SYMBOLS_FALLBACK
            
        except Exception as e:
            print(f"⚠️  Error loading Nifty 500 CSV: {e}, using fallback list")
            return self.NIFTY_500_SYMBOLS_FALLBACK
    
    def get_instruments(self, data_source: IDataSource) -> List[Instrument]:
        """Get Nifty 500 constituent instruments"""
        symbols = self._load_symbols_from_csv()
        all_instruments = data_source.get_instruments(exchange="NSE")
        
        nifty_500 = [
            inst for inst in all_instruments
            if inst.segment == "NSE"
            and inst.instrument_type == "EQ"
            and inst.tradingsymbol in symbols
        ]
        
        return nifty_500
    
    def get_name(self) -> str:
        return "Nifty 500 Universe"


class Nifty200Universe(IStockUniverse):
    """
    Nifty 200 index constituents.
    
    Large and mid cap stocks.
    Uses same list as Nifty 500 (subset).
    """
    
    # For now, use same as Nifty 500 (they're very similar)
    # You can create separate nifty200_stocks.csv if needed
    
    def get_instruments(self, data_source: IDataSource) -> List[Instrument]:
        """Get Nifty 200 constituent instruments"""
        # Reuse Nifty 500 logic for now
        nifty500 = Nifty500Universe()
        return nifty500.get_instruments(data_source)
    
    def get_name(self) -> str:
        return "Nifty 200 Universe"


class CustomUniverse(IStockUniverse):
    """
    User-defined stock universe.
    
    Usage:
        universe = CustomUniverse(["RELIANCE", "TCS", "INFY"])
    """
    
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
    
    def get_instruments(self, data_source: IDataSource) -> List[Instrument]:
        """Get instruments for specified symbols"""
        all_instruments = data_source.get_instruments(exchange="NSE")
        
        custom_stocks = [
            inst for inst in all_instruments
            if inst.segment == "NSE"
            and inst.instrument_type == "EQ"
            and inst.tradingsymbol in self.symbols
        ]
        
        return custom_stocks
    
    def get_name(self) -> str:
        return f"Custom Universe ({len(self.symbols)} stocks)"
