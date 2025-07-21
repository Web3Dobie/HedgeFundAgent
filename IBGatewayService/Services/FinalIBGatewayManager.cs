using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using IBApi;

namespace IBGatewayService.Services
{
    public class FinalIBGatewayManager : EWrapper
    {
        private readonly ILogger<FinalIBGatewayManager> _logger;
        private readonly IConfiguration _configuration;
        private readonly EClientSocket _clientSocket;
        private readonly EReaderSignal _signal;
        private EReader? _reader;
        
        // Connection state
        private bool _isConnected = false;
        private int _nextOrderId = -1;
        
        // Data storage - using ConcurrentDictionary for thread safety
        private readonly ConcurrentDictionary<int, MarketDataResponse> _marketDataResponses;
        private readonly ConcurrentDictionary<int, TaskCompletionSource<MarketDataResponse>> _pendingRequests;
        
        // Request ID management
        private int _requestIdCounter = 1;
        private readonly object _requestIdLock = new object();
        
        // Public properties for compatibility
        public bool IsConnected => _isConnected;

        public FinalIBGatewayManager(ILogger<FinalIBGatewayManager> logger, IConfiguration configuration)
        {
            _logger = logger;
            _configuration = configuration;
            _signal = new EReaderMonitorSignal();
            _clientSocket = new EClientSocket(this, _signal);
            _marketDataResponses = new ConcurrentDictionary<int, MarketDataResponse>();
            _pendingRequests = new ConcurrentDictionary<int, TaskCompletionSource<MarketDataResponse>>();
        }

        #region Connection Methods
        
        public async Task<bool> ConnectAsync(string host = null, int? port = null, int? clientId = null)
        {
            try
            {
                // Use configuration values if parameters not provided
                var configHost = host ?? _configuration["IBGateway:Host"] ?? "10.0.0.6";
                var configPort = port ?? _configuration.GetValue<int>("IBGateway:Port", 4001);
                var configClientId = clientId ?? _configuration.GetValue<int>("IBGateway:ClientId", 1);
                var connectionTimeout = _configuration.GetValue<int>("IBGateway:ConnectionTimeoutSeconds", 30);
                
                _logger.LogInformation($"Connecting to IB Gateway at {configHost}:{configPort} with client ID {configClientId}");
                
                _clientSocket.eConnect(configHost, configPort, configClientId);
                
                // Wait for connection to be established
                var connectionTimeoutSpan = TimeSpan.FromSeconds(connectionTimeout);
                var startTime = DateTime.UtcNow;
                
                while (!_isConnected && DateTime.UtcNow - startTime < connectionTimeoutSpan)
                {
                    await Task.Delay(100);
                }
                
                if (!_isConnected)
                {
                    _logger.LogError($"Failed to connect to IB Gateway at {configHost}:{configPort} within {connectionTimeout} seconds");
                    return false;
                }
                
                // Start the reader thread
                _reader = new EReader(_clientSocket, _signal);
                _reader.Start();
                
                // Start processing messages
                _ = Task.Run(ProcessMessages);
                
                // Wait for next valid ID
                var idTimeout = TimeSpan.FromSeconds(5);
                startTime = DateTime.UtcNow;
                
                while (_nextOrderId == -1 && DateTime.UtcNow - startTime < idTimeout)
                {
                    await Task.Delay(100);
                }
                
                _logger.LogInformation($"Connected successfully to {configHost}:{configPort}. Next Order ID: {_nextOrderId}");
                return _isConnected;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to connect to IB Gateway");
                return false;
            }
        }
        
        public void Disconnect()
        {
            try
            {
                _clientSocket?.eDisconnect();
                _isConnected = false;
                _logger.LogInformation("Disconnected from IB Gateway");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error during disconnect");
            }
        }
        
        private async Task ProcessMessages()
        {
            while (_isConnected)
            {
                try
                {
                    _signal.waitForSignal();
                    _reader.processMsgs();
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error processing messages");
                    await Task.Delay(100);
                }
            }
        }

        #endregion

        #region Compatibility Methods for Existing Controller
        
        public async Task<bool> InitializeAsync()
        {
            return await ConnectAsync();
        }
        
        public string GetStatus()
        {
            return _isConnected ? "Connected" : "Disconnected";
        }
        
        public async Task<MarketDataResponse> GetMarketDataAsync(string symbol)
        {
            var contract = CreateStockContract(symbol);
            return await GetMarketDataAsync(contract);
        }
        
        public async Task<List<MarketDataResponse>> GetMultipleMarketDataAsync(List<string> symbols)
        {
            var results = new List<MarketDataResponse>();
            var tasks = new List<Task<MarketDataResponse>>();

            foreach (var symbol in symbols)
            {
                var contract = CreateStockContract(symbol);
                tasks.Add(GetMarketDataAsync(contract));
            }

            try
            {
                var responses = await Task.WhenAll(tasks);
                results.AddRange(responses);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting multiple market data");
                throw;
            }

            return results;
        }
        
        public async Task<bool> SubscribeToMarketDataAsync(string symbol)
        {
            try
            {
                var result = await GetMarketDataAsync(symbol);
                return result != null;
            }
            catch
            {
                return false;
            }
        }
        
        public async Task<bool> UnsubscribeFromMarketDataAsync(string symbol)
        {
            // For simplicity, return true as we don't maintain subscriptions
            return await Task.FromResult(true);
        }
        
        public async Task<bool> UnsubscribeFromMarketDataAsync(int requestId)
        {
            // Overload for int parameter
            return await Task.FromResult(true);
        }
        
        public async Task<bool> DisconnectAsync()
        {
            return await Task.Run(() =>
            {
                Disconnect();
                return true;
            });
        }
        
        private Contract CreateStockContract(string symbol)
        {
            return new Contract
            {
                Symbol = symbol,
                SecType = "STK",
                Currency = "USD",
                Exchange = "SMART"
            };
        }

        #endregion

        #region Market Data Methods
        
        public async Task<MarketDataResponse> GetMarketDataAsync(Contract contract, int timeoutSeconds = 30)
        {
            var requestId = GetNextRequestId();
            var tcs = new TaskCompletionSource<MarketDataResponse>();
            
            _pendingRequests[requestId] = tcs;
            _marketDataResponses[requestId] = new MarketDataResponse { RequestId = requestId };
            
            try
            {
                // Request market data with delayed data type
                _clientSocket.reqMarketDataType(3); // 3 = Delayed data
                _clientSocket.reqMktData(requestId, contract, "", false, false, new List<TagValue>());
                
                // Wait for response with timeout
                using (var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds)))
                {
                    var timeoutTask = Task.Delay(TimeSpan.FromSeconds(timeoutSeconds), cts.Token);
                    var completedTask = await Task.WhenAny(tcs.Task, timeoutTask);
                    
                    if (completedTask == timeoutTask)
                    {
                        throw new TimeoutException($"Market data request timed out for request ID {requestId}");
                    }
                    
                    cts.Cancel(); // Cancel the timeout task
                    return await tcs.Task;
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error getting market data for request ID {requestId}");
                throw;
            }
            finally
            {
                // Cleanup
                _clientSocket.cancelMktData(requestId);
                _pendingRequests.TryRemove(requestId, out _);
                _marketDataResponses.TryRemove(requestId, out _);
            }
        }
        
        private int GetNextRequestId()
        {
            lock (_requestIdLock)
            {
                return _requestIdCounter++;
            }
        }

        #endregion

        #region EWrapper Implementation - Connection Events
        
        public void connectAck()
        {
            _isConnected = true;
            _logger.LogInformation("Connection acknowledged");
        }
        
        public void connectionClosed()
        {
            _isConnected = false;
            _logger.LogInformation("Connection closed");
        }
        
        public void nextValidId(int orderId)
        {
            _nextOrderId = orderId;
            _logger.LogDebug($"Next valid order ID: {orderId}");
        }

        #endregion

        #region EWrapper Implementation - Market Data Events
        
        public void tickPrice(int tickerId, int field, double price, TickAttrib attribs)
        {
            if (_marketDataResponses.TryGetValue(tickerId, out var response))
            {
                response.LastUpdate = DateTime.UtcNow;
                
                _logger.LogInformation($"📊 Tick Price: tickerId={tickerId}, field={field}, price={price}, attribs={attribs}");
                
                switch (field)
                {
                    case 1: // BID
                        response.BidPrice = price;
                        _logger.LogInformation($"   → Set BID to {price}");
                        break;
                    case 2: // ASK
                        response.AskPrice = price;
                        _logger.LogInformation($"   → Set ASK to {price}");
                        break;
                    case 4: // LAST
                        response.LastPrice = price;
                        _logger.LogInformation($"   → Set LAST to {price}");
                        break;
                    case 6: // HIGH
                        _logger.LogInformation($"   → HIGH: {price}");
                        break;
                    case 7: // LOW
                        _logger.LogInformation($"   → LOW: {price}");
                        break;
                    case 9: // CLOSE
                        response.ClosePrice = price;
                        _logger.LogInformation($"   → Set CLOSE to {price}");
                        break;
                    case 14: // OPEN
                        _logger.LogInformation($"   → OPEN: {price}");
                        break;
                    case 66: // DELAYED_BID
                        response.BidPrice = price;
                        _logger.LogInformation($"   → Set DELAYED BID to {price}");
                        break;
                    case 67: // DELAYED_ASK
                        response.AskPrice = price;
                        _logger.LogInformation($"   → Set DELAYED ASK to {price}");
                        break;
                    case 68: // DELAYED_LAST
                        response.LastPrice = price;
                        _logger.LogInformation($"   → Set DELAYED LAST to {price}");
                        break;
                    case 72: // DELAYED_HIGH
                        _logger.LogInformation($"   → DELAYED HIGH: {price}");
                        break;
                    case 73: // DELAYED_LOW  
                        _logger.LogInformation($"   → DELAYED LOW: {price}");
                        break;
                    case 75: // DELAYED_CLOSE
                        response.ClosePrice = price;
                        _logger.LogInformation($"   → Set DELAYED CLOSE to {price}");
                        break;
                    case 76: // DELAYED_OPEN
                        _logger.LogInformation($"   → DELAYED OPEN: {price}");
                        break;
                    default:
                        _logger.LogInformation($"   → UNKNOWN FIELD {field}: {price}");
                        break;
                }
                
                CheckIfDataComplete(tickerId);
            }
        }
        
        public void tickSize(int tickerId, int field, int size)
        {
            if (_marketDataResponses.TryGetValue(tickerId, out var response))
            {
                _logger.LogDebug($"Received tick size for {tickerId}: field={field}, size={size}");
                
                switch (field)
                {
                    case 0: // BID_SIZE
                        response.BidSize = size;
                        break;
                    case 3: // ASK_SIZE
                        response.AskSize = size;
                        break;
                    case 5: // LAST_SIZE
                        response.LastSize = size;
                        break;
                    case 8: // VOLUME
                        response.Volume = size;
                        break;
                    case 69: // DELAYED_BID_SIZE
                        response.BidSize = size;
                        break;
                    case 70: // DELAYED_ASK_SIZE
                        response.AskSize = size;
                        break;
                    case 71: // DELAYED_LAST_SIZE
                        response.LastSize = size;
                        break;
                }
                
                CheckIfDataComplete(tickerId);
            }
        }
        
        public void tickString(int tickerId, int tickType, string value)
        {
            if (_marketDataResponses.TryGetValue(tickerId, out var response))
            {
                // Handle string data like timestamps, etc.
                _logger.LogDebug($"Tick string for {tickerId}: Type {tickType}, Value {value}");
            }
        }
        
        public void tickGeneric(int tickerId, int tickType, double value)
        {
            if (_marketDataResponses.TryGetValue(tickerId, out var response))
            {
                // Handle generic tick data
                _logger.LogDebug($"Tick generic for {tickerId}: Type {tickType}, Value {value}");
            }
        }
        
        private void CheckIfDataComplete(int tickerId)
        {
            if (_marketDataResponses.TryGetValue(tickerId, out var response) &&
                _pendingRequests.TryGetValue(tickerId, out var tcs))
            {
                _logger.LogDebug($"Checking data completeness for {tickerId}: Last={response.LastPrice}, Bid={response.BidPrice}, Ask={response.AskPrice}");
                
                // Check if we have enough data to complete the request
                // For delayed data, we need at least one price point
                if (response.LastPrice > 0 || response.BidPrice > 0 || response.AskPrice > 0)
                {
                    _logger.LogInformation($"Data complete for {tickerId}: Price={response.CurrentPrice}");
                    response.IsComplete = true;
                    tcs.SetResult(response);
                }
            }
        }

        #endregion

        #region EWrapper Implementation - Error Handling
        
        public void error(Exception e)
        {
            _logger.LogError(e, "IB API Exception");
        }
        
        public void error(string str)
        {
            _logger.LogError($"IB API Error: {str}");
        }
        
        public void error(int id, int errorCode, string errorMsg)
        {
            // Some error codes are just informational
            if (errorCode == 2104 || errorCode == 2106 || errorCode == 2158)
            {
                _logger.LogDebug($"IB Info {errorCode}: {errorMsg}");
                return;
            }
            
            _logger.LogError($"IB Error {errorCode} for request {id}: {errorMsg}");
            
            // Complete pending requests with error for connection issues
            if (errorCode >= 504 && errorCode <= 507)
            {
                if (_pendingRequests.TryGetValue(id, out var tcs))
                {
                    tcs.SetException(new Exception($"IB Error {errorCode}: {errorMsg}"));
                }
            }
        }

        #endregion

        #region EWrapper Implementation - Required but Unused Methods
        
        public void currentTime(long time) { }
        public void tickEFP(int tickerId, int tickType, double basisPoints, string formattedBasisPoints, double impliedFuture, int holdDays, string futureLastTradeDate, double dividendImpact, double dividendsToLastTradeDate) { }
        public void deltaNeutralValidation(int reqId, DeltaNeutralContract deltaNeutralContract) { }
        public void tickOptionComputation(int tickerId, int field, double impliedVol, double delta, double optPrice, double pvDividend, double gamma, double vega, double theta, double undPrice) { }
        public void tickSnapshotEnd(int reqId) { }
        public void managedAccounts(string accountsList) { }
        public void accountSummary(int reqId, string account, string tag, string value, string currency) { }
        public void accountSummaryEnd(int reqId) { }
        public void bondContractDetails(int reqId, ContractDetails contractDetails) { }
        public void updateAccountValue(string key, string value, string currency, string accountName) { }
        public void updatePortfolio(Contract contract, double position, double marketPrice, double marketValue, double averageCost, double unrealizedPNL, double realizedPNL, string accountName) { }
        public void updateAccountTime(string timeStamp) { }
        public void accountDownloadEnd(string accountName) { }
        public void orderStatus(int orderId, string status, double filled, double remaining, double avgFillPrice, int permId, int parentId, double lastFillPrice, int clientId, string whyHeld, double mktCapPrice) { }
        public void openOrder(int orderId, Contract contract, Order order, OrderState orderState) { }
        public void openOrderEnd() { }
        public void contractDetails(int reqId, ContractDetails contractDetails) { }
        public void contractDetailsEnd(int reqId) { }
        public void execDetails(int reqId, Contract contract, Execution execution) { }
        public void execDetailsEnd(int reqId) { }
        public void commissionReport(CommissionReport commissionReport) { }
        public void fundamentalData(int reqId, string data) { }
        public void historicalData(int reqId, Bar bar) { }
        public void historicalDataUpdate(int reqId, Bar bar) { }
        public void historicalDataEnd(int reqId, string startDateStr, string endDateStr) { }
        public void marketDataType(int reqId, int marketDataType) { }
        public void updateMktDepth(int id, int position, int operation, int side, double price, int size) { }
        public void updateMktDepthL2(int id, int position, string marketMaker, int operation, int side, double price, int size, bool isSmartDepth) { }
        public void updateNewsBulletin(int msgId, int msgType, string newsMessage, string originatingExch) { }
        public void position(string account, Contract contract, double position, double avgCost) { }
        public void positionEnd() { }
        public void realtimeBar(int reqId, long time, double open, double high, double low, double close, long volume, double wap, int count) { }
        public void scannerParameters(string xml) { }
        public void scannerData(int reqId, int rank, ContractDetails contractDetails, string distance, string benchmark, string projection, string legsStr) { }
        public void scannerDataEnd(int reqId) { }
        public void receiveFA(int faData, string cxml) { }
        public void verifyMessageAPI(string apiData) { }
        public void verifyCompleted(bool isSuccessful, string errorText) { }
        public void verifyAndAuthMessageAPI(string apiData, string xyzChallange) { }
        public void verifyAndAuthCompleted(bool isSuccessful, string errorText) { }
        public void displayGroupList(int reqId, string groups) { }
        public void displayGroupUpdated(int reqId, string contractInfo) { }
        public void positionMulti(int reqId, string account, string modelCode, Contract contract, double position, double avgCost) { }
        public void positionMultiEnd(int reqId) { }
        public void accountUpdateMulti(int reqId, string account, string modelCode, string key, string value, string currency) { }
        public void accountUpdateMultiEnd(int reqId) { }
        public void securityDefinitionOptionParameter(int reqId, string exchange, int underlyingConId, string tradingClass, string multiplier, HashSet<string> expirations, HashSet<double> strikes) { }
        public void securityDefinitionOptionParameterEnd(int reqId) { }
        public void softDollarTiers(int reqId, SoftDollarTier[] tiers) { }
        public void familyCodes(FamilyCode[] familyCodes) { }
        public void symbolSamples(int reqId, ContractDescription[] contractDescriptions) { }
        public void mktDepthExchanges(DepthMktDataDescription[] depthMktDataDescriptions) { }
        public void tickNews(int tickerId, long timeStamp, string providerCode, string articleId, string headline, string extraData) { }
        public void smartComponents(int reqId, Dictionary<int, KeyValuePair<string, char>> theMap) { }
        public void tickReqParams(int tickerId, double minTick, string bboExchange, int snapshotPermissions) { }
        public void newsProviders(NewsProvider[] newsProviders) { }
        public void newsArticle(int requestId, int articleType, string articleText) { }
        public void historicalNews(int requestId, string time, string providerCode, string articleId, string headline) { }
        public void historicalNewsEnd(int requestId, bool hasMore) { }
        public void headTimestamp(int reqId, string headTimestamp) { }
        public void histogramData(int reqId, HistogramEntry[] data) { }
        public void rerouteMktDataReq(int reqId, int conid, string exchange) { }
        public void rerouteMktDepthReq(int reqId, int conid, string exchange) { }
        public void marketRule(int marketRuleId, PriceIncrement[] priceIncrements) { }
        public void pnl(int reqId, double dailyPnL, double unrealizedPnL, double realizedPnL) { }
        public void pnlSingle(int reqId, int pos, double dailyPnL, double unrealizedPnL, double realizedPnL, double value) { }
        public void historicalTicks(int reqId, HistoricalTick[] ticks, bool done) { }
        public void historicalTicksBidAsk(int reqId, HistoricalTickBidAsk[] ticks, bool done) { }
        public void historicalTicksLast(int reqId, HistoricalTickLast[] ticks, bool done) { }
        public void tickByTickAllLast(int reqId, int tickType, long time, double price, int size, TickAttribLast tickAttribLast, string exchange, string specialConditions) { }
        public void tickByTickBidAsk(int reqId, long time, double bidPrice, double askPrice, int bidSize, int askSize, TickAttribBidAsk tickAttribBidAsk) { }
        public void tickByTickMidPoint(int reqId, long time, double midPoint) { }
        public void orderBound(long orderId, int apiClientId, int apiOrderId) { }
        public void completedOrder(Contract contract, Order order, OrderState orderState) { }
        public void completedOrdersEnd() { }

        #endregion
    }

    public class MarketDataResponse
    {
        public int RequestId { get; set; }
        public double BidPrice { get; set; }
        public double AskPrice { get; set; }
        public double LastPrice { get; set; }
        public double ClosePrice { get; set; }
        public int BidSize { get; set; }
        public int AskSize { get; set; }
        public int LastSize { get; set; }
        public int Volume { get; set; }
        public DateTime LastUpdate { get; set; }
        public bool IsComplete { get; set; }
        
        public double ChangePercent
        {
            get
            {
                if (ClosePrice > 0 && LastPrice > 0)
                {
                    return ((LastPrice - ClosePrice) / ClosePrice) * 100;
                }
                return 0;
            }
        }
        
        public double CurrentPrice => LastPrice > 0 ? LastPrice : 
                                      (BidPrice > 0 && AskPrice > 0) ? (BidPrice + AskPrice) / 2 : 
                                      BidPrice > 0 ? BidPrice : 
                                      AskPrice;
    }
}