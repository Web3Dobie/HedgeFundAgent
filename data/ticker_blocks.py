# data/ticker_blocks.py
# Updated for Interactive Brokers Gateway symbols - VERIFIED WORKING SYMBOLS

ASIA_EQUITY = {
    "Hang Seng": "HSI",                # ✅ VERIFIED: HSI futures (HKFE, HKD) - Working: 25270 HKD
    "Nikkei 225": "NKD",               # ❓ TO TEST: Nikkei futures (might be market hours issue)
    "KOSPI": "KOSPI",                  # ❓ TO TEST: KOSPI futures 
    "CSI 300": "A50",                  # ❓ TO TEST: FTSE China A50 futures (more liquid than CSI 300)
}

EUROPE_EQUITY = {
    "DAX": "FDAX",                     # ✅ VERIFIED: FDAX futures (EUREX, EUR) - Working: 24114 EUR
    "Euro Stoxx 50": "FESX",           # ✅ VERIFIED: FESX futures (EUREX, EUR) - Working
    "FTSE 100": "Z",                   # ❓ TO TEST: FTSE 100 futures (LIFFE, GBP)
    "CAC 40": "CAC",                   # ❓ TO TEST: CAC 40 futures
}

US_EQUITY = {
    "S&P 500": "ES",                   # ✅ VERIFIED: E-mini S&P 500 futures (CME, USD) - Working: 6335.25 USD
    "NASDAQ": "NQ",                    # ❓ TO TEST: E-mini NASDAQ futures (CME, USD)
    "Dow Jones": "YM",                 # ❓ TO TEST: E-mini Dow futures (CBOT, USD)
    "Russell 2000": "RTY",             # ❓ TO TEST: Russell 2000 futures (CME, USD)
}

FX_PAIRS = {
    # Note: FX might need different symbol format - TO TEST
    "EUR/USD": "EURUSD",               # ❓ TO TEST: EUR/USD spot
    "USD/JPY": "USDJPY",               # ❓ TO TEST: USD/JPY spot
    "GBP/USD": "GBPUSD",               # ❓ TO TEST: GBP/USD spot
    "USD/CHF": "USDCHF",               # ❓ TO TEST: USD/CHF spot
    "AUD/USD": "AUDUSD",               # ❓ TO TEST: AUD/USD spot
    "USD/CAD": "USDCAD",               # ❓ TO TEST: USD/CAD spot
}

COMMODITIES = {
    "Gold": "GC",                      # ❓ TO TEST: Gold futures (COMEX, USD)
    "Silver": "SI",                    # ❓ TO TEST: Silver futures (COMEX, USD)
    "Crude Oil": "CL",                 # ❓ TO TEST: WTI Crude futures (NYMEX, USD)
    "Natural Gas": "NG",               # ❓ TO TEST: Natural Gas futures (NYMEX, USD)
    "Copper": "HG",                    # ❓ TO TEST: Copper futures (COMEX, USD)
}

RATES = {
    "10Y US Treasury": "ZN",           # ❓ TO TEST: 10-Year Treasury Note futures (CBOT, USD)
    "2Y US Treasury": "ZT",            # ❓ TO TEST: 2-Year Treasury Note futures (CBOT, USD)
    "30Y US Treasury": "ZB",           # ❓ TO TEST: 30-Year Treasury Bond futures (CBOT, USD)
}

# For crypto, we'll keep the CoinGecko IDs since IB doesn't have good crypto coverage
CRYPTO = {
    "bitcoin": "BTC",
    "ethereum": "ETH", 
    "solana": "SOL",
    "ripple": "XRP",
    "sui": "SUI",
    "cardano": "ADA",
}

# Treasury yield symbols for direct yield data (these might be indices, not futures)
YIELD_SYMBOLS = {
    "2Y": "ZT",                        # ❓ TO TEST: Use futures for yield calculation
    "10Y": "ZN",                       # ❓ TO TEST: Use futures for yield calculation  
    "30Y": "ZB"                        # ❓ TO TEST: Use futures for yield calculation
}

# Alternative symbol formats to test if the above don't work
ALTERNATIVE_FORMATS = {
    # If simple symbols don't work, try these explicit formats
    "FX_ALTERNATIVE": {
        "EUR/USD": "EUR.USD",
        "USD/JPY": "USD.JPY", 
        "GBP/USD": "GBP.USD",
    },
    "STOCK_INDICES": {
        # Try direct stock indices instead of futures
        "S&P 500": "SPX",
        "NASDAQ": "NDX", 
        "Dow Jones": "DJX",
        "DAX": "DAX",
        "FTSE 100": "UKX",
    },
    "EXPLICIT_FUT_FORMAT": {
        # Explicit futures format if needed
        "S&P 500": "ES-FUT-USD",
        "NASDAQ": "NQ-FUT-USD",
        "DAX": "FDAX-FUT-EUR",
        "Hang Seng": "HSI-FUT-HKD",
    }
}

# Summary of what we know works so far:
VERIFIED_WORKING = {
    "Stocks": {
        "AAPL": "213.19 USD",  # ✅ Verified working
    },
    "US Futures": {
        "ES": "6335.25 USD",   # ✅ S&P 500 E-mini futures
    },
    "European Futures": {
        "FDAX": "24114 EUR",   # ✅ DAX futures
        "FESX": "Working",     # ✅ Euro Stoxx 50 futures
    },
    "Asian Futures": {
        "HSI": "25270 HKD",    # ✅ Hang Seng futures
    }
}

# Notes for testing:
TESTING_NOTES = """
TESTING PRIORITY:
1. ✅ VERIFIED WORKING: ES, FDAX, FESX, HSI, AAPL
2. 🎯 HIGH PRIORITY TO TEST: NQ, YM, RTY, GC, SI, CL, NG (common US futures)
3. 🌍 INTERNATIONAL: Z (FTSE), CAC, NKD (Nikkei), KOSPI
4. 💱 FX PAIRS: Might need different format (EURUSD vs EUR.USD vs EURUSD-CASH-USD)
5. 📊 INDICES: Might work as direct symbols (SPX, NDX) instead of futures

SYMBOL FORMAT PATTERNS DISCOVERED:
- Simple symbols work best: "ES", "FDAX", "HSI" (not "ES-FUT-USD")
- Exchange-specific formats: 
  * EUREX: Full dates (20250919)
  * HKFE: YYYYMM format (202508)
  * CME: Full dates (20250919)
"""
# Backward compatibility aliases

# For compatibility with existing code that uses FOREX_PAIRS
FOREX_PAIRS = FX_PAIRS

# Additional compatibility aliases if needed
EQUITY_INDICES = {**US_EQUITY, **EUROPE_EQUITY, **ASIA_EQUITY}
ALL_SYMBOLS = {**US_EQUITY, **EUROPE_EQUITY, **ASIA_EQUITY, **FX_PAIRS, **COMMODITIES, **RATES}