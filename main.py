import argparse
import sys
import random
import datetime
from typing import List, Dict, Any

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer

from pylightcharts import PyLightChartWidget

def generate_mock_data(num_candles: int = 200, tf_seconds: int = 60, base_price: float = 150.00,
                       seed: int | None = None) -> List[Dict[str, Any]]:
    """Generate deterministic mock historical OHLCV data.

    This is useful for automated tests or reproducible rendering.
    """
    if seed is not None:
        random.seed(seed)

    data: List[Dict[str, Any]] = []
    price = base_price
    now = datetime.datetime.now(datetime.timezone.utc)
    base_time = now - datetime.timedelta(seconds=num_candles * tf_seconds)
    volatility = 0.05 * (tf_seconds ** 0.5)

    for i in range(num_candles):
        move = random.uniform(-volatility, volatility)
        open_p = price
        close_p = open_p + move
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
    def __init__(self, symbol: str = "AAPL", timeframe: int = 60, seed: int | None = None):
        super().__init__()
        self.setWindowTitle("PyLightCharts - Live Tick & Buffer Test")
        self.resize(1100, 700)

        self.chart = PyLightChartWidget()
        self.setCentralWidget(self.chart)

        # Keep a deterministic seed for reproducible tests
        self._seed = seed

        # Connect to the data hook
        self.chart.historical_data_requested.connect(self.on_chart_requested_data)

        self.current_price = 150.00
        self._symbol = symbol
        self._timeframe = timeframe

        # Simulate live ticks at 4Hz
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.on_live_tick)
        self.tick_timer.start(250)

        # Trigger the initial load
        self.chart.change_symbol(symbol)

    def on_chart_requested_data(self, symbol, timeframe):
        print(f"[Main App] Hook fired! Requesting history for {symbol} at {timeframe}s")
        
        # Randomize the base price so we visually see the symbol change
        self.current_price = random.uniform(10.0, 500.0)
        print(f"[Main App] Waiting 2 seconds for historical data... (Live ticks are buffering!)")
        
        # Simulate a 2-second network delay from IBKR
        QTimer.singleShot(2000, lambda: self._simulate_ibkr_response(timeframe))

    def _simulate_ibkr_response(self, timeframe):
        print("[Main App] Historical data arrived! Pushing to chart.")
        history = generate_mock_data(300, timeframe, base_price=self.current_price, seed=self._seed)
        self.current_price = history[-1]['close']
        
        # Hand it to the chart. It will auto-merge with the 2 seconds of buffered live ticks.
        self.chart.apply_historical_data(history)

    def on_live_tick(self):
        """Simulates an incoming ib_async.Ticker update via reqMktData"""
        volatility = 0.05 * (self.chart.data_manager.timeframe ** 0.5)
        self.current_price += random.uniform(-volatility, volatility)
        
        # Simulate a live Bid/Ask spread
        spread = random.uniform(0.01, 0.05)
        
        # <-- ROUND THESE TO 2 DECIMALS -->
        bid_price = round(self.current_price - (spread / 2.0), 2) 
        ask_price = round(self.current_price + (spread / 2.0), 2)

        # Build the simulated tick dictionary
        live_tick = {
            "time": datetime.datetime.now(datetime.timezone.utc),
            "bid": bid_price,
            "ask": ask_price,
            "volume": random.randint(1, 15)
        }
        
        self.chart.update_tick(live_tick)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PyLightCharts testing harness")
    parser.add_argument("--symbol", default="AAPL", help="Symbol to display")
    parser.add_argument("--timeframe", type=int, default=60, help="Timeframe in seconds")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for deterministic data")
    parser.add_argument("--candles", type=int, default=300, help="Number of candles to generate")
    parser.add_argument("--no-ui", action="store_true", help="Generate data only and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.no_ui:
        data = generate_mock_data(num_candles=args.candles, tf_seconds=args.timeframe,
                                  base_price=150.0, seed=args.seed)
        print(f"Generated {len(data)} candles (seed={args.seed})")
        print("Sample:", data[-3:])
        return 0

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = TradingApp(symbol=args.symbol, timeframe=args.timeframe, seed=args.seed)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())