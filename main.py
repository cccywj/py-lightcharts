import sys
import random
import datetime
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer

# Import your library component
from pylightcharts import PyLightChartWidget

def generate_mock_data(num_candles=200, tf_seconds=60):
    """Generates mock historical data, scaling volatility by timeframe."""
    data = []
    price = 150.00
    now = datetime.datetime.now(datetime.UTC)
    base_time = now - datetime.timedelta(seconds=num_candles * tf_seconds)
    volatility = 0.05 * (tf_seconds ** 0.5)
    
    for i in range(num_candles):
        move = random.uniform(-volatility, volatility)
        open_p = price
        close_p = open_p + move
        high_p = max(open_p, close_p) + random.uniform(0, volatility/2)
        low_p = min(open_p, close_p) - random.uniform(0, volatility/2)
        data.append({
            "time": base_time + datetime.timedelta(seconds=i * tf_seconds),
            "open": round(open_p, 5), "high": round(high_p, 5),
            "low": round(low_p, 5), "close": round(close_p, 5),
            "volume": random.randint(100, 1000)
        })
        price = close_p
    return data


class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyLightCharts - Final Architecture")
        self.resize(1100, 700)
        
        # 1. Instantiate the chart library widget directly
        self.chart = PyLightChartWidget()
        self.setCentralWidget(self.chart)
        
        # 2. Connect Library Hooks to App Logic
        # When the user clicks "5m", the chart tells us so we can fetch 5m data!
        self.chart.timeframe_requested.connect(self.fetch_historical_data)
        
        # 3. Initialize default state
        self.current_tf = 60
        self.chart.set_timeframe(self.current_tf)
        self.fetch_historical_data(self.current_tf)
        
        # Live Tick Simulator
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.on_live_tick)
        self.tick_timer.start(250)

    def fetch_historical_data(self, tf_seconds):
        """Hook triggered when user selects a new timeframe inside the chart's toolbar."""
        print(f"[Main App] Fetching historical data for timeframe: {tf_seconds}s")
        self.current_tf = tf_seconds
        
        # In the future, this is where you call ib_async to get historical bars!
        history = generate_mock_data(300, tf_seconds)
        self.current_price = history[-1]['close']
        
        # Pass the newly fetched data back into the chart
        self.chart.apply_new_data(history)

    def on_live_tick(self):
        """Simulates a live market tick."""
        volatility = 0.05 * (self.current_tf ** 0.5)
        self.current_price += random.uniform(-volatility, volatility)
        self.current_price = round(self.current_price, 2)
        
        now = datetime.datetime.now(datetime.UTC)
        
        # Feed the live tick into the chart (including simulated volume)
        self.chart.update_data(self.current_price, now, volume=random.randint(1, 15))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Guarantees the dark-theme dropdowns look correct on Windows/Mac
    window = TradingApp()
    window.show()
    sys.exit(app.exec())