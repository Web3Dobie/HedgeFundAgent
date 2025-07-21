namespace IBGatewayService.Models
{
    public class MarketData
    {
        public string Symbol { get; set; } = string.Empty;
        public double Bid { get; set; }
        public double Ask { get; set; }
        public double Last { get; set; }
        public long Volume { get; set; }
        public DateTime Timestamp { get; set; }
        public double BidSize { get; set; }
        public double AskSize { get; set; }
    }

    public class OrderRequest
    {
        public string Symbol { get; set; } = string.Empty;
        public string Action { get; set; } = string.Empty; // BUY or SELL
        public int Quantity { get; set; }
        public string OrderType { get; set; } = "MKT"; // MKT, LMT, etc.
        public double? LimitPrice { get; set; }
        public string Exchange { get; set; } = "SMART";
    }

    public class MarketDataSubscription
    {
        public int RequestId { get; set; }
        public string Symbol { get; set; } = string.Empty;
        public DateTime SubscribedAt { get; set; }
    }

    public class PriceData
    {
        public string Symbol { get; set; } = string.Empty;
        public double Price { get; set; }
        public DateTime Timestamp { get; set; }
    }
}