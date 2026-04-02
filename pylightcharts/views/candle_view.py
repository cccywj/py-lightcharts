"""Candle (OHLC) rendering layer showing price action with wicks and bodies."""
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCore import Qt

from pylightcharts.views.base_view import BaseView
from pylightcharts.core.data_manager import DataManager
from pylightcharts.core.viewport import Viewport
from pylightcharts.math.coordinate import CoordinateEngine


class CandleView(BaseView):
    """Renders Open-High-Low-Close candlesticks for price action.
    
    Candlesticks consist of two parts:
    1. Wick (thin line): Connects the high and low prices
    2. Body (rectangle): Shows the relationship between open and close
       - Bullish (green): close >= open
       - Bearish (red): close < open
    
    This view performs automatic Y-axis scaling based on visible price range.
    """

    def __init__(self) -> None:
        """Initialize the candle view with bull/bear colors."""
        super().__init__()
        # These colors follow TradingView's default light theme
        self.bull_color = QColor("#089981")  # Green for up candles
        self.bear_color = QColor("#F23645")  # Red for down candles

    def draw(
        self,
        painter: QPainter,
        viewport: Viewport,
        data_manager: DataManager,
        chart_width: int,
        chart_height: int,
    ) -> None:
        """Render all visible candlesticks.
        
        See BaseView.draw() for parameter documentation.
        """
        data_list = data_manager.get_data_list()
        data_length = len(data_list)
        if data_length == 0:
            return

        # --- STEP 1: Determine which candles are visible on screen ---
        left_idx, right_idx = viewport.get_visible_indices(chart_width, data_length)
        visible_data = data_manager.get_visible_data(left_idx, right_idx)

        if not visible_data:
            return

        # --- STEP 2: Auto-scale Y-axis based on the high/low of visible candles ---
        # This ensures all data is visible without manual zoom/pan
        viewport.apply_auto_scale(visible_data)

        # --- STEP 3: Cache viewport state for fast coordinate math in the loop ---
        v_mid = viewport.view_mid_price
        v_range = viewport.view_price_range
        scroll = viewport.scroll_index_offset
        t_space = viewport.total_space
        r_blank = viewport.right_blank_space
        c_width = viewport.candle_width
        tf_sec = data_manager.timeframe

        # --- STEP 4: Draw candles from right to left (newest to oldest) ---
        # This order allows early exit when we scroll off the left edge
        for i in range(right_idx, left_idx - 1, -1):
            if i < 0 or i >= data_length:
                continue

            d = data_list[i]

            # --- Coordinate Transformation ---
            # X from bar time so candles align with time-based grid lines
            x_center = CoordinateEngine.index_to_x(
                i, 
                data_length, 
                scroll, 
                t_space, 
                r_blank, 
                chart_width)

            # Stop drawing if we've scrolled off the left edge
            if x_center + (c_width / 2.0) < 0:
                break

            # Convert OHLC prices to pixel Y coordinates
            y_open = CoordinateEngine.price_to_y(d["open"], v_mid, v_range, chart_height)
            y_close = CoordinateEngine.price_to_y(
                d["close"], v_mid, v_range, chart_height
            )
            y_high = CoordinateEngine.price_to_y(d["high"], v_mid, v_range, chart_height)
            y_low = CoordinateEngine.price_to_y(d["low"], v_mid, v_range, chart_height)

            # --- Rendering ---
            # Determine bull/bear coloring based on open/close relationship
            is_bull = d["close"] >= d["open"]
            color = self.bull_color if is_bull else self.bear_color

            painter.setPen(QPen(color, 1))
            painter.setBrush(color)

            # Draw the wick (thin line from high to low)
            painter.drawLine(int(x_center), int(y_high), int(x_center), int(y_low))

            # Draw the body (rectangle from open to close, or close to open if bearish)
            rect_x, rect_y, rect_w, rect_h = CoordinateEngine.get_candle_rect(
                x_center, y_open, y_close, c_width
            )
            painter.fillRect(int(rect_x), int(rect_y), int(rect_w), int(rect_h), color)