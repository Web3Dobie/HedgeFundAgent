import matplotlib.pyplot as plt

def plot_price_trend(data, ticker: str, output_file: str):
    """
    Create a price trend chart for a given ticker and save it to a file.
    :param data: Pandas DataFrame containing historical data.
    :param ticker: Ticker symbol (e.g., 'AAPL').
    :param output_file: File path to save the chart.
    """
    plt.figure(figsize=(10, 6))
    plt.plot(data.index, data['Close'], label='Close Price')
    plt.title(f'{ticker} Price Trend')
    plt.xlabel('Date')
    plt.ylabel('Price (USD)')
    plt.legend()
    plt.grid()
    plt.savefig(output_file)
    plt.close()  # Close the figure to avoid overlap during batching
    print(f"Chart saved to {output_file}")
