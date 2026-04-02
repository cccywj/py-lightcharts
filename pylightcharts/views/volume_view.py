"""Volume bars rendering layer showing trading volume per candle."""
from PySide6.QtGui import QPainter, QColor

from pylightcharts.views.base_view import BaseView
from pylightcharts.core.data_manager import DataManager
from pylightcharts.core.viewport import Viewport
from pylightcharts.math.coordinate import CoordinateEngine


class VolumeView(BaseView):
    """Renders volume bars at the bottom of the chart.
    
    Volume is displayed as vertical bars with automatic scaling based on
    the maximum volume in the visible range. Colors match the candle direction:
    - Bullish volume (green): Volume on candles where close >= open
    - Bearish volume (red): Volume on candles where close < open
    
    Volume bars are semi-transparent (alpha=120) to sit subtly behind other layers.
    This view is optional and toggled via the toolbar indicator selector.
    """

    def __init__(self) -> None:
        """Initialize the volume view with semi-transparent bull/bear colors."""
        super().__init__()
        # Semi-transparent colors (alpha=120) for subtle background effect
        self.bull_color = QColor(8, 153, 129, 120)  # Transparent green
        self.bear_color = QColor(242, 54, 69, 120)  # Transparent red
        self.visible = False  # Toggle via toolbar

    def draw(
        self,
        painter: QPainter,
        viewport: Viewport,
        data_manager: DataManager,
        chart_width: int,
        chart_height: int,
    ) -> None:
        """Render volume bars for all visible candles.
        
        See BaseView.draw() for parameter documentation.
        """
        if not self.visible:
            return

        data_list = data_manager.get_data_list()
        data_length = len(data_list)
        if data_length == 0:
            return

        left_idx, right_idx = viewport.get_visible_indices(chart_width, data_length)
        visible_data = data_manager.get_visible_data(left_idx, right_idx)
        if not visible_data:
            return

        # --- STEP 1: Find the maximum volume in the visible range ---
        # Volume bars are scaled relative to this maximum for auto-scaling
        max_vol = max((d.get("volume", 0) for d in visible_data), default=1)
        if max_vol == 0:
            max_vol = 1  # Avoid division by zero

        # Volume bars occupy at most 20% of the chart height
        max_height_px = chart_height * 0.20
        base_y = chart_height  # Bottom of chart

        # Cache viewport parameters for coordinate math
        scroll = viewport.scroll_index_offset
        t_space = viewport.total_space
        r_blank = viewport.right_blank_space
        tf_sec = data_manager.timeframe

        # --- STEP 2: Draw volume bars for all visible candles ---
        for i in range(right_idx, left_idx - 1, -1):
            if i < 0 or i >= data_length:
                continue
            d = data_list[i]
            vol = d.get("volume", 0)
            if vol <= 0:
                continue  # Skip candles with no volume

            # Scale volume proportionally to the maximum
            h_px = (vol / max_vol) * max_height_px

            x_center = CoordinateEngine.index_to_x(
                i, 
                data_length, 
                scroll, 
                t_space, 
                r_blank, 
                chart_width)
            if x_center + (viewport.candle_width / 2.0) < 0:
                break  # Stop drawing when off the left edge

            # Get rectangle coordinates from base_y up to the bar height
            rect_x, rect_y, rect_w, rect_h = CoordinateEngine.get_candle_rect(
                x_center, base_y - h_px, base_y, viewport.candle_width
            )

            # Color based on bull/bear
            color = self.bull_color if d["close"] >= d["open"] else self.bear_color
            painter.fillRect(int(rect_x), int(rect_y), int(rect_w), int(rect_h), color)