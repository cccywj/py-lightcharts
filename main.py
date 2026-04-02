"""
PyLightCharts - Testing Harness and Usage Example

This module demonstrates:
1. Generating mock historical OHLCV data for testing
2. Integrating PyLightChartWidget into a QMainWindow application
3. Simulating live market tick data with buffering
4. Handling timeframe changes and ticker updates

Usage:
    python main.py                          # Launch the GUI
    python main.py --no-ui                  # Generate and print test data
    python main.py --symbol TSLA --timeframe 300  # Change symbol/timeframe
    python main.py --seed 42                # Use a specific seed for determinism
"""
import argparse
import sys
import random
import datetime
from typing import List, Dict, Any

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer

from pylightcharts import PyLightChartWidget


def generate_mock_data(
    num_candles: int = 200,
    tf_seconds: int = 60,
    base_price: float = 150.00,
    seed: int | None = None,
) -> List[Dict[str, Any]]:
    """Generate deterministic mock historical OHLCV data for testing.
    
    Creates synthetic price data that follows realistic patterns with
    configurable volatility. Useful for testing chart rendering without
    a live data connection.
    
    Args:
        num_candles: Number of candles to generate (default: 200).
        tf_seconds: Timeframe in seconds (default: 60 = 1 minute).
        base_price: Starting price (default: 150.00).
        seed: Random seed for deterministic generation (default: None).
    
    Returns:
        List of OHLCV dictionaries with keys:
        - 'time': datetime.datetime in UTC
        - 'open': float
        - 'high': float
        - 'low': float
        - 'close': float
        - 'volume': int
    """
    if seed is not None:
        random.seed(seed)

    data: List[Dict[str, Any]] = []
    price = base_price
    now = datetime.datetime.now(datetime.timezone.utc)
    base_time = now - datetime.timedelta(seconds=num_candles * tf_seconds)
    
    # Volatility scales with the square root of timeframe
    # (longer timeframes = larger price movements)
    volatility = 0.05 * (tf_seconds ** 0.5)

    for i in range(num_candles):
        # Random directional movement
        move = random.uniform(-volatility, volatility)
        open_p = price
        close_p = open_p + move
        
        # High and low include some randomness beyond open/close
        high_p = max(open_p, close_p) + random.uniform(0, volatility / 2)
        low_p = min(open_p, close_p) - random.uniform(0, volatility / 2)

        data.append({
            "time": base_time + datetime.timedelta(seconds=i * tf_seconds),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": random.randint(100, 1000),
        })

        price = close_p

    return data


class TradingApp(QMainWindow):
    """Main application window demonstrating PyLightChartWidget usage.
    
    This example shows:
    1. Setting up a chart widget in a QMainWindow
    2. Responding to data requests via signals
    3. Simulating a 2-second network delay (realistic for IB Async)
    4. Generating live ticks at 4Hz and handling buffering
    5. Switching between symbols and timeframes
    
    The app simulates the workflow of:
    - User clicks chart or combo box → change_symbol() is called
    - Chart emits historical_data_requested signal
    - App waits 2 seconds (network delay simulation)
    - App calls apply_historical_data() to load history
    - Meanwhile, on_live_tick() fires every 250ms to simulate market data
    """

    def __init__(
        self,
        symbol: str = "AAPL",
        timeframe: int = 60,
        seed: int | None = None,
    ) -> None:
        """Initialize the trading application.
        
        Args:
            symbol: Initial ticker symbol (default: 'AAPL').
            timeframe: Initial timeframe in seconds (default: 60).
            seed: Random seed for deterministic data generation.
        """
        super().__init__()
        self.setWindowTitle("PyLightCharts - Live Tick & Buffer Test")
        self.resize(1100, 700)

        # Create the chart widget
        self.chart = PyLightChartWidget()
        self.setCentralWidget(self.chart)

        # Keep a deterministic seed for reproducible tests
        self._seed = seed

        # Connect to data request signals
        self.chart.historical_data_requested.connect(self.on_chart_requested_data)

        self.current_price = 150.00
        self._symbol = symbol
        self._timeframe = timeframe

        # Simulate live ticks at 4 Hz (250ms between ticks)
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.on_live_tick)
        self.tick_timer.start(250)

        # Request initial data for the symbol
        self.chart.change_symbol(symbol)

    def on_chart_requested_data(self, symbol: str, timeframe: int) -> None:
        """Handle the chart's request for historical data.
        
        This is called when:
        - A new symbol is selected
        - The timeframe is changed
        - The chart widget is initialized
        
        Args:
            symbol: The requested symbol.
            timeframe: The requested timeframe in seconds.
        """
        print(f"[Main App] Hook fired! Requesting history for {symbol} at {timeframe}s")

        # Randomize the base price so we visually see the symbol change
        self.current_price = random.uniform(10.0, 500.0)
        print(f"[Main App] Starting from ${self.current_price:.2f}")
        print(
            f"[Main App] Waiting 2 seconds for historical data..."
            f" (Live ticks are buffering!)"
        )

        # Simulate a 2-second network delay from IBKR (realistic for reqHistoricalData)
        QTimer.singleShot(2000, lambda: self._simulate_ibkr_response(timeframe))

    def _simulate_ibkr_response(self, timeframe: int) -> None:
        """Simulate receiving historical data after a network delay."""
        print("[Main App] Historical data arrived! Pushing to chart.")
        
        history = generate_mock_data(
            300, timeframe, base_price=self.current_price, seed=self._seed
        )

        # FIX: The random walk drifted over 300 bars. 
        # Calculate how far it drifted, and shift the entire history backwards
        # so the final historical candle perfectly aligns with our live ticks.
        drift = history[-1]["close"] - self.current_price
        
        for bar in history:
            bar["open"] = round(bar["open"] - drift, 2)
            bar["high"] = round(bar["high"] - drift, 2)
            bar["low"] = round(bar["low"] - drift, 2)
            bar["close"] = round(bar["close"] - drift, 2)

        # (Remove the old line: self.current_price = history[-1]["close"])

        # Hand it to the chart. It will now auto-merge seamlessly!
        self.chart.apply_historical_data(history)

    def on_live_tick(self) -> None:
        """Simulate an incoming live market tick (every 250ms = 4Hz).
        
        Generates realistic bid/ask spread and volume, and pushes to the chart.
        If called before historical data is loaded, the chart buffers the ticks.
        """
        # Calculate volatility for price movement
        timeframe = self.chart.data_manager.timeframe
        
        # A full bar has (timeframe * 4) ticks at 250ms interval.
        # To match the total variance of a historical bar, divide by sqrt(ticks_per_bar)
        ticks_per_bar = timeframe * 4
        bar_volatility = 0.05 * (timeframe ** 0.5)
        tick_volatility = bar_volatility / (ticks_per_bar ** 0.5) 
        
        self.current_price += random.uniform(-tick_volatility, tick_volatility)

        # Simulate a realistic Bid/Ask spread
        spread = random.uniform(0.01, 0.05)

        # Round prices to 2 decimals (market standard)
        bid_price = round(self.current_price - (spread / 2.0), 2)
        ask_price = round(self.current_price + (spread / 2.0), 2)

        # Build the simulated tick dictionary
        live_tick = {
            "time": datetime.datetime.now(datetime.timezone.utc),
            "bid": bid_price,
            "ask": ask_price,
            "volume": random.randint(1, 15),
        }

        # Push the tick to the chart
        self.chart.update_tick(live_tick)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Run the PyLightCharts testing harness"
    )
    parser.add_argument("--symbol", default="AAPL", help="Symbol to display")
    parser.add_argument(
        "--timeframe", type=int, default=60, help="Timeframe in seconds"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for deterministic data",
    )
    parser.add_argument(
        "--candles", type=int, default=300, help="Number of candles to generate"
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Generate data only and exit (no GUI)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point for the application.
    
    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = parse_args()

    if args.no_ui:
        # Data generation mode (no GUI)
        try:
            data = generate_mock_data(
                num_candles=args.candles,
                tf_seconds=args.timeframe,
                base_price=150.0,
                seed=args.seed,
            )
            print(f"Generated {len(data)} candles (seed={args.seed})")
            print("Sample:", data[-3:])
            return 0
        except Exception as e:
            print(f"Error generating data: {e}")
            return 1

    # GUI mode
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        window = TradingApp(
            symbol=args.symbol, timeframe=args.timeframe, seed=args.seed
        )
        window.show()
        return app.exec()
    except Exception as e:
        print(f"Error running GUI: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
