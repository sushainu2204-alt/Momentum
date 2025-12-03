#!/usr/bin/env python3
"""
Universe List Manager

Utility to help update and manage stock universe lists.

Usage:
    # Test current universes
    python -m backend.scripts.manage_universes test
    
    # Download latest from NSE (requires internet)
    python -m backend.scripts.manage_universes download
    
    # Show stats
    python -m backend.scripts.manage_universes stats
"""

import sys
import csv
from pathlib import Path
from typing import List, Set

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.infrastructure.data_sources import FnOUniverse, Nifty500Universe
from backend.core.services.kite_service import KiteService
from backend.infrastructure.data_sources import ZerodhaDataSource


def test_universes():
    """Test loading universes and show counts"""
    print("\n" + "="*70)
    print("TESTING STOCK UNIVERSES")
    print("="*70)
    
    try:
        # Initialize Kite
        kite_service = KiteService()
        kite = kite_service.kite
        
        if not kite:
            print("❌ Kite not initialized. Run authentication first.")
            return
        
        data_source = ZerodhaDataSource(kite)
        
        # Test F&O Universe
        print("\n📊 F&O Universe:")
        fno = FnOUniverse()
        fno_instruments = fno.get_instruments(data_source)
        print(f"  Loaded: {len(fno_instruments)} stocks")
        print(f"  Sample: {', '.join([i.tradingsymbol for i in fno_instruments[:10]])}")
        
        # Test Nifty 500
        print("\n📊 Nifty 500 Universe:")
        n500 = Nifty500Universe()
        n500_instruments = n500.get_instruments(data_source)
        print(f"  Loaded: {len(n500_instruments)} stocks")
        print(f"  Sample: {', '.join([i.tradingsymbol for i in n500_instruments[:10]])}")
        
        # Compare
        fno_symbols = {i.tradingsymbol for i in fno_instruments}
        n500_symbols = {i.tradingsymbol for i in n500_instruments}
        
        print(f"\n🔍 Overlap Analysis:")
        print(f"  F&O only: {len(fno_symbols - n500_symbols)} stocks")
        print(f"  Nifty 500 only: {len(n500_symbols - fno_symbols)} stocks")
        print(f"  Common: {len(fno_symbols & n500_symbols)} stocks")
        
        print("\n✅ Universe loading successful!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def show_stats():
    """Show universe statistics from CSV files"""
    print("\n" + "="*70)
    print("UNIVERSE STATISTICS")
    print("="*70)
    
    data_dir = Path(__file__).parent.parent.parent / "data" / "universes"
    
    for csv_file in ["fno_stocks.csv", "nifty500_stocks.csv"]:
        csv_path = data_dir / csv_file
        
        if csv_path.exists():
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                symbols = [row['symbol'] for row in reader]
            
            print(f"\n📄 {csv_file}:")
            print(f"  Total symbols: {len(symbols)}")
            print(f"  First 10: {', '.join(symbols[:10])}")
            print(f"  Last 10: {', '.join(symbols[-10:])}")
        else:
            print(f"\n⚠️  {csv_file}: Not found (will use fallback)")


def export_current_fno():
    """Export current F&O stocks from Kite API"""
    print("\n" + "="*70)
    print("EXPORTING F&O STOCKS FROM KITE API")
    print("="*70)
    
    try:
        kite_service = KiteService()
        kite = kite_service.kite
        
        if not kite:
            print("❌ Kite not initialized")
            return
        
        print("\n📥 Fetching instruments from Kite...")
        data_source = ZerodhaDataSource(kite)
        
        # Get NFO instruments
        nfo_instruments = data_source.get_instruments(exchange="NFO")
        nfo_symbols = {
            inst.tradingsymbol 
            for inst in nfo_instruments 
            if inst.instrument_type == "FUT"
        }
        
        print(f"Found {len(nfo_symbols)} F&O stocks in NFO")
        
        # Get NSE instruments
        nse_instruments = data_source.get_instruments(exchange="NSE")
        fno_stocks = [
            inst.tradingsymbol
            for inst in nse_instruments
            if inst.segment == "NSE"
            and inst.instrument_type == "EQ"
            and inst.tradingsymbol in nfo_symbols
        ]
        
        fno_stocks.sort()
        
        # Export to CSV
        output_path = Path(__file__).parent.parent.parent / "data" / "universes" / "fno_stocks_new.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol'])
            for symbol in fno_stocks:
                writer.writerow([symbol])
        
        print(f"\n✅ Exported {len(fno_stocks)} F&O stocks to:")
        print(f"   {output_path}")
        print(f"\n💡 To use this list:")
        print(f"   mv {output_path} {output_path.parent}/fno_stocks.csv")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python -m backend.scripts.manage_universes [test|stats|export]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "test":
        test_universes()
    elif command == "stats":
        show_stats()
    elif command == "export":
        export_current_fno()
    else:
        print(f"Unknown command: {command}")
        print("Available: test, stats, export")


if __name__ == '__main__':
    main()

