"""
Coordinate system translation engine for financial charts.

This module provides pure mathematical transformations between:
- Data space (price values, array indices) and pixel space (X, Y screen coordinates)
- This decouples rendering logic from viewport calculations
"""

import bisect
import math
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator, List, Tuple

class CoordinateEngine:
    """
    Mathematical translation layer for coordinate transformations.
    
    Converts between logical data/price values and physical X/Y pixel coordinates in both directions.
    This layer is viewport-agnostic and deals purely with math, making it easily testable.
    
    Attributes:
        None - this is a stateless utility class with only static methods.
    
    Methods:
        price_to_y: Convert a price value to Y-pixel coordinate
        y_to_price: Convert Y-pixel coordinate to price value
        index_to_x: Convert data array index to X-pixel coordinate
        x_to_index: Convert X-pixel coordinate to data array index
        get_candle_rect: Calculate rectangle bounds for a candlestick body
        calculate_nice_step: Generate human-readable grid intervals
    """

    # ==========================================
    # Y-AXIS: PRICE <-> PIXEL
    # ==========================================

    @staticmethod
    def price_to_y(price: float, view_mid_price: float, view_price_range: float, chart_height: int) -> float:
        """
        Converts a price value to a Y-axis pixel coordinate.
        
        In Qt/PySide6, Y=0 is at the top of the screen and increases downward.
        This method inverts the price scale so higher prices appear higher on screen.
        
        Args:
            price: The price value to convert (e.g., 150.25)
            view_mid_price: The midpoint price currently visible on screen
            view_price_range: The total price range currently visible (e.g., 10.0 for a 10-dollar range)
            chart_height: Height of the chart area in pixels
        
        Returns:
            float: Y-pixel coordinate (0 at top, chart_height at bottom)
        
        Examples:
            >>> CoordinateEngine.price_to_y(150.0, 150.0, 10.0, 800)
            400.0  # Midpoint
            >>> CoordinateEngine.price_to_y(155.0, 150.0, 10.0, 800)
            0.0    # Top of screen (height = 5 dollars above mid)
        """
        if view_price_range <= 0 or chart_height <= 0:
            return 0.0
            
        display_min = view_mid_price - (view_price_range / 2.0)
        normalized_position = (price - display_min) / view_price_range
        
        # Invert because UI coordinates go down, but price goes up
        return chart_height - (normalized_position * chart_height)

    @staticmethod
    def y_to_price(y: float, view_mid_price: float, view_price_range: float, chart_height: int) -> float:
        """
        Converts a Y-axis pixel coordinate (from mouse hover) back into a price value.
        
        This is the inverse of price_to_y(), used when the user hovers/clicks on the chart.
        
        Args:
            y: The pixel Y-coordinate (0 at top, chart_height at bottom)
            view_mid_price: The midpoint price currently visible on screen
            view_price_range: The total price range currently visible
            chart_height: Height of the chart area in pixels
        
        Returns:
            float: The price value at the given Y-pixel position
        
        Examples:
            >>> CoordinateEngine.y_to_price(400, 150.0, 10.0, 800)
            150.0  # Midpoint
            >>> CoordinateEngine.y_to_price(0, 150.0, 10.0, 800)
            155.0  # Top of screen
        """
        if view_price_range <= 0 or chart_height <= 0:
            return 0.0
            
        display_min = view_mid_price - (view_price_range / 2.0)
        normalized_position = (chart_height - y) / chart_height
        
        return display_min + (normalized_position * view_price_range)

    # ==========================================
    # X-AXIS: INDEX <-> PIXEL
    # ==========================================

    @staticmethod
    def index_to_x(index: int, data_length: int, scroll_offset: float, total_candle_space: float, 
                   right_blank_space: float, chart_width: int) -> float:
        """
        Converts a data array index to an X-axis pixel coordinate.
        
        The returned coordinate is the exact CENTER of the candlestick.
        Right-anchored: the latest candle (index = data_length - 1) is always on the right side.
        
        Args:
            index: Data array index (0 = oldest, data_length-1 = newest)
            data_length: Total number of candles in the dataset
            scroll_offset: How many candles the view has been panned left (floating-point)
            total_candle_space: Width of one candle + spacing (candle_width + spacing)
            right_blank_space: Padding on the right side of the chart (for price labels)
            chart_width: Total width of the chart area in pixels
        
        Returns:
            float: X-pixel coordinate of the candle's center
        
        Note:
            - Negative X means the candle is off the left edge of the screen
            - X > chart_width - right_blank_space means off the right edge
            - When data_length is 0, index is virtual (same formula with latest at -1)
        """
        # The exact center X pixel of the absolute latest candlestick
        right_anchor_x = chart_width - right_blank_space - (total_candle_space / 2.0)
        
        # How many candles from the latest? Subtract scroll for panning
        candles_from_right = (data_length - 1 - index) - scroll_offset
        
        return right_anchor_x - (candles_from_right * total_candle_space)

    @staticmethod
    def x_to_index(x: float, data_length: int, scroll_offset: float, total_candle_space: float, 
                   right_blank_space: float, chart_width: int) -> int:
        """
        Converts an X-pixel coordinate to the nearest data array index.
        
        This reverses index_to_x(), used when the user hovers/clicks on the chart.
        The returned index is rounded to the nearest candle.
        
        Args:
            x: The pixel X-coordinate
            data_length: Total number of candles in the dataset
            scroll_offset: Current pan offset in candles
            total_candle_space: Width of one candle + spacing
            right_blank_space: Padding on the right side
            chart_width: Width of chart area in pixels
        
        Returns:
            int: Data array index (clamped to [0, data_length-1])
        
        Examples:
            >>> # If the latest candle is at x=900, this returns data_length-1
            >>> CoordinateEngine.x_to_index(900, 300, 0, 10, 100, 1000)
            299
        """
        if total_candle_space <= 0:
            return -1

        right_anchor_x = chart_width - right_blank_space - (total_candle_space / 2.0)
        
        # How many candles away from the anchor is this pixel?
        candles_from_right = (right_anchor_x - x) / total_candle_space
        
        # Reverse the math to find the exact float index, then round
        last_idx = (data_length - 1) if data_length > 0 else -1
        exact_index = last_idx - scroll_offset - candles_from_right
        
        return int(round(exact_index))

    @staticmethod
    def x_to_float_index(
        x: float,
        data_length: int,
        scroll_offset: float,
        total_candle_space: float,
        right_blank_space: float,
        chart_width: int,
    ) -> float:
        """
        Same as x_to_index but returns fractional index (no rounding).
        Used for time-aligned grid lines and mapping visible time range.
        """
        if total_candle_space <= 0:
            return 0.0
        right_anchor_x = chart_width - right_blank_space - (total_candle_space / 2.0)
        candles_from_right = (right_anchor_x - x) / total_candle_space
        last_idx = (data_length - 1) if data_length > 0 else -1.0
        return last_idx - scroll_offset - candles_from_right

    # ==========================================
    # TIME-ALIGNED X GRID (calendar clock ticks)
    # ==========================================

    # Seconds: sub-minute, 1m, 2m, 5m, 10m, 15m, 30m, 1h–12h, 1d, 2d, 1w
    _TIME_GRID_STEP_CANDIDATES: Tuple[int, ...] = (
        1,
        5,
        10,
        15,
        30,
        60,
        120,
        300,
        600,
        900,
        1800,
        3600,
        7200,
        14400,
        21600,
        28800,
        43200,
        86400,
        172800,
        604800,
    )

    @staticmethod
    def choose_time_grid_step_seconds(
        span_seconds: float, chart_width: int, min_px: float = 80.0
    ) -> int:
        """
        Pick a nice wall-clock step (1m, 5m, 15m, 1h, …) so grid lines stay
        roughly min_px apart given the visible time span and chart width.
        """
        if chart_width <= 0:
            return 900
        if span_seconds <= 0:
            return 60
        min_step = span_seconds * (min_px / float(chart_width))
        for step in CoordinateEngine._TIME_GRID_STEP_CANDIDATES:
            if step >= min_step:
                return step
        return CoordinateEngine._TIME_GRID_STEP_CANDIDATES[-1]

    @staticmethod
    def floor_time_to_grid_step(dt: datetime, step_seconds: float) -> datetime:
        """
        Floor a datetime to the start of the current grid interval in local clock time
        (e.g. 9:17 with 15m step -> 9:15). For multi-day steps, uses unix alignment.
        """
        if step_seconds <= 0:
            return dt
        if step_seconds < 86400:
            midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            sec = (dt - midnight).total_seconds()
            floored = (int(sec // step_seconds)) * step_seconds
            return midnight + timedelta(seconds=floored)
        if step_seconds == 86400:
            d = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            if dt < d:
                d -= timedelta(days=1)
            return d
        ts = dt.timestamp()
        floored_ts = int(ts // int(step_seconds)) * int(step_seconds)
        return datetime.fromtimestamp(floored_ts)

    @staticmethod
    def iter_aligned_time_ticks(
        t_left: datetime, t_right: datetime, step_seconds: float
    ) -> Iterator[datetime]:
        """Yield wall-clock aligned times from t_left through t_right (inclusive)."""
        if t_left > t_right:
            t_left, t_right = t_right, t_left
        t = CoordinateEngine.floor_time_to_grid_step(t_left, step_seconds)
        step_td = timedelta(seconds=step_seconds)
        if t < t_left:
            t += step_td
        while t <= t_right:
            yield t
            t += step_td

    @staticmethod
    def time_to_float_index(
        t: datetime, data_list: List[Dict[str, Any]], tf_seconds: int
    ) -> float:
        """
        Map a wall time to a fractional bar index using linear interpolation
        between adjacent candles (extrapolate with average bar width or tf).
        Bar open times that match a candle exactly snap to that integer index so
        candles, grid, and axis share one consistent X mapping.
        """
        n = len(data_list)
        if n == 0:
            return 0.0
        times = [d["time"] for d in data_list]

        # Snap bucketed bar times to their bar index (avoids drift vs index_to_x)
        tol = max(1e-6, min(1.0, float(tf_seconds) * 1e-6))
        j = bisect.bisect_left(times, t)
        for cand in (j, j - 1):
            if 0 <= cand < n and abs((t - times[cand]).total_seconds()) <= tol:
                return float(cand)

        def avg_bar_seconds() -> float:
            if n >= 2:
                return max((times[-1] - times[0]).total_seconds() / float(n - 1), 1.0)
            return max(float(tf_seconds), 1.0)

        s = avg_bar_seconds()
        if t <= times[0]:
            return (t - times[0]).total_seconds() / s
        if t >= times[-1]:
            return (n - 1) + (t - times[-1]).total_seconds() / s
        i = bisect.bisect_right(times, t) - 1
        i = max(0, min(i, n - 2))
        t0, t1 = times[i], times[i + 1]
        dt_sec = (t1 - t0).total_seconds()
        if dt_sec <= 0:
            return float(i)
        frac = (t - t0).total_seconds() / dt_sec
        return float(i) + frac

    @staticmethod
    def float_index_to_time(
        idx: float, data_list: List[Dict[str, Any]], tf_seconds: int
    ) -> datetime:
        """Inverse of time_to_float_index: fractional index -> interpolated datetime."""
        n = len(data_list)
        if n == 0:
            return datetime.now()
        times = [d["time"] for d in data_list]

        def avg_bar_seconds() -> float:
            if n >= 2:
                return max((times[-1] - times[0]).total_seconds() / float(n - 1), 1.0)
            return max(float(tf_seconds), 1.0)

        s = avg_bar_seconds()
        if idx <= 0:
            return times[0] + timedelta(seconds=idx * s)
        if idx >= n - 1:
            return times[-1] + timedelta(seconds=(idx - (n - 1)) * s)
        i = int(math.floor(idx))
        i = max(0, min(i, n - 2))
        frac = idx - float(i)
        t0, t1 = times[i], times[i + 1]
        return t0 + timedelta(seconds=(t1 - t0).total_seconds() * frac)

    @staticmethod
    def time_to_x(
        t: datetime,
        data_list: List[Dict[str, Any]],
        tf_seconds: int,
        data_length: int,
        scroll_offset: float,
        total_candle_space: float,
        right_blank_space: float,
        chart_width: int,
    ) -> float:
        """Pixel X for a wall time (fractional index -> same path as index_to_x)."""
        idx = CoordinateEngine.time_to_float_index(t, data_list, tf_seconds)
        return CoordinateEngine.index_to_x(
            idx,
            data_length,
            scroll_offset,
            total_candle_space,
            right_blank_space,
            chart_width,
        )

    @staticmethod
    def format_time_axis_label(dt: datetime, step_seconds: float) -> str:
        """Format a tick time for the X axis based on grid step size."""
        if step_seconds >= 86400:
            return dt.strftime("%Y-%m-%d")
        if step_seconds >= 3600:
            return dt.strftime("%H:%M")
        if step_seconds >= 60:
            return dt.strftime("%H:%M")
        return dt.strftime("%H:%M:%S")

    # ==========================================
    # HELPER METHODS
    # ==========================================

    @staticmethod
    def get_candle_rect(center_x: float, open_y: float, close_y: float, candle_width: float) -> Tuple[float, float, float, float]:
        """
        Calculate the bounding rectangle for a candlestick body.
        
        Creates the rectangle needed for QPainter.fillRect() to draw the main OHLC body
        (not including the wick). The rectangle is centered on center_x and spans from
        the open to close price on the Y-axis.
        
        Args:
            center_x: The X-pixel center of the candlestick
            open_y: The Y-pixel coordinate of the open price
            close_y: The Y-pixel coordinate of the close price
            candle_width: Width of the candlestick in pixels
        
        Returns:
            Tuple[float, float, float, float]: (x, y, width, height) for the rectangle
        
        Note:
            - The height is guaranteed to be at least 1 pixel, even for doji candles
            - Doji handling ensures they remain visible (not collapsed to 0 pixels)
        
        Examples:
            >>> CoordinateEngine.get_candle_rect(100, 200, 180, 8)
            (96.0, 180, 8, 20)  # x, y, width, height
        """
        rect_x = center_x - (candle_width / 2.0)
        rect_y = min(open_y, close_y)
        rect_height = max(abs(open_y - close_y), 1.0)  # Guarantee at least 1px height for visibility
        
        return rect_x, rect_y, candle_width, rect_height
    
    @staticmethod
    def calculate_nice_step(price_range: float, max_ticks: int = 5) -> float:
        """
        Calculate human-readable grid intervals for axis labels and grid lines.
        
        This algorithm generates "nice" step sizes like 0.1, 0.5, 1, 2, 5, 10, 50, 100, etc.
        that are pleasant for human reading, rather than arbitrary floating-point values.
        
        It uses a decade-based algorithm:
        - Find the order of magnitude of the rough step
        - Snap the normalized step to a nice multiplier (1, 2, 5, or 10)
        
        Args:
            price_range: The total price range to divide (e.g., 120.0 for a chart showing $120)
            max_ticks: Desired maximum number of grid lines (default 5, actual may be ±1)
        
        Returns:
            float: A human-readable step size that divides the price_range evenly
        
        Examples:
            >>> CoordinateEngine.calculate_nice_step(100.0, 5)
            20.0  # 5 grid lines at $20 intervals
            >>> CoordinateEngine.calculate_nice_step(0.5, 5)
            0.1   # 5 grid lines at $0.10 intervals
            >>> CoordinateEngine.calculate_nice_step(0.0025, 5)
            0.0005  # Very small ranges (penny stocks, crypto)
        """
        if price_range <= 0 or (price_range / max_ticks) <= 1e-12:
            return 1.0
        
        rough_step = price_range / max_ticks
        
        # Find the power of 10 magnitude (e.g., 100, 10, 1, 0.1, 0.01)
        magnitude = math.pow(10, math.floor(math.log10(rough_step)))
        normalized_step = rough_step / magnitude
        
        # Snap the normalized step to one of the nice multipliers
        if normalized_step < 1.5:
            nice_multiplier = 1.0
        elif normalized_step < 3.0:
            nice_multiplier = 2.0
        elif normalized_step < 7.0:
            nice_multiplier = 5.0
        else:
            nice_multiplier = 10.0
            
        return nice_multiplier * magnitude