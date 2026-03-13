# PyLightCharts

**A high-performance, native PySide6 financial charting library.**

PyLightCharts is a lightweight, TradingView-style charting library built entirely in Python using PySide6's `QPainter`. It is designed for algorithmic traders and quantitative developers who need a seamless, gapless charting experience when connecting to live data streams like **Interactive Brokers (`ib_async`)**.

## Features
* **Native PySide6 Rendering**: Hardware-accelerated drawing with zero web-engine overhead.
* **TradingView Aesthetics**: Sleek dark theme, flat UI dropdowns, magnetic crosshairs, and floating OHLC tooltips.
* **Gapless Buffer Architecture**: Seamlessly merges asynchronous historical data payloads with live tick streams to ensure zero missing candles during symbol or timeframe changes.
* **Native `ib_async` Support**: Feed `BarData` and `RealTimeBar` objects directly into the chart. The library handles timezone conversions (UTC-aware) and data parsing automatically.
* **Built-in Toolbar**: Integrated dropdowns for Timeframes and Indicators.
* **Dynamic Precision**: Automatically detects if a symbol is a stock (2 decimals) or forex/crypto (up to 8 decimals) and formats the Y-axis accordingly.
* **Built-in Indicators**: Includes Simple Moving Average (SMA), Volume Weighted Average Price (VWAP), and Volume bars out of the box.

---

## Quick Start

### 1. Basic Implementation
Because PyLightCharts handles its own UI and math, embedding it into your main application is incredibly simple.

```python
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from pylightcharts import PyLightChartWidget

class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1100, 700)
        
        # 1. Instantiate the chart
        self.chart = PyLightChartWidget()
        self.setCentralWidget(self.chart)
        
        # 2. Connect the data hook
        self.chart.historical_data_requested.connect(self.on_data_requested)
        
        # 3. Trigger the initial load
        self.chart.change_symbol("AAPL")

    def on_data_requested(self, symbol, timeframe_seconds):
        # Fetch your data here...
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Recommended for correct dropdown styling
    window = TradingApp()
    window.show()
    sys.exit(app.exec())
```

---

## The Gapless Buffer Architecture

Most charting libraries flicker or drop live ticks while waiting for an API to return historical data. PyLightCharts solves this using a background buffer. 

When you use the `ib_async` integration loop, follow this specific pattern to guarantee gapless data:

```python
def on_data_requested(self, symbol, timeframe_seconds):
    contract = Stock(symbol, 'SMART', 'USD')
    
    # 1. Start live stream FIRST (The chart is buffering in the background)
    bars = self.ib.reqRealTimeBars(contract, 5, 'TRADES', False)
    bars.updateEvent += lambda b, _: self.chart.update_live_bar(b[-1])

    # 2. Request history
    history = self.ib.reqHistoricalData(
        contract, endDateTime='', durationStr='2 D',
        barSizeSetting='1 min', whatToShow='TRADES', useRTH=True
    )
    
    # 3. Apply history. The chart will instantly stitch the history 
    # and the queued live buffer together!
    self.chart.apply_historical_data(history)
```

---

## API Reference

### Signals (Hooks)
The chart communicates with your main application purely through Qt Signals.

* **`historical_data_requested(symbol: str, timeframe_seconds: int)`**: Emitted when the user changes the symbol programmatically or selects a new timeframe from the toolbar. Your app should catch this, fetch data, and call `apply_historical_data`.
* **`timeframe_requested(timeframe_seconds: int)`**: Emitted when the timeframe is changed (typically handled internally, but exposed for custom integrations).
* **`indicator_requested(ind_code: str)`**: Emitted when a user selects an indicator from the toolbar. (Handled internally by default).

### Public Methods
* **`change_symbol(symbol: str)`**: The main entry point to switch charts. This clears the current chart, enables the background buffer, and emits the `historical_data_requested` signal.
* **`enable_buffering()`**: Manually wipe the chart and start queueing incoming `update_live_bar` calls.
* **`apply_historical_data(ib_bars: list)`**: Takes a list of `ib_async` objects (or standard dictionaries) and paints the chart. If the buffer is active, it seamlessly merges the lists.
* **`update_live_bar(ib_bar)`**: Feed a live tick into the chart. The chart will automatically floor the timestamp to match the current timeframe bucket, updating the current candle or spawning a new one.
* **`set_timeframe(seconds: int)`**: Programmatically change the timeframe. Updates the toolbar UI to match.
* **`toggle_indicator(ind_code: str)`**: Programmatically toggle an indicator layer (e.g., `"SMA"`, `"VWAP"`, `"VOL"`).

---

## Data Format Requirements

If you are not using `ib_async` objects, you can pass standard Python dictionaries to `apply_historical_data` and `update_live_bar`. The dictionary must contain:

```python
import datetime

{
    "time": datetime.datetime.now(datetime.UTC), # Must be UTC-aware!
    "open": 150.00,
    "high": 150.50,
    "low": 149.80,
    "close": 150.25,
    "volume": 5000 
}
```
