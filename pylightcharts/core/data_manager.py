import datetime
from PySide6.QtCore import QObject, Signal
from .indicators import IndicatorMath

class DataManager(QObject):
    """
    Manages the OHLCV data array, time-bucketing, and data size limits.
    Completely decoupled from the UI and rendering logic.
    """
    
    data_changed = Signal() 

    def __init__(self, timeframe_seconds: int = 60, max_capacity: int = 10000):
        super().__init__()
        self._data_list = []
        self._timeframe_seconds = timeframe_seconds
        self._max_capacity = max_capacity
        self.price_precision = 2 

        self.active_indicators = {} 
        self.indicator_data = {}    

        # --- GAPLESS BUFFER STATE ---
        self._is_buffering = False
        self._live_buffer = []

    @property
    def timeframe(self) -> int:
        return self._timeframe_seconds

    def set_timeframe(self, tf_seconds: int):
        self._timeframe_seconds = tf_seconds
        self.clear_data()

    def clear_data(self):
        self._data_list.clear()
        self.indicator_data.clear()
        self._live_buffer.clear()
        self._is_buffering = False
        self.data_changed.emit()

    def get_data_list(self) -> list[dict]:
        return self._data_list

    # ==========================================
    # UTILITY: IB_ASYNC & TIMEZONE FORMATTING
    # ==========================================
    def _ensure_utc_aware(self, dt) -> datetime.datetime:
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.time.min)
        if dt is None:
            return datetime.datetime.now(datetime.timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)

    def _parse_ib_bar(self, bar) -> dict:
        """Translates an ib_async BarData or plain dictionary into our internal format."""
        if isinstance(bar, dict):
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
            raw_time = getattr(bar, 'date', getattr(bar, 'time', None))
            return {
                "time": self._ensure_utc_aware(raw_time),
                "open": getattr(bar, 'open'),
                "high": getattr(bar, 'high'),
                "low": getattr(bar, 'low'),
                "close": getattr(bar, 'close'),
                "volume": getattr(bar, 'volume', 0.0)
            }

    def _parse_tick(self, tick) -> dict:
        """Translates an ib_async Ticker or dict into a single-price OHLC mini-bar using Bid/Ask Midpoint."""
        if isinstance(tick, dict):
            raw_time = tick.get('time')
            bid = tick.get('bid', 0.0)
            ask = tick.get('ask', 0.0)
            
            if bid and ask and bid > 0 and ask > 0:
                price = (bid + ask) / 2.0
            else:
                price = tick.get('price', 0.0)
                
            vol = tick.get('volume', 0.0)
        else:
            # It's an ib_async.Ticker object
            raw_time = getattr(tick, 'time', None)
            
            bid = getattr(tick, 'bid', 0.0)
            ask = getattr(tick, 'ask', 0.0)
            
            # Midpoint calculation: Ensure bid/ask exist, are not NaN, and are > 0
            if bid and ask and bid == bid and ask == ask and bid > 0 and ask > 0:
                price = (bid + ask) / 2.0
            else:
                # Fallback to last trade or close if spread is missing/invalid
                price = getattr(tick, 'last', 0.0)
                if price is None or price != price or price == 0.0: 
                    price = getattr(tick, 'close', 0.0)
                    
            vol = getattr(tick, 'lastSize', getattr(tick, 'volume', 0.0))
            if vol is None or vol != vol: 
                vol = 0.0

        return {
            "time": self._ensure_utc_aware(raw_time),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": vol
        }

    def _calculate_precision(self, price: float) -> int:
        s = str(price)
        if 'e' in s.lower(): return 8
        if '.' in s: return min(max(len(s.rstrip('0').split('.')[1]), 2), 8)
        return 2

    # ==========================================
    # GAPLESS DATA PIPELINE
    # ==========================================
    def enable_buffering(self):
        self.clear_data()
        self._is_buffering = True

    def apply_historical_data(self, ib_bars: list):
        historical_data = [self._parse_ib_bar(b) for b in ib_bars]
        
        if self._is_buffering and self._live_buffer:
            merged_dict = {b['time']: b for b in historical_data}
            
            for live_bar in self._live_buffer:
                bt = live_bar['time']
                if bt in merged_dict:
                    hist_bar = merged_dict[bt]
                    hist_bar['close'] = live_bar['close']
                    hist_bar['high'] = max(hist_bar['high'], live_bar['high'])
                    hist_bar['low'] = min(hist_bar['low'], live_bar['low'])
                    hist_bar['volume'] += live_bar['volume']
                else:
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

    def update_tick(self, tick):
        """Processes a live tick and aggregates it into the current bucket."""
        parsed_tick = self._parse_tick(tick)
        
        # Abort if price is invalid (e.g. 0.0 from an empty ticker object)
        if not parsed_tick['close'] or parsed_tick['close'] == 0.0:
            return
            
        ts = parsed_tick['time'].timestamp()
        floored_ts = (ts // self._timeframe_seconds) * self._timeframe_seconds
        bucket_time = datetime.datetime.fromtimestamp(floored_ts, tz=datetime.timezone.utc)
        parsed_tick['time'] = bucket_time

        if self._is_buffering:
            if not self._live_buffer:
                self._live_buffer.append(parsed_tick)
            else:
                last_buf = self._live_buffer[-1]
                if bucket_time > last_buf['time']:
                    self._live_buffer.append(parsed_tick)
                else:
                    last_buf['close'] = parsed_tick['close']
                    last_buf['high'] = max(last_buf['high'], parsed_tick['high'])
                    last_buf['low'] = min(last_buf['low'], parsed_tick['low'])
                    last_buf['volume'] += parsed_tick['volume']
            return

        if not self._data_list:
            self._data_list.append(parsed_tick)
        else:
            current_candle = self._data_list[-1]
            if bucket_time > current_candle['time']:
                self._data_list.append(parsed_tick)
                if len(self._data_list) > self._max_capacity:
                    self._data_list.pop(0)
            else:
                current_candle['close'] = parsed_tick['close']
                current_candle['high'] = max(current_candle['high'], parsed_tick['high'])
                current_candle['low'] = min(current_candle['low'], parsed_tick['low'])
                current_candle['volume'] += parsed_tick['volume']

        self._recalculate_indicators()
        self.data_changed.emit()

    def get_visible_data(self, left_index: int, right_index: int) -> list[dict]:
        left_index = max(0, left_index)
        right_index = min(len(self._data_list) - 1, right_index)
        if left_index > right_index or not self._data_list: return []
        return self._data_list[left_index : right_index + 1]

    def _recalculate_indicators(self):
        if not self._data_list: return
        if "SMA" in self.active_indicators:
            self.indicator_data["SMA"] = IndicatorMath.calculate_sma(self._data_list, self.active_indicators["SMA"].get("period", 14))
        if "VWAP" in self.active_indicators:
            self.indicator_data["VWAP"] = IndicatorMath.calculate_vwap(self._data_list)
            
    def add_indicator(self, name: str, params: dict = None):
        self.active_indicators[name] = params or {}
        self._recalculate_indicators()
        self.data_changed.emit()

    def remove_indicator(self, name: str):
        if name in self.active_indicators:
            del self.active_indicators[name]
            if name in self.indicator_data: del self.indicator_data[name]
            self.data_changed.emit()