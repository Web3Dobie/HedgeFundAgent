# data/ticker_blocks.py
"""
Standardized ticker symbols using yfinance format for universal compatibility
Updated to work seamlessly with IG Index + yfinance fallback system
"""

# ============================================================================
# EQUITY INDICES - Standardized to yfinance symbols
# ============================================================================

US_EQUITY = {
    "S&P 500": "^GSPC",              # ✅ Already mapped in IG: IX.D.SPTRD.DAILY.IP
    "NASDAQ": "^IXIC",               # ✅ Already mapped in IG: IX.D.NASDAQ.DAILY.IP  
    "Dow Jones": "^DJI",             # ✅ Already mapped in IG: IX.D.DOW.DAILY.IP
    "Russell 2000": "^RUT",          # 🔄 Need IG EPIC
}

EUROPE_EQUITY = {
    "DAX": "^GDAXI",                 # ✅ Already mapped in IG: IX.D.DAX.DAILY.IP
    "FTSE 100": "^FTSE",             # ✅ Already mapped in IG: IX.D.FTSE.DAILY.IP
    "Euro Stoxx 50": "^STOXX50E",    # 🔄 Need IG EPIC
    "CAC 40": "^FCHI",               # 🔄 Need IG EPIC
}

ASIA_EQUITY = {
    "Nikkei 225": "^N225",           # ✅ Already mapped in IG: IX.D.NIKKEI.DAILY.IP
    "Hang Seng": "^HSI",             # ✅ Already mapped in IG: IX.D.XINHUA.DFB.IP (China A50 proxy)
    "Shanghai Composite": "000001.SS", # 🔄 Need IG EPIC
    "KOSPI": "^KS11",                # 🔄 Need IG EPIC
}

# ============================================================================
# FOREX PAIRS - Standardized to yfinance format
# ============================================================================

FX_PAIRS = {
    "EUR/USD": "EURUSD=X",           # ✅ Already mapped in IG: CS.D.EURUSD.TODAY.IP
    "USD/JPY": "USDJPY=X",           # 🔄 Need IG EPIC  
    "GBP/USD": "GBPUSD=X",           # 🔄 Need IG EPIC
    "USD/CHF": "USDCHF=X",           # 🔄 Need IG EPIC
    "AUD/USD": "AUDUSD=X",           # 🔄 Need IG EPIC
    "USD/CAD": "USDCAD=X",           # 🔄 Need IG EPIC
    "EUR/GBP": "EURGBP=X",           # ✅ Already mapped in IG: CS.D.EURGBP.TODAY.IP
    "EUR/JPY": "EURJPY=X",           # ✅ Already mapped in IG: CS.D.EURJPY.TODAY.IP
}

# ============================================================================
# COMMODITIES - Standardized to yfinance futures format
# ============================================================================

COMMODITIES = {
    "Gold": "GC=F",                  # ✅ Already in IG alternatives: IX.D.GOLD.CFD.IP
    "Silver": "SI=F",                # 🔄 Need IG EPIC
    "Crude Oil": "CL=F",             # ✅ Already in IG alternatives: IX.D.OIL.CFD.IP
    "Brent Oil": "BZ=F",             # 🔄 Need IG EPIC (Brent)
    "Natural Gas": "NG=F",           # 🔄 Need IG EPIC
    "Copper": "HG=F",                # 🔄 Need IG EPIC
}

# ============================================================================
# TREASURY RATES - Using yfinance treasury futures
# ============================================================================

RATES = {
    "10Y US Treasury": "^TNX",       # 🔄 Direct yield index (better than futures)
    "2Y US Treasury": "^TYX",        # 🔄 Direct yield index 
    "30Y US Treasury": "^TYX",       # 🔄 Direct yield index
}

# Alternative approach using futures (backup)
TREASURY_FUTURES = {
    "2Y US Treasury": "ZT=F",        # 🔄 2-Year Treasury futures
    "10Y US Treasury": "ZN=F",       # 🔄 10-Year Treasury futures  
    "30Y US Treasury": "ZB=F",       # 🔄 30-Year Treasury futures
}

# ============================================================================
# CRYPTO - Keep existing format (works with crypto APIs)
# ============================================================================

CRYPTO = {
    "Bitcoin": "BTC-USD",            # ✅ Already mapped in IG: CS.D.BITCOIN.CFD.IP
    "Ethereum": "ETH-USD",           # 🔄 Need IG EPIC
    "Solana": "SOL-USD",             # 🔄 Need IG EPIC  
    "XRP": "XRP-USD",                # 🔄 Need IG EPIC
    "Cardano": "ADA-USD",            # 🔄 Need IG EPIC
}

# ============================================================================
# YIELD CALCULATION SYMBOLS
# ============================================================================

YIELD_SYMBOLS = {
    "2Y": "^TYX",                    # Direct yield indices are better
    "10Y": "^TNX", 
    "30Y": "^TYX"
}

# ============================================================================
# BACKWARD COMPATIBILITY ALIASES
# ============================================================================

# For compatibility with existing code
FOREX_PAIRS = FX_PAIRS
EQUITY_INDICES = {**US_EQUITY, **EUROPE_EQUITY, **ASIA_EQUITY}
ALL_SYMBOLS = {**US_EQUITY, **EUROPE_EQUITY, **ASIA_EQUITY, **FX_PAIRS, **COMMODITIES, **RATES}