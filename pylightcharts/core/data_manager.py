import datetime
from PySide6.QtCore import QObject, Signal
from .indicators import IndicatorMath

class DataManager(QObject):
    """
    Manages the OHLCV data array, time-bucketing, and data size limits.
    Completely decoupled from the UI and rendering logic.
    """
    
    # Signal emitted whenever data is added or a live tick modifies a candle.
    # The UI will connect to this signal to trigger a repaint().
    data_changed = Signal() 

    def __init__(self, timeframe_seconds: int = 60, max_capacity: int = 10000):
        super().__init__()
        self._data_list = []
        self._timeframe_seconds = timeframe_seconds
        self._max_capacity = max_capacity
        self.price_precision = 2 

        self.active_indicators = {} # e.g. {"SMA": {"period": 14}}
        self.indicator_data = {}    # e.g. {"SMA": [None, 150, 151...]}

        # --- GAPLESS BUFFER STATE ---
        self._is_buffering = False
        self._live_buffer = []

    @property
    def timeframe(self) -> int:
        return self._timeframe_seconds

    def set_timeframe(self, tf_seconds: int):
        """Changes the timeframe resolution and clears the current data."""
        self._timeframe_seconds = tf_seconds
        self.clear_data()

    def clear_data(self):
        """Wipes the chart and resets the buffer."""
        self._data_list.clear()
        self.indicator_data.clear()
        self._live_buffer.clear()
        self._is_buffering = False
        self.data_changed.emit()

    def get_data_list(self) -> list[dict]:
        """Returns the active list of OHLC dictionaries."""
        return self._data_list

    # ==========================================
    # UTILITY: IB_ASYNC & TIMEZONE FORMATTING
    # ==========================================
    def _ensure_utc_aware(self, dt) -> datetime.datetime:
        """Converts ib_async's mixed dates/times into strict UTC-aware datetimes."""
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.time.min)
        
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
            
        return dt.astimezone(datetime.timezone.utc)

    def _parse_ib_bar(self, bar) -> dict:
        """Translates an ib_async BarData, RealTimeBar, or plain dictionary into our internal format."""
        if isinstance(bar, dict):
            # It's a dictionary (e.g., from your mock data generator)
            raw_time = bar.get('date', bar.get('time'))
            return {
                "time": self._ensure_utc_aware(raw_time),
                "open": bar.get('open'),
                "high": bar.get('high'),
                "low": bar.get('low'),
                "close": bar.get('close'),
                "volume": bar.get('volume', 0.0)
            }
        else:
            # It's an ib_async object
            # Note: ib_async uses 'date' for historical bars and 'time' for live ticks
            raw_time = getattr(bar, 'date', getattr(bar, 'time', None))
            return {
                "time": self._ensure_utc_aware(raw_time),
                "open": getattr(bar, 'open'),
                "high": getattr(bar, 'high'),
                "low": getattr(bar, 'low'),
                "close": getattr(bar, 'close'),
                "volume": getattr(bar, 'volume', 0.0)
            }

    def _calculate_precision(self, price: float) -> int:
        """Determines the number of decimal places in a float."""
        s = str(price)
        if 'e' in s.lower(): return 8
        if '.' in s: return min(max(len(s.rstrip('0').split('.')[1]), 2), 8)
        return 2

    # ==========================================
    # GAPLESS DATA PIPELINE
    # ==========================================
    def enable_buffering(self):
        """Call this right before switching symbols to queue up incoming live ticks."""
        self.clear_data()
        self._is_buffering = True

    def apply_historical_data(self, ib_bars: list):
        """
        Receives historical BarData from ib_async, parses it, and seamlessly 
        merges it with any live ticks that arrived while waiting.
        """
        historical_data = [self._parse_ib_bar(b) for b in ib_bars]
        
        if self._is_buffering and self._live_buffer:
            # Use timestamp as dict key to align buckets
            merged_dict = {b['time']: b for b in historical_data}
            
            for live_bar in self._live_buffer:
                bt = live_bar['time']
                if bt in merged_dict:
                    # AGGREGATE the live buffer into the historical snapshot
                    hist_bar = merged_dict[bt]
                    hist_bar['close'] = live_bar['close']
                    hist_bar['high'] = max(hist_bar['high'], live_bar['high'])
                    hist_bar['low'] = min(hist_bar['low'], live_bar['low'])
                    hist_bar['volume'] += live_bar['volume']
                else:
                    # If it's a completely new bucket, just insert it
                    merged_dict[bt] = live_bar
                
            self._data_list = sorted(merged_dict.values(), key=lambda x: x['time'])
            self._live_buffer.clear()
        else:
            self._data_list = historical_data

        if len(self._data_list) > self._max_capacity:
            self._data_list = self._data_list[-self._max_capacity:]
            
        if self._data_list:
            self.price_precision = self._calculate_precision(self._data_list[-1]['close'])

        self._is_buffering = False
        self._recalculate_indicators()
        self.data_changed.emit()

    def update_live_bar(self, bar):
        """
        Processes a live tick from a network stream (like ib_async).
        Aggregates the tick into the current candle or creates a new one.
        """
        parsed_bar = self._parse_ib_bar(bar)
        
        # 1. FIX: Floor timestamp to the nearest timeframe boundary IMMEDIATELY
        ts = parsed_bar['time'].timestamp()
        floored_ts = (ts // self._timeframe_seconds) * self._timeframe_seconds
        bucket_time = datetime.datetime.fromtimestamp(floored_ts, tz=datetime.timezone.utc)
        parsed_bar['time'] = bucket_time

        # 2. Handle Buffering State
        if self._is_buffering:
            if not self._live_buffer:
                self._live_buffer.append(parsed_bar)
            else:
                last_buf = self._live_buffer[-1]
                if bucket_time > last_buf['time']:
                    self._live_buffer.append(parsed_bar)
                else:
                    # Aggregate inside the buffer!
                    last_buf['close'] = parsed_bar['close']
                    last_buf['high'] = max(last_buf['high'], parsed_bar['high'])
                    last_buf['low'] = min(last_buf['low'], parsed_bar['low'])
                    last_buf['volume'] += parsed_bar['volume']
            return

        # 3. Handle Standard Live Updates
        if not self._data_list:
            self._data_list.append(parsed_bar)
        else:
            current_candle = self._data_list[-1]
            if bucket_time > current_candle['time']:
                self._data_list.append(parsed_bar)
                if len(self._data_list) > self._max_capacity:
                    self._data_list.pop(0)
            else:
                current_candle['close'] = parsed_bar['close']
                current_candle['high'] = max(current_candle['high'], parsed_bar['high'])
                current_candle['low'] = min(current_candle['low'], parsed_bar['low'])
                current_candle['volume'] += parsed_bar['volume']
                
        # Update precision dynamically
        new_prec = self._calculate_precision(parsed_bar['close'])
        if new_prec > self.price_precision: self.price_precision = new_prec

        self._recalculate_indicators()
        self.data_changed.emit()

    def get_visible_data(self, left_index: int, right_index: int) -> list[dict]:
        """Helper method to slice only the data currently visible on the screen."""
        left_index = max(0, left_index)
        right_index = min(len(self._data_list) - 1, right_index)
        if left_index > right_index or not self._data_list: return []
        return self._data_list[left_index : right_index + 1]

    def _recalculate_indicators(self):
        """Runs the math for all active indicators. Called automatically on tick/data load."""
        if not self._data_list: return
        if "SMA" in self.active_indicators:
            self.indicator_data["SMA"] = IndicatorMath.calculate_sma(self._data_list, self.active_indicators["SMA"].get("period", 14))
        if "VWAP" in self.active_indicators:
            self.indicator_data["VWAP"] = IndicatorMath.calculate_vwap(self._data_list)
            
    def add_indicator(self, name: str, params: dict = None):
        """Registers an indicator and triggers an initial calculation."""
        self.active_indicators[name] = params or {}
        self._recalculate_indicators()
        self.data_changed.emit()

    def remove_indicator(self, name: str):
        """Unregisters an indicator and clears its cached data."""
        if name in self.active_indicators:
            del self.active_indicators[name]
            if name in self.indicator_data: del self.indicator_data[name]
            self.data_changed.emit()