using Microsoft.AspNetCore.Mvc;
using IBGatewayService.Services;
using IBApi;

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

        [HttpPost("disconnect")]

        [HttpGet("status")]
        public IActionResult GetStatus()
        {
            try
            {
                var status = _ibGatewayManager.GetStatus();
                _logger.LogInformation($"Status requested: {status}");
                return Ok(status);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting status");
                return StatusCode(500, $"Error: {ex.Message}");
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
                return Ok(result);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error getting stock price for {symbol}");
                return StatusCode(500, new { error = ex.Message, symbol = symbol });
            }
        }

        [HttpGet("futures/{symbol}")]
        public async Task<IActionResult> GetFuturesPrice(string symbol, [FromQuery] string expiry = "202503")
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

                // Create futures contract
                var contract = new Contract
                {
                    Symbol = symbol,
                    SecType = "FUT",
                    Currency = "USD",
                    Exchange = GetFuturesExchange(symbol),
                    LastTradeDateOrContractMonth = expiry
                };

                _logger.LogInformation($"Getting futures market data for: {symbol} on {contract.Exchange}");
                var result = await _ibGatewayManager.GetMarketDataAsync(contract);
                
                _logger.LogInformation($"Futures market data received for {symbol}: Price={result.CurrentPrice}");
                return Ok(result);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error getting futures price for {symbol}");
                return StatusCode(500, new { error = ex.Message, symbol = symbol, expiry = expiry });
            }
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
                _ => "CME"
            };
        }
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
    }
}