using Microsoft.AspNetCore.Mvc;
using IBGatewayService.Services;
using IBApi;
using System.Text.Json;

namespace IBGatewayService.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class MarketDataController : ControllerBase
    {
        private readonly FinalIBGatewayManager _ibGatewayManager;
        private readonly ILogger<MarketDataController> _logger;

        public MarketDataController(FinalIBGatewayManager ibGatewayManager, ILogger<MarketDataController> logger)
        {
            _ibGatewayManager = ibGatewayManager;
            _logger = logger;
        }

        [HttpGet("status")]
        public IActionResult GetStatus()
        {
            try
            {
                var status = _ibGatewayManager.GetStatus();
                _logger.LogInformation($"Status requested: {status}");
                return Ok(new { status = status, timestamp = DateTime.UtcNow });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting status");
                return StatusCode(500, new { error = ex.Message });
            }
        }

        [HttpPost("connect")]
        public async Task<IActionResult> Connect()
        {
            try
            {
                _logger.LogInformation("Connect requested");
                
                if (_ibGatewayManager.IsConnected)
                {
                    return Ok(new { status = "already_connected", message = "Already connected to IB Gateway", timestamp = DateTime.UtcNow });
                }

                var connected = await _ibGatewayManager.ConnectAsync();
                
                if (connected)
                {
                    return Ok(new { status = "connected", message = "IB Gateway connection successful", timestamp = DateTime.UtcNow });
                }
                else
                {
                    return StatusCode(500, new { status = "failed", message = "Failed to connect to IB Gateway", timestamp = DateTime.UtcNow });
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error connecting to IB Gateway");
                return StatusCode(500, new { status = "error", message = ex.Message, timestamp = DateTime.UtcNow });
            }
        }

        [HttpPost("disconnect")]
        public async Task<IActionResult> Disconnect()
        {
            try
            {
                _logger.LogInformation("Disconnect requested");
                await _ibGatewayManager.DisconnectAsync();
                return Ok(new { status = "disconnected", message = "Disconnected from IB Gateway", timestamp = DateTime.UtcNow });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error disconnecting from IB Gateway");
                return StatusCode(500, new { error = ex.Message });
            }
        }

        [HttpGet("stock/{symbol}")]
        public async Task<IActionResult> GetStockPrice(string symbol)
        {
            try
            {
                _logger.LogInformation($"Stock price requested for: {symbol}");

                if (!_ibGatewayManager.IsConnected)
                {
                    _logger.LogWarning("Not connected to IB Gateway, attempting to connect...");
                    var connected = await _ibGatewayManager.ConnectAsync();
                    if (!connected)
                    {
                        return StatusCode(500, new { error = "Not connected to IB Gateway and connection failed" });
                    }
                }

                _logger.LogInformation($"Getting market data for: {symbol}");
                var result = await _ibGatewayManager.GetMarketDataAsync(symbol);
                
                _logger.LogInformation($"Market data received for {symbol}: Price={result.CurrentPrice}");
                return Ok(new { 
                    symbol = symbol,
                    price = result.CurrentPrice,
                    change_percent = result.ChangePercent,
                    timestamp = result.LastUpdate.ToString("yyyy-MM-dd HH:mm:ss"),
                    bid = result.BidPrice,
                    ask = result.AskPrice,
                    last = result.LastPrice
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error getting stock price for {symbol}");
                return StatusCode(500, new { error = ex.Message, symbol = symbol });
            }
        }

        [HttpGet("futures/{symbol}")]
        public async Task<IActionResult> GetFuturesPrice(string symbol, [FromQuery] string expiry = "AUTO")
        {
            try
            {
                _logger.LogInformation($"Futures price requested for: {symbol} expiry: {expiry}");

                if (!_ibGatewayManager.IsConnected)
                {
                    _logger.LogWarning("Not connected to IB Gateway, attempting to connect...");
                    var connected = await _ibGatewayManager.ConnectAsync();
                    if (!connected)
                    {
                        return StatusCode(500, new { error = "Not connected to IB Gateway and connection failed" });
                    }
                }

                // Determine currency and exchange for international symbols
                string currency = "USD";
                string exchange = GetFuturesExchange(symbol);
                
                // Override for international symbols
                if (symbol.ToUpper() == "FDAX" || symbol.ToUpper() == "FESX")
                {
                    currency = "EUR";
                    exchange = "EUREX";
                }
                else if (symbol.ToUpper() == "HSI")
                {
                    currency = "HKD";  
                    exchange = "HKFE";
                }
                else if (symbol.ToUpper() == "NKD")
                {
                    currency = "JPY";
                    exchange = "OSE.JPN";
                }
                else if (symbol.ToUpper() == "Z")
                {
                    currency = "GBP";
                    exchange = "LIFFE";
                }
                else if (symbol.ToUpper() == "CAC")
                {
                    currency = "EUR";
                    exchange = "MONEP";
                }
                else if (symbol.ToUpper() == "KOSPI")
                {
                    currency = "KRW";
                    exchange = "KRX";
                }
                else if (symbol.ToUpper() == "A50")
                {
                    currency = "USD";
                    exchange = "SGX";
                }

                // Use dynamic expiry calculation instead of hardcoded dates
                var dynamicExpiry = GetDynamicExpiry(exchange, symbol);
                var finalExpiry = (expiry == "AUTO") ? dynamicExpiry : expiry;

                // Create futures contract
                var contract = new Contract
                {
                    Symbol = symbol,
                    SecType = "FUT",
                    Currency = currency,
                    Exchange = exchange,
                    LastTradeDateOrContractMonth = finalExpiry
                };

                // Add contract enhancements
                EnhanceContractForExchange(contract, symbol, exchange);

                _logger.LogInformation($"Getting futures market data for: {contract.Symbol} on {contract.Exchange} in {contract.Currency} expiry {contract.LastTradeDateOrContractMonth}");
                var result = await _ibGatewayManager.GetMarketDataAsync(contract);
                
                _logger.LogInformation($"Futures market data received for {symbol}: Price={result.CurrentPrice}");
                return Ok(new { 
                    symbol = symbol,
                    price = result.CurrentPrice,
                    change_percent = result.ChangePercent,
                    timestamp = result.LastUpdate.ToString("yyyy-MM-dd HH:mm:ss"),
                    bid = result.BidPrice,
                    ask = result.AskPrice,
                    last = result.LastPrice,
                    currency = contract.Currency,
                    exchange = contract.Exchange,
                    expiry = contract.LastTradeDateOrContractMonth
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error getting futures price for {symbol}");
                return StatusCode(500, new { error = ex.Message, symbol = symbol, expiry = expiry });
            }
        }

        // New generic endpoint that handles both stocks and futures
        [HttpGet("price/{symbol}")]
        public async Task<IActionResult> GetPrice(string symbol)
        {
            try
            {
                _logger.LogInformation($"Price requested for: {symbol}");

                if (!_ibGatewayManager.IsConnected)
                {
                    _logger.LogWarning("Not connected to IB Gateway, attempting to connect...");
                    var connected = await _ibGatewayManager.ConnectAsync();
                    if (!connected)
                    {
                        return StatusCode(500, new { error = "Not connected to IB Gateway and connection failed" });
                    }
                }

                Contract contract;

                // Enhanced contract type detection
                if (IsFXPair(symbol))
                {
                    // FX PAIRS (Forex) - FIXED FORMAT FROM IB DOCS
                    _logger.LogInformation($"💱 Detected FX pair: {symbol}");
                    
                    // Get base and quote currencies
                    var (baseCurrency, quoteCurrency) = ParseFXPair(symbol);
                    
                    contract = new Contract
                    {
                        Symbol = baseCurrency,       // Base currency only (EUR for EURUSD)
                        SecType = "CASH", 
                        Currency = quoteCurrency,    // Quote currency (USD for EURUSD)
                        Exchange = "IDEALPRO"        // ✅ FIXED: Use IDEALPRO (not IBFX) per IB docs
                    };
                    _logger.LogInformation($"🔧 FX contract: Symbol={baseCurrency}, Currency={quoteCurrency}, Exchange=IDEALPRO");
                }
                else if (IsTreasuryBond(symbol))
                {
                    // TREASURY BONDS/NOTES
                    _logger.LogInformation($"📊 Detected Treasury: {symbol}");
                    
                    // Use the same logic as working futures
                    string currency = "USD";
                    string exchange = GetFuturesExchange(symbol);
                    var dynamicExpiry = GetDynamicExpiry(exchange, symbol);

                    contract = new Contract
                    {
                        Symbol = symbol,
                        SecType = "FUT",  // Treasury futures, not STK
                        Currency = currency,
                        Exchange = exchange,
                        LastTradeDateOrContractMonth = dynamicExpiry
                    };
                    
                    EnhanceContractForExchange(contract, symbol, exchange);
                    _logger.LogInformation($"🔧 Treasury futures contract: Symbol={contract.Symbol}, Exchange={contract.Exchange}, Expiry={contract.LastTradeDateOrContractMonth}");
                }
                else if (symbol.Contains("-FUT-") || IsKnownFuturesSymbol(symbol))
                {
                    // FUTURES CONTRACTS
                    _logger.LogInformation($"🎯 Detected futures symbol: {symbol} - using proven /futures/ logic");
                    
                    // Determine currency and exchange for international symbols (same as /futures/ endpoint)
                    string currency = "USD";
                    string exchange = GetFuturesExchange(symbol);
                    
                    // Override for international symbols (exact same logic as /futures/)
                    if (symbol.ToUpper() == "FDAX" || symbol.ToUpper() == "FESX")
                    {
                        currency = "EUR";
                        exchange = "EUREX";
                    }
                    else if (symbol.ToUpper() == "HSI")
                    {
                        currency = "HKD";  
                        exchange = "HKFE";
                    }
                    else if (symbol.ToUpper() == "NKD")
                    {
                        currency = "JPY";
                        exchange = "OSE.JPN";
                    }
                    else if (symbol.ToUpper() == "Z")
                    {
                        currency = "GBP";
                        exchange = "LIFFE";
                    }
                    else if (symbol.ToUpper() == "CAC")
                    {
                        currency = "EUR";
                        exchange = "MONEP";  // Fixed: French exchange
                    }
                    else if (symbol.ToUpper() == "KOSPI")
                    {
                        currency = "KRW";
                        exchange = "KRX";    // Fixed: Korean exchange
                    }
                    else if (symbol.ToUpper() == "A50")
                    {
                        currency = "USD";
                        exchange = "SGX";    // Fixed: Singapore exchange
                    }

                    // Use dynamic expiry calculation (same as /futures/)
                    var dynamicExpiry = GetDynamicExpiry(exchange, symbol);

                    // Create futures contract (exact same way as /futures/)
                    contract = new Contract
                    {
                        Symbol = symbol,
                        SecType = "FUT",
                        Currency = currency,
                        Exchange = exchange,
                        LastTradeDateOrContractMonth = dynamicExpiry
                    };

                    // Add contract enhancements (same as /futures/)
                    EnhanceContractForExchange(contract, symbol, exchange);
                    
                    _logger.LogInformation($"🔧 Final futures contract: Symbol={contract.Symbol}, LocalSymbol={contract.LocalSymbol}, Currency={contract.Currency}, Exchange={contract.Exchange}, Expiry={contract.LastTradeDateOrContractMonth}");
                }
                else
                {
                    // DEFAULT TO STOCK
                    contract = new Contract
                    {
                        Symbol = symbol,
                        SecType = "STK",
                        Currency = "USD",
                        Exchange = "SMART"
                    };
                    _logger.LogInformation($"🔧 Stock contract: Symbol={contract.Symbol}, Exchange={contract.Exchange}");
                }

                _logger.LogInformation($"Getting market data for: {contract.Symbol} ({contract.SecType}) on {contract.Exchange}");
                
                var result = await _ibGatewayManager.GetMarketDataAsync(contract);
                
                return Ok(new { 
                    symbol = symbol,
                    price = result.CurrentPrice,
                    change_percent = result.ChangePercent,
                    timestamp = result.LastUpdate.ToString("yyyy-MM-dd HH:mm:ss"),
                    bid = result.BidPrice,
                    ask = result.AskPrice,
                    last = result.LastPrice,
                    currency = contract.Currency,
                    exchange = contract.Exchange,
                    secType = contract.SecType
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error getting price for {symbol}");
                return StatusCode(500, new { error = ex.Message, symbol = symbol });
            }
        }

        [HttpGet("test-fx-localsymbol")]
        public async Task<IActionResult> TestFXLocalSymbol()
        {
            var results = new List<object>();
            
            if (!_ibGatewayManager.IsConnected)
            {
                await _ibGatewayManager.ConnectAsync();
            }

            // Test FX using LocalSymbol approach (per IB documentation)
            var fxContracts = new[]
            {
                // Method 1: LocalSymbol approach (recommended in IB docs)
                new Contract { LocalSymbol = "EUR.USD", SecType = "CASH", Exchange = "IDEALPRO", Currency = "USD" },
                
                // Method 2: Standard approach with IDEALPRO  
                new Contract { Symbol = "EUR", SecType = "CASH", Exchange = "IDEALPRO", Currency = "USD" },
                
                // Method 3: Try with different base currencies
                new Contract { LocalSymbol = "GBP.USD", SecType = "CASH", Exchange = "IDEALPRO", Currency = "USD" },
                new Contract { Symbol = "GBP", SecType = "CASH", Exchange = "IDEALPRO", Currency = "USD" },
                
                // Method 4: Try reverse pairs
                new Contract { LocalSymbol = "USD.JPY", SecType = "CASH", Exchange = "IDEALPRO", Currency = "JPY" },
                new Contract { Symbol = "USD", SecType = "CASH", Exchange = "IDEALPRO", Currency = "JPY" },
            };

            var contractNames = new[]
            {
                "EUR.USD-LocalSymbol", "EUR-Standard", 
                "GBP.USD-LocalSymbol", "GBP-Standard",
                "USD.JPY-LocalSymbol", "USD-JPY-Standard"
            };

            for (int i = 0; i < fxContracts.Length; i++)
            {
                try
                {
                    var contract = fxContracts[i];
                    var name = contractNames[i];
                    
                    _logger.LogInformation($"Testing {name}: Symbol={contract.Symbol}, LocalSymbol={contract.LocalSymbol}, Currency={contract.Currency}, Exchange={contract.Exchange}");
                    
                    // Try a very short timeout to fail fast
                    var result = await _ibGatewayManager.GetMarketDataAsync(contract, 8);
                    
                    results.Add(new { 
                        test = i+1,
                        name = name,
                        status = "SUCCESS", 
                        symbol = contract.Symbol,
                        localSymbol = contract.LocalSymbol,
                        currency = contract.Currency,
                        exchange = contract.Exchange,
                        price = result.CurrentPrice 
                    });
                    
                    _logger.LogInformation($"✅ {name} WORKS! Price: {result.CurrentPrice}");
                    
                    // Don't break - test all to see which formats work
                }
                catch (Exception ex)
                {
                    var name = contractNames[i];
                    results.Add(new { 
                        test = i+1,
                        name = name,
                        status = "FAILED", 
                        error = ex.Message,
                        symbol = fxContracts[i].Symbol,
                        localSymbol = fxContracts[i].LocalSymbol,
                        currency = fxContracts[i].Currency,
                        exchange = fxContracts[i].Exchange
                    });
                    
                    _logger.LogInformation($"❌ {name} failed: {ex.Message}");
                }
                
                await Task.Delay(1000); // Wait between tests
            }

            return Ok(new { 
                message = "FX LocalSymbol testing complete",
                results = results,
                totalTested = fxContracts.Length,
                workingFormats = results.Where(r => r.GetType().GetProperty("status")?.GetValue(r)?.ToString() == "SUCCESS").ToList(),
                timestamp = DateTime.UtcNow
            });
        }

        [HttpGet("test-problematic-symbols")]
        public async Task<IActionResult> TestProblematicSymbols()
        {
            var results = new List<object>();
            
            if (!_ibGatewayManager.IsConnected)
            {
                await _ibGatewayManager.ConnectAsync();
            }

            // Test different contract variations for the failing symbols
            var testContracts = new[]
            {
                // FX - Try different formats since EURUSD failed all tests
                new Contract { Symbol = "EUR", SecType = "CASH", Currency = "USD", Exchange = "FXCONV" },
                new Contract { Symbol = "EURUSD", SecType = "CASH", Currency = "USD", Exchange = "FXCONV" },
                
                // Treasury ZT - Try different formats
                new Contract { Symbol = "ZT", SecType = "FUT", Exchange = "ECBOT", Currency = "USD", LastTradeDateOrContractMonth = "20250919" },
                new Contract { Symbol = "TU", SecType = "FUT", Exchange = "CBOT", Currency = "USD", LastTradeDateOrContractMonth = "20250919" }, // Alternative symbol
                new Contract { Symbol = "ZT", SecType = "FUT", Exchange = "CBOT", Currency = "USD", LastTradeDateOrContractMonth = "202509" }, // YYYYMM format
                
                // Gold GC - Try different expiry formats and exchanges
                new Contract { Symbol = "GC", SecType = "FUT", Exchange = "NYMEX", Currency = "USD", LastTradeDateOrContractMonth = "20250827" }, // August
                new Contract { Symbol = "GC", SecType = "FUT", Exchange = "COMEX", Currency = "USD", LastTradeDateOrContractMonth = "202508" }, // YYYYMM
                new Contract { Symbol = "GC", SecType = "FUT", Exchange = "NYMEX", Currency = "USD", LastTradeDateOrContractMonth = "202508" }, // YYYYMM
                
                // CAC - Try different symbols and exchanges
                new Contract { Symbol = "FCE", SecType = "FUT", Exchange = "MONEP", Currency = "EUR", LastTradeDateOrContractMonth = "20250919" }, // Alternative symbol
                new Contract { Symbol = "CAC40", SecType = "FUT", Exchange = "MONEP", Currency = "EUR", LastTradeDateOrContractMonth = "202509" },
                new Contract { Symbol = "PX1", SecType = "FUT", Exchange = "EUREX", Currency = "EUR", LastTradeDateOrContractMonth = "20250919" }, // Euro Stoxx 50 alternative
                
                // Try KOSPI alternatives
                new Contract { Symbol = "KOSPI200", SecType = "FUT", Exchange = "KRX", Currency = "KRW", LastTradeDateOrContractMonth = "20250911" },
                new Contract { Symbol = "KS200", SecType = "FUT", Exchange = "KRX", Currency = "KRW", LastTradeDateOrContractMonth = "202509" },
                
                // Try A50 alternatives
                new Contract { Symbol = "CN", SecType = "FUT", Exchange = "SGX", Currency = "USD", LastTradeDateOrContractMonth = "20250730" },
                new Contract { Symbol = "FTSTI", SecType = "FUT", Exchange = "SGX", Currency = "USD", LastTradeDateOrContractMonth = "202507" },
            };

            var contractNames = new[]
            {
                "FX-FXCONV", "FX-EURUSD-FXCONV", "ZT-ECBOT", "TU-CBOT", "ZT-YYYYMM", 
                "GC-NYMEX-Aug", "GC-COMEX-YYYYMM", "GC-NYMEX-YYYYMM", 
                "FCE-MONEP", "CAC40-MONEP", "PX1-EUREX", 
                "KOSPI200-KRX", "KS200-KRX", "CN-SGX", "FTSTI-SGX"
            };

            for (int i = 0; i < testContracts.Length; i++)
            {
                try
                {
                    var contract = testContracts[i];
                    var name = contractNames[i];
                    
                    _logger.LogInformation($"Testing {name}: Symbol={contract.Symbol}, SecType={contract.SecType}, Exchange={contract.Exchange}, Currency={contract.Currency}, Expiry={contract.LastTradeDateOrContractMonth}");
                    
                    // Try a very short timeout to fail fast
                    var result = await _ibGatewayManager.GetMarketDataAsync(contract, 5);
                    
                    results.Add(new { 
                        test = i+1,
                        name = name,
                        status = "SUCCESS", 
                        symbol = contract.Symbol,
                        secType = contract.SecType,
                        exchange = contract.Exchange,
                        currency = contract.Currency,
                        expiry = contract.LastTradeDateOrContractMonth,
                        price = result.CurrentPrice 
                    });
                    
                    _logger.LogInformation($"✅ {name} WORKS! Price: {result.CurrentPrice}");
                }
                catch (Exception ex)
                {
                    var name = contractNames[i];
                    results.Add(new { 
                        test = i+1,
                        name = name,
                        status = "FAILED", 
                        error = ex.Message,
                        symbol = testContracts[i].Symbol,
                        secType = testContracts[i].SecType,
                        exchange = testContracts[i].Exchange,
                        currency = testContracts[i].Currency,
                        expiry = testContracts[i].LastTradeDateOrContractMonth
                    });
                    
                    _logger.LogInformation($"❌ {name} failed: {ex.Message}");
                }
                
                await Task.Delay(1000); // Wait between tests
            }

            return Ok(new { 
                message = "Problematic symbols testing complete",
                results = results,
                totalTested = testContracts.Length,
                timestamp = DateTime.UtcNow
            });
        }

        private bool IsFXPair(string symbol)
        {
            var fxPairs = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "EURUSD", "USDJPY", "GBPUSD", "USDCHF", "AUDUSD", "USDCAD",
                "EURJPY", "EURGBP", "EURCHF", "EURAUD", "EURCAD", "GBPJPY",
                "CHFJPY", "AUDJPY", "CADJPY", "AUDCHF", "AUDCAD", "GBPCHF",
                "GBPCAD", "CADCHF", "NZDUSD", "NZDJPY", "USDNOK", "USDSEK"
            };
            
            return fxPairs.Contains(symbol);
        }

        private (string baseCurrency, string quoteCurrency) ParseFXPair(string symbol)
        {
            // Parse FX pair to get base and quote currencies
            var fxMappings = new Dictionary<string, (string, string)>(StringComparer.OrdinalIgnoreCase)
            {
                {"EURUSD", ("EUR", "USD")},
                {"GBPUSD", ("GBP", "USD")},
                {"USDJPY", ("USD", "JPY")},
                {"USDCHF", ("USD", "CHF")},
                {"AUDUSD", ("AUD", "USD")},
                {"USDCAD", ("USD", "CAD")},
                {"EURJPY", ("EUR", "JPY")},
                {"EURGBP", ("EUR", "GBP")},
                {"EURCHF", ("EUR", "CHF")},
                {"EURAUD", ("EUR", "AUD")},
                {"EURCAD", ("EUR", "CAD")},
                {"GBPJPY", ("GBP", "JPY")},
                {"CHFJPY", ("CHF", "JPY")},
                {"AUDJPY", ("AUD", "JPY")},
                {"CADJPY", ("CAD", "JPY")},
                {"AUDCHF", ("AUD", "CHF")},
                {"AUDCAD", ("AUD", "CAD")},
                {"GBPCHF", ("GBP", "CHF")},
                {"GBPCAD", ("GBP", "CAD")},
                {"CADCHF", ("CAD", "CHF")},
                {"NZDUSD", ("NZD", "USD")},
                {"NZDJPY", ("NZD", "JPY")},
                {"USDNOK", ("USD", "NOK")},
                {"USDSEK", ("USD", "SEK")}
            };
            
            if (fxMappings.TryGetValue(symbol, out var currencies))
            {
                _logger.LogInformation($"🔄 Parsed FX pair: {symbol} → Base: {currencies.Item1}, Quote: {currencies.Item2}");
                return currencies;
            }
            
            // Auto-parse if not in mapping
            if (symbol.Length == 6)
            {
                var baseCurrency = symbol.Substring(0, 3).ToUpper();
                var quoteCurrency = symbol.Substring(3, 3).ToUpper();
                _logger.LogInformation($"🔄 Auto-parsed FX pair: {symbol} → Base: {baseCurrency}, Quote: {quoteCurrency}");
                return (baseCurrency, quoteCurrency);
            }
            
            // Default fallback
            _logger.LogWarning($"⚠️ Could not parse FX pair: {symbol}, using defaults");
            return ("EUR", "USD");
        }

        private bool IsTreasuryBond(string symbol)
        {
            var treasurySymbols = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "ZT", "ZF", "ZN", "ZB", "TN"  // US Treasury futures
            };
            
            return treasurySymbols.Contains(symbol);
        }

        private bool IsKnownFuturesSymbol(string symbol)
        {
            var knownFutures = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "ES", "NQ", "YM", "RTY", "GC", "SI", "CL", "NG", "HG", "ZN", "ZB", "ZT",
                "FDAX", "FESX", "Z", "HSI", "NKD", "SGX", "KOSPI", "CAC", "BZ", "A50"
            };
            
            return knownFutures.Contains(symbol);
        }

        private string GetInternationalFuturesExchange(string symbol)
        {
            return symbol.ToUpper() switch
            {
                "FDAX" => "EUREX",
                "FESX" => "EUREX",
                "FGBL" => "EUREX",
                "FGBM" => "EUREX",
                "Z" => "LIFFE",
                "CAC" => "MONEP",        // Fixed: CAC trades on MONEP, not CME
                "HSI" => "HKFE",
                "NKD" => "OSE.JPN",
                "KOSPI" => "KRX",        // Fixed: KOSPI trades on KRX (Korea Exchange), not CME
                "A50" => "SGX",          // Fixed: China A50 trades on SGX (Singapore), not as US stock
                "SGX" => "SGX",
                "BZ" => "NYMEX",
                _ => "EUREX"
            };
        }

        private string GetFuturesExchange(string symbol)
        {
            return symbol.ToUpper() switch
            {
                "ES" => "CME",
                "NQ" => "CME",
                "YM" => "CBOT",
                "RTY" => "CME",
                "GC" => "COMEX",
                "SI" => "COMEX",
                "CL" => "NYMEX",
                "NG" => "NYMEX",
                "HG" => "COMEX",
                "ZN" => "CBOT",
                "ZB" => "CBOT",
                "ZT" => "CBOT",          // Fixed: 2Y Treasury futures trade on CBOT
                
                // Add international symbols
                "FDAX" => "EUREX",
                "FESX" => "EUREX", 
                "HSI" => "HKFE",
                "NKD" => "OSE.JPN",
                "Z" => "LIFFE",
                "CAC" => "MONEP",        // Fixed: French CAC 40 futures
                "KOSPI" => "KRX",        // Fixed: Korean KOSPI futures
                "A50" => "SGX",          // Fixed: China A50 futures on Singapore Exchange
                
                _ => "CME"
            };
        }

        private void EnhanceContractForExchange(Contract contract, string symbol, string exchange)
        {
            switch (exchange.ToUpper())
            {
                case "EUREX":
                    switch (symbol.ToUpper())
                    {
                        case "FDAX":
                            // IBKR expects Symbol="DAX" with LocalSymbol="FDAX 20250919 M"
                            contract.Symbol = "DAX";
                            contract.LocalSymbol = $"FDAX {contract.LastTradeDateOrContractMonth} M";
                            contract.Multiplier = "25";
                            contract.TradingClass = "FDAX";
                            _logger.LogInformation($"🔧 Enhanced FDAX contract: Symbol=DAX, LocalSymbol={contract.LocalSymbol}");
                            break;
                        case "FESX":
                            contract.Multiplier = "10";
                            contract.TradingClass = "FESX";
                            break;
                    }
                    break;
                    
                case "HKFE":
                    switch (symbol.ToUpper())
                    {
                        case "HSI":
                            contract.Multiplier = "50";
                            contract.TradingClass = "HSI";
                            // HSI uses YYYYMM format - ensure we have the right format
                            if (contract.LastTradeDateOrContractMonth.Length == 8)
                            {
                                // Convert YYYYMMDD to YYYYMM for HSI
                                contract.LastTradeDateOrContractMonth = contract.LastTradeDateOrContractMonth.Substring(0, 6);
                                _logger.LogInformation($"🇭🇰 Converted HSI expiry to YYYYMM format: {contract.LastTradeDateOrContractMonth}");
                            }
                            break;
                    }
                    break;
                    
                case "OSE.JPN":
                    switch (symbol.ToUpper())
                    {
                        case "NKD":
                            contract.Multiplier = "1000";
                            contract.TradingClass = "NK";
                            break;
                    }
                    break;
                    
                case "LIFFE":
                    switch (symbol.ToUpper())
                    {
                        case "Z":
                            contract.Multiplier = "10";
                            contract.TradingClass = "Z";
                            break;
                    }
                    break;
            }
        }

        // Dynamic expiry calculation with commodity-specific cycles
        private string GetDynamicExpiry(string exchange, string symbol)
        {
            try
            {
                var now = DateTime.UtcNow;
                var currentMonth = now.Month;
                var currentYear = now.Year;
                
                _logger.LogInformation($"🔥 GetDynamicExpiry: {exchange}/{symbol} - Current: {now:yyyy-MM-dd} (Month {currentMonth})");
                
                // Calculate next expiry month based on exchange and symbol type
                int nextExpiryMonth;
                
                // Commodities have different expiry cycles
                if (IsCommodity(symbol))
                {
                    nextExpiryMonth = GetCommodityExpiryMonth(symbol, currentMonth, ref currentYear);
                }
                else if (exchange.ToUpper() == "EUREX" || exchange.ToUpper() == "CME" || exchange.ToUpper() == "CBOT" || exchange.ToUpper() == "LIFFE" || exchange.ToUpper() == "OSE.JPN")
                {
                    // Quarterly cycle: Mar(3), Jun(6), Sep(9), Dec(12)
                    if (currentMonth <= 3)
                        nextExpiryMonth = 3;
                    else if (currentMonth <= 6)
                        nextExpiryMonth = 6;
                    else if (currentMonth <= 9)
                        nextExpiryMonth = 9; // ← July should hit this!
                    else
                    {
                        nextExpiryMonth = 3;
                        currentYear++;
                    }
                }
                else
                {
                    // Monthly cycle for others like HKFE
                    nextExpiryMonth = currentMonth == 12 ? 1 : currentMonth + 1;
                    if (nextExpiryMonth == 1) currentYear++;
                }
                
                // Special format handling for different exchanges
                string result;
                if (exchange.ToUpper() == "HKFE")
                {
                    // HSI uses YYYYMM format (confirmed working: "202507", "202508")
                    result = $"{currentYear:D4}{nextExpiryMonth:D2}";
                    _logger.LogInformation($"🇭🇰 HSI using YYYYMM format: {result}");
                }
                else
                {
                    // Most others use YYYYMMDD format (like EUREX, CME)
                    var expiryDate = CalculateExpiryDate(currentYear, nextExpiryMonth, exchange, symbol);
                    result = expiryDate.ToString("yyyyMMdd");
                    _logger.LogInformation($"📅 Using full date format: {result}");
                }
                
                _logger.LogInformation($"🔥 Calculated expiry: {result} (Year: {currentYear}, Month: {nextExpiryMonth})");
                return result;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error calculating dynamic expiry for {exchange}/{symbol}");
                
                // Emergency fallbacks based on exchange
                if (exchange.ToUpper() == "HKFE")
                    return "202508"; // HSI format
                else
                    return new DateTime(2025, 9, 19).ToString("yyyyMMdd"); // Default format
            }
        }

        private bool IsCommodity(string symbol)
        {
            var commodities = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "GC", "SI", "CL", "NG", "HG", "ZC", "ZS", "ZW"  // Gold, Silver, Oil, Gas, Copper, Corn, Soybeans, Wheat
            };
            
            return commodities.Contains(symbol);
        }

        private int GetCommodityExpiryMonth(string symbol, int currentMonth, ref int currentYear)
        {
            // Different commodities have different active months
            return symbol.ToUpper() switch
            {
                "GC" or "SI" => GetNearestFromMonths(currentMonth, ref currentYear, new[] { 2, 4, 6, 8, 10, 12 }), // Gold/Silver: Feb, Apr, Jun, Aug, Oct, Dec
                "CL" => GetNearestFromMonths(currentMonth, ref currentYear, new[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 }), // Oil: All months
                "NG" => GetNearestFromMonths(currentMonth, ref currentYear, new[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 }), // Natural Gas: All months
                "HG" => GetNearestFromMonths(currentMonth, ref currentYear, new[] { 3, 5, 7, 9, 12 }), // Copper: Mar, May, Jul, Sep, Dec
                _ => GetNearestFromMonths(currentMonth, ref currentYear, new[] { 3, 6, 9, 12 }) // Default quarterly
            };
        }

        private int GetNearestFromMonths(int currentMonth, ref int currentYear, int[] activeMonths)
        {
            foreach (var month in activeMonths)
            {
                if (month > currentMonth)
                    return month;
            }
            
            // If no month found this year, go to next year
            currentYear++;
            return activeMonths[0];
        }

        private DateTime CalculateExpiryDate(int year, int month, string exchange, string symbol)
        {
            return exchange.ToUpper() switch
            {
                "EUREX" => GetThirdFriday(year, month),
                "HKFE" => GetLastBusinessDay(year, month), 
                "OSE.JPN" => GetSecondFriday(year, month),
                "LIFFE" => GetThirdFriday(year, month),
                "CME" or "CBOT" or "COMEX" or "NYMEX" => GetThirdFriday(year, month),
                _ => GetThirdFriday(year, month)
            };
        }

        private DateTime GetThirdFriday(int year, int month)
        {
            var firstDay = new DateTime(year, month, 1);
            var firstFriday = firstDay;
            
            while (firstFriday.DayOfWeek != DayOfWeek.Friday)
                firstFriday = firstFriday.AddDays(1);
            
            return firstFriday.AddDays(14);
        }

        private DateTime GetSecondFriday(int year, int month)
        {
            var firstDay = new DateTime(year, month, 1);
            var firstFriday = firstDay;
            
            while (firstFriday.DayOfWeek != DayOfWeek.Friday)
                firstFriday = firstFriday.AddDays(1);
            
            return firstFriday.AddDays(7);
        }

        private DateTime GetLastBusinessDay(int year, int month)
        {
            var lastDay = new DateTime(year, month, DateTime.DaysInMonth(year, month));
            
            while (lastDay.DayOfWeek == DayOfWeek.Saturday || lastDay.DayOfWeek == DayOfWeek.Sunday)
                lastDay = lastDay.AddDays(-1);
            
            return lastDay;
        }
    }
}