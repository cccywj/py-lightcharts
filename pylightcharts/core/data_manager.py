"""
Data management and aggregation engine for financial charting.

Handles:
- OHLCV (Open, High, Low, Close, Volume) data storage and management
- Timeframe-based bar aggregation from live tick data
- Indicator calculations (SMA, VWAP, etc.)
- Data buffering for gapless merging of historical + live data
- Support for both ib_async and plain dictionary data formats
"""

import datetime
import math
from typing import List, Dict, Any, Optional, Union
from PySide6.QtCore import QObject, Signal

class DataManager(QObject):
    """
    Core data management system for the charting library.
    
    Responsibilities:
    - Stores and updates OHLCV candle data
    - Converts incoming live ticks into aggregated OHLCV bars
    - Manages indicator calculations
    - Handles gapless data merging (historical + live ticks)
    - Enforces data capacity limits
    - Supports multiple data sources (ib_async, plain dicts, custom objects)
    
    Signal:
        data_changed: Emitted whenever data is modified, triggering UI updates
    
    Attributes:
        price_precision: Number of decimal places for price display (auto-detected)
    
    Examples:
        >>> dm = DataManager(timeframe_seconds=60)
        >>> dm.update_tick({"bid": 150.1, "ask": 150.3, "time": datetime.datetime.now()})
        >>> dm.add_indicator("SMA", {"period": 14})
        >>> dm.apply_historical_data([{"open": 150, "high": 151, ...}, ...])
    """
    
    # Qt Signal emitted whenever data changes (connected to view updates)
    data_changed = Signal()

    def __init__(self, timeframe_seconds: int = 60, max_capacity: int = 10000):
        """
        Initialize the DataManager.
        
        Args:
            timeframe_seconds: candlestick aggregation period in seconds (default 60 = 1 minute)
            max_capacity: Maximum number of candlesticks to store in memory (default 10000)
                         Older candles are discarded when the limit is exceeded.
        """
        super().__init__()
        self._data_list: List[Dict[str, Any]] = []
        self._timeframe_seconds = timeframe_seconds
        self._max_capacity = max_capacity
        self.price_precision = 2  # will auto-adjust based on price scale

        # Gapless buffering system
        self._is_buffering = False
        self._live_buffer: List[Dict[str, Any]] = []

    # ==========================================
    # PROPERTIES & SETTERS
    # ==========================================

    @property
    def timeframe(self) -> int:
        """Returns the current timeframe in seconds."""
        return self._timeframe_seconds

    def set_timeframe(self, tf_seconds: int) -> None:
        """
        Change the timeframe and reset all data.
        
        When the timeframe changes, all existing candles must be recalculated,
        so we clear the data and start fresh.
        
        Args:
            tf_seconds: New timeframe in seconds
        """
        self._timeframe_seconds = tf_seconds
        self.clear_data()

    def clear_data(self) -> None:
        """
        Clear all data, indicators, and buffering state.
        
        Called when:
        - Switching to a new symbol
        - Changing timeframe
        - User explicitly resets
        """
        self._data_list.clear()
        self._live_buffer.clear()
        self._is_buffering = False
        self.data_changed.emit()

    def get_data_list(self) -> List[Dict[str, Any]]:
        """
        Get the complete OHLCV data list.
        
        Returns:
            List of candles, newest at the end. Each candle is a dict with keys:
            {'time': datetime, 'open': float, 'high': float, 'low': float, 'close': float, 'volume': float/int}
        """
        return self._data_list

    # ==========================================
    # DATA SOURCE PARSING (Flexible Input Handling)
    # ==========================================

    def _ensure_utc_aware(self, dt: Optional[Union[datetime.datetime, datetime.date]]) -> datetime.datetime:
        """
        Ensure a datetime object is timezone-aware and in UTC.
        
        Handles multiple input formats:
        - datetime.date objects (converts to datetime with time 00:00:00)
        - Naive datetime (assumes UTC)
        - Timezone-aware datetime (converts to UTC)
        - None (returns current UTC time)
        
        Args:
            dt: A datetime, date, or None value
        
        Returns:
            datetime.datetime: Timezone-aware datetime in UTC
        """
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.time.min)
        if dt is None:
            return datetime.datetime.now(datetime.timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)

    def _floor_time_to_timeframe(self, dt: datetime.datetime) -> datetime.datetime:
        """
        Snap a bar open time to the start of its timeframe bucket in UTC.

        Matches live tick handling in update_tick() so historical and live candles
        share the same global bucket times for chart alignment.
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)
        ts = dt.timestamp()
        floored_ts = (ts // self._timeframe_seconds) * self._timeframe_seconds
        return datetime.datetime.fromtimestamp(floored_ts, tz=datetime.timezone.utc)

    def _parse_ib_bar(self, bar: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
        """
        Parse an OHLCV bar from ib_async.BarData or a plain dictionary.
        
        Supports:
        - ib_async.BarData objects
        - Plain dictionaries with 'open', 'high', 'low', 'close', 'volume' keys
        - Alternative keys: 'date' or 'time' for timestamps
        - Missing volume (defaults to 0)
        
        Args:
            bar: Either an ib_async.BarData object or a dict with OHLCV data
        
        Returns:
            Dict with standardized keys: {'time', 'open', 'high', 'low', 'close', 'volume'}
        
        Raises:
            Silently handles missing fields by using None or 0
        
        Examples:
            >>> # From dict
            >>> dm._parse_ib_bar({"date": "2024-01-15", "open": 150, "high": 152, ...})
            
            >>> # From ib_async.BarData
            >>> dm._parse_ib_bar(ib_bar_data_object)
        """
        if isinstance(bar, dict):
            raw_time = bar.get('date', bar.get('time'))
            if raw_time is None:
                raise ValueError("Historical bar data is missing a 'time' or 'date' key.")
            t = self._floor_time_to_timeframe(self._ensure_utc_aware(raw_time))
            return {
                "time": t,
                "open": float(bar.get('open', 0.0)),
                "high": float(bar.get('high', 0.0)),
                "low": float(bar.get('low', 0.0)),
                "close": float(bar.get('close', 0.0)),
                "volume": float(bar.get('volume', 0.0))
            }
        else:
            # ib_async.BarData object: use getattr with fallbacks
            raw_time = getattr(bar, 'date', getattr(bar, 'time', None))
            if raw_time is None:
                raise ValueError("Historical bar data is missing a 'time' or 'date' key.")
            t = self._floor_time_to_timeframe(self._ensure_utc_aware(raw_time))
            return {
                "time": t,
                "open": float(getattr(bar, 'open', 0.0)),
                "high": float(getattr(bar, 'high', 0.0)),
                "low": float(getattr(bar, 'low', 0.0)),
                "close": float(getattr(bar, 'close', 0.0)),
                "volume": float(getattr(bar, 'volume', 0.0))
            }

    def _parse_tick(self, tick: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
        """
        Parse a single market tick into a mini OHLC bar.
        
        Tick ticks represent a single price point in time. This method converts them into
        a degenerate OHLCV bar (open == high == low == close) by using the midpoint of
        the bid/ask spread when available.
        
        Supports:
        - ib_async.Ticker objects (with bid, ask, lastSize, etc.)
        - Plain dictionaries with 'bid', 'ask', 'price', and optional 'volume'
        - Fallback to last trade price if bid/ask unavailable
        - NaN/None handling (skips invalid values)
        
        Args:
            tick: Either an ib_async.Ticker or a dict with market tick data
        
        Returns:
            Dict with structure like a candlestick (all OHLC the same):
            {'time': datetime, 'open': price, 'high': price, 'low': price, 'close': price, 'volume': vol}
        
        Note:
            - Invalid prices (None, NaN, 0.0) are replaced with fallbacks
            - Volume defaults to 0 if missing or invalid
        """
        if isinstance(tick, dict):
            raw_time = tick.get('time')
            bid = tick.get('bid')
            ask = tick.get('ask')
            
            # Calculate midpoint or fallback to price
            if bid and ask and bid > 0 and ask > 0:
                price = (bid + ask) / 2.0
            else:
                price = tick.get('price', 0.0)
            
            vol = tick.get('volume', 0.0)
        else:
            # ib_async.Ticker object: extract bid/ask/lastSize with fallbacks
            raw_time = getattr(tick, 'time', None)
            
            bid = getattr(tick, 'bid', None)
            ask = getattr(tick, 'ask', None)
            
            # Validate bid/ask: not None, not NaN, and > 0
            if bid is not None and ask is not None and not math.isnan(bid) and not math.isnan(ask) and bid > 0 and ask > 0:
                price = (bid + ask) / 2.0
            else:
                # Fallback to last trade price
                price = getattr(tick, 'last', None)
                if price is None or price != price or price == 0.0:
                    # If still invalid, try 'close' field
                    price = getattr(tick, 'close', 0.0)
                    if price is None or price != price:
                        price = 0.0
            
            vol = getattr(tick, 'lastSize', getattr(tick, 'volume', None))
            if vol is None or vol != vol:  # NaN check
                vol = 0.0

        return {
            "time": self._ensure_utc_aware(raw_time),
            "open": float(price),
            "high": float(price),
            "low": float(price),
            "close": float(price),
            "volume": float(vol)
        }

    def _calculate_precision(self, price: float) -> int:
        """
        Determine appropriate decimal precision for displaying a price.
        
        Examines the price value and determines how many decimal places should be shown.
        This helps avoid displaying meaningless trailing zeros or excessive decimals.
        
        Args:
            price: A price value (e.g., 150.25 or 0.0001234567)
        
        Returns:
            int: Number of decimal places to display (min 2, max 8)
        
        Examples:
            >>> dm._calculate_precision(150.0)
            2  # Show as 150.00
            >>> dm._calculate_precision(0.001234)
            6  # Show as 0.001234
            >>> dm._calculate_precision(0.0000000001)
            8  # Max out at 8 decimal places
        """
        try:
            s = str(price)
            if 'e' in s.lower():  # Scientific notation (very small/large numbers)
                return 8
            if '.' in s:
                # Count significant decimals (strip trailing zeros)
                decimal_part = s.rstrip('0').split('.')[1]
                return min(max(len(decimal_part), 2), 8)
            return 2
        except (ValueError, IndexError, AttributeError):
            return 2

    # ==========================================
    # GAPLESS DATA PIPELINE
    # ==========================================

    def enable_buffering(self) -> None:
        """
        Enable buffering mode for gapless data merging.
        
        Call this before requesting historical data. It clears existing data and enables
        a buffer that will hold live ticks until historical data arrives. This ensures
        no price updates are lost during the network delay.
        
        Flow:
        1. enable_buffering() called
        2. Historical data request sent to broker/API
        3. Live ticks arrive and go into buffer (not rendered yet)
        4. Historical data arrives
        5. apply_historical_data() merges buffer with history
        6. Chart fully rendered with continuous data
        """
        self.clear_data()
        self._is_buffering = True

    def apply_historical_data(self, ib_bars: List[Union[Dict[str, Any], Any]]) -> None:
        """
        Load historical OHLCV data and merge with any buffered live ticks.
        
        This is the completion step for gapless data loading:
        - Parses the historical bars
        - Merges them with any live ticks that arrived during the download
        - Recalculates all indicators
        - Triggers UI update
        
        Args:
            ib_bars: List of bar data (dicts or ib_async.BarData objects)
        
        Note:
            - When merging, live ticks take precedence over historical close/high/low
            - Volumes are summated
            - Data is automatically capped at max_capacity
        
        Examples:
            >>> dm.enable_buffering()
            >>> # ... request and receive historical data ...
            >>> dm.apply_historical_data(bars_from_broker)
        """
        historical_data = [self._parse_ib_bar(b) for b in ib_bars]
        
        if self._is_buffering and self._live_buffer:
            # Merge strategy: historical data as base, live data updates close/HLVW
            merged_dict = {b['time']: b for b in historical_data}
            
            for live_bar in self._live_buffer:
                bt = live_bar['time']
                if bt in merged_dict:
                    # Same candle: live data updates the close, high, low, volume
                    hist_bar = merged_dict[bt]
                    hist_bar['close'] = live_bar['close']
                    hist_bar['high'] = max(hist_bar['high'], live_bar['high'])
                    hist_bar['low'] = min(hist_bar['low'], live_bar['low'])
                    hist_bar['volume'] += live_bar['volume']
                else:
                    # New candle from live data
                    merged_dict[bt] = live_bar
                
            # Sort by time
            self._data_list = sorted(merged_dict.values(), key=lambda x: x['time'])
            self._live_buffer.clear()
        else:
            # No buffering or no buffered data: just use historical
            self._data_list = historical_data

        # Enforce capacity limit
        if len(self._data_list) > self._max_capacity:
            self._data_list = self._data_list[-self._max_capacity:]
            
        # Update price precision based on latest price
        if self._data_list:
            self.price_precision = self._calculate_precision(self._data_list[-1]['close'])

        self._is_buffering = False
        self.data_changed.emit()

    def update_tick(self, tick: Union[Dict[str, Any], Any]) -> None:
        """
        Process a live market tick and aggregate into the current timeframe candle.
        
        This method:
        1. Parses the tick into an OHLC bar
        2. Rounds the time to the nearest candle boundary
        3. Either adds to buffer (if buffering) or updates/appends data array
        4. Recalculates indicators
        5. Triggers UI update
        
        Args:
            tick: Either an ib_async.Ticker or dict with bid/ask/volume data
        
        Note:
            - Invalid prices (0.0, None, NaN) are skipped silently
            - Time is snapped to candle boundaries (e.g., 14:32:45 -> 14:32:00 for 60s timeframe)
            - Older candles are dropped when max_capacity is exceeded
            - If buffering, ticks are queued; otherwise, they update the current candle
        
        Examples:
            >>> tick = {"time": datetime.now(), "bid": 150.1, "ask": 150.3, "volume": 100}
            >>> dm.update_tick(tick)
        """
        parsed_tick = self._parse_tick(tick)
        
        # Skip if price is invalid
        if not parsed_tick['close'] or parsed_tick['close'] == 0.0:
            return
            
        bucket_time = self._floor_time_to_timeframe(parsed_tick['time'])
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

        self.data_changed.emit()

    def get_visible_data(self, left_index: int, right_index: int) -> List[Dict[str, Any]]:
        """
        Get a slice of data for a visible range.
        
        Clamps indices to valid range and returns the sub-list of candles that fall within.
        Used by rendering layers to draw only what's on screen.
        
        Args:
            left_index: Starting index (inclusive)
            right_index: Ending index (inclusive)
        
        Returns:
            List of candles from left_index to right_index (or empty list if invalid range)
        
        Note:
            - Indices are clamped to [0, len(data_list)-1]
            - Returns empty list if range is invalid
        
        Examples:
            >>> dm.get_visible_data(10, 20)
            [{"time": ..., "open": ..., ...}, ...]
        """
        left_index = max(0, left_index)
        right_index = min(len(self._data_list) - 1, right_index)
        if left_index > right_index or not self._data_list:
            return []
        return self._data_list[left_index : right_index + 1]