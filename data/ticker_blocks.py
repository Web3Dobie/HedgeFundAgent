# data/ticker_blocks.py
# Updated for Interactive Brokers Gateway symbols

ASIA_EQUITY = {
    "Nikkei 225": "N225-IND-JPY",      # Nikkei 225 Index
    "KOSPI": "KOSPI-IND-KRW",          # Korean index
    "Hang Seng": "HSI-IND-HKD",        # Hong Kong
    "CSI 300": "300-IND-CNH",          # China CSI 300
}

EUROPE_EQUITY = {
    "Euro Stoxx 50": "SX5E-IND-EUR",   # Euro Stoxx 50
    "FTSE 100": "UKX-IND-GBP",         # UK FTSE 100
    "DAX": "DAX-IND-EUR",              # German DAX
    "CAC 40": "CAC-IND-EUR",           # French CAC 40
}

US_EQUITY = {
    "S&P 500": "ES-FUT-USD",           # E-mini S&P 500 futures
    "Dow Jones": "YM-FUT-USD",         # E-mini Dow futures
    "NASDAQ Composite": "NQ-FUT-USD",  # E-mini NASDAQ futures
    "Russell 2000": "RTY-FUT-USD",     # Russell 2000 futures
}

FX_PAIRS = {
    "USD/JPY": "USDJPY-CASH-JPY",      # USD/JPY spot
    "USD/CNH": "USDCNH-CASH-CNH",      # USD/CNH offshore
    "USD/AUD": "AUDUSD-CASH-AUD",      # AUD/USD (note: IB quotes as AUDUSD)
    "EUR/USD": "EURUSD-CASH-EUR",      # EUR/USD
    "GBP/USD": "GBPUSD-CASH-GBP",      # GBP/USD
    "EUR/CHF": "EURCHF-CASH-EUR",      # EUR/CHF
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

# Treasury yield symbols for direct yield data
YIELD_SYMBOLS = {
    "3M": "IRX-IND-USD",
    "5Y": "FVX-IND-USD", 
    "10Y": "TNX-IND-USD",
    "30Y": "TYX-IND-USD"
}