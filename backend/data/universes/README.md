# Stock Universe Data Files

## Overview
These CSV files contain the list of stocks for each trading universe. They can be updated independently of the code.

## Files
- `fno_stocks.csv` - F&O stocks (~150 stocks with active futures/options)
- `nifty500_stocks.csv` - Nifty 500 index constituents
- `nifty200_stocks.csv` - Nifty 200 index constituents (subset of Nifty 500)

## Update Frequency
- **F&O List**: Update monthly (NSE adds/removes stocks from F&O segment)
- **Nifty 500/200**: Update quarterly (index rebalancing in Mar, Jun, Sep, Dec)

## Data Sources
1. **F&O Stocks**: https://www.nseindia.com/market-data/equity-derivatives
2. **Nifty 500**: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
3. **Nifty 200**: https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv

## Format
```csv
symbol
RELIANCE
TCS
HDFCBANK
...
```

## Usage
The universe classes will automatically load from these files. If files are missing or corrupted, hardcoded fallback lists are used.

## Maintenance
1. Download latest CSV from NSE/Nifty indices
2. Extract symbol column
3. Replace the file
4. No code changes needed - restart the application

## Notes
- Use exact NSE symbols (e.g., "M&M", "BAJAJ-AUTO")
- One symbol per line
- Remove header row if present in source data
- Symbols are case-sensitive (use uppercase)
