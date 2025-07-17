# data/ticker_blocks.py
# Updated for Interactive Brokers Gateway symbols - ALL INDICES AS FUTURES

ASIA_EQUITY = {
    "Nikkei 225": "NK-FUT-JPY",        # Nikkei 225 futures
    "KOSPI": "KS200-FUT-KRW",          # KOSPI 200 futures  
    "Hang Seng": "HSI-FUT-HKD",        # Hang Seng futures
    "CSI 300": "A50-FUT-USD",          # FTSE China A50 futures (more liquid than CSI 300)
}

EUROPE_EQUITY = {
    "Euro Stoxx 50": "ESTX50-FUT-EUR",   # Euro Stoxx 50 futures
    "FTSE 100": "Z-FUT-GBP",           # FTSE 100 futures
    "DAX": "DAX-FUT-EUR",             # DAX futures
    "CAC 40": "CAC40-FUT-EUR",           # CAC 40 futures
}

US_EQUITY = {
    "S&P 500": "ES-FUT-USD",           # E-mini S&P 500 futures
    "Dow Jones": "YM-FUT-USD",         # E-mini Dow futures
    "NASDAQ": "NQ-FUT-USD",            # E-mini NASDAQ futures
    "Russell 2000": "RTY-FUT-USD",     # Russell 2000 futures
}

FX_PAIRS = {
    "USD/JPY": "USD.JPY-CASH-USD",      # USD/JPY spot
    "EUR/USD": "EUR.USD-CASH-USD",      # EUR/USD spot
    "GBP/USD": "GBP.USD-CASH-USD",      # GBP/USD spot
    "USD/CHF": "USD.CHF-CASH-USD",      # USD/CHF spot
    "AUD/USD": "AUD.USD-CASH-USD",      # AUD/USD spot
    "USD/CAD": "USD.CAD-CASH-USD",      # USD/CAD spot
}

COMMODITIES = {
    "Gold": "GC-FUT-USD",              # Gold futures
    "Silver": "SI-FUT-USD",            # Silver futures
    "Crude Oil": "CL-FUT-USD",         # WTI Crude futures
    "Natural Gas": "NG-FUT-USD",       # Natural Gas futures
    "Copper": "HG-FUT-USD",            # Copper futures
}

RATES = {
    "10Y US Treasury": "ZN-FUT-USD",   # 10-Year Treasury Note futures
    "2Y US Treasury": "ZT-FUT-USD",    # 2-Year Treasury Note futures
    "30Y US Treasury": "ZB-FUT-USD",   # 30-Year Treasury Bond futures
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
    "2Y": "ZT-FUT-USD",    # Use futures for yield calculation
    "10Y": "ZN-FUT-USD",   # Use futures for yield calculation  
    "30Y": "ZB-FUT-USD"    # Use futures for yield calculation
}