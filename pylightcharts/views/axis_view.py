import math

from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt

from pylightcharts.views.base_view import BaseView
from pylightcharts.core.data_manager import DataManager
from pylightcharts.core.viewport import Viewport
from pylightcharts.math.coordinate import CoordinateEngine

class AxisView(BaseView):
    def __init__(self):
        super().__init__()
        self.text_color = QColor("#B2B5BE")
        self.axis_line_color = QColor("#2A2E39")
        self.font = QFont("Trebuchet MS", 9)

    def _get_time_format(self, tf_seconds: int) -> str:
        """Returns the appropriate datetime format based on the chart's timeframe."""
        if tf_seconds >= 86400: # Daily
            return '%Y-%m-%d'
        elif tf_seconds >= 60:  # Minute/Hourly
            return '%H:%M'
        else:                   # Seconds
            return '%H:%M:%S'

    def draw(self, painter: QPainter, viewport: Viewport, data_manager: DataManager, 
             chart_width: int, chart_height: int):
        
        painter.setFont(self.font)
        v_mid = viewport.view_mid_price
        v_range = viewport.view_price_range
        
        # --- 1. Draw the Frame Borders ---
        painter.setPen(QPen(self.axis_line_color, 1, Qt.SolidLine))
        # Vertical divider line
        painter.drawLine(chart_width, 0, chart_width, chart_height)
        # Horizontal divider line (draws all the way across the widget including the margin)
        painter.drawLine(0, chart_height, chart_width + viewport.margin_right, chart_height)
        
        # --- 2. Draw Y-Axis Text (Prices) ---
        painter.setPen(self.text_color)
        display_min = v_mid - (v_range / 2.0)
        display_max = v_mid + (v_range / 2.0)

        # Choose the number of ticks based on chart height so labels don't overlap
        desired_tick_px = 50
        max_ticks = max(2, min(10, int(chart_height / desired_tick_px)))

        step = CoordinateEngine.calculate_nice_step(v_range, max_ticks)

        # Align the first tick to a "nice" rounded value
        first_tick = math.floor(display_min / step) * step
        last_tick = math.ceil(display_max / step) * step
        num_ticks = int(round((last_tick - first_tick) / step)) + 1

        # Use price precision to format labels and avoid floating point artifacts
        prec = data_manager.price_precision
        text_rect_width = max(0, viewport.margin_right - 10)

        for i in range(num_ticks):
            price = first_tick + (i * step)
            price = round(price, prec)
            y_pixel = CoordinateEngine.price_to_y(price, v_mid, v_range, chart_height)

            if 0 <= y_pixel <= chart_height:
                label_rect = (chart_width + 5, int(y_pixel) - 8, text_rect_width, 16)
                painter.drawText(*label_rect, Qt.AlignRight | Qt.AlignVCenter, f"{price:.{prec}f}")

        # --- 3. Draw X-Axis Text (Times) ---
        data_list = data_manager.get_data_list()
        data_length = len(data_list)
        if data_length == 0:
            return
            
        left_idx, right_idx = viewport.get_visible_indices(chart_width, data_length)
        scroll = viewport.scroll_index_offset
        t_space = viewport.total_space
        r_blank = viewport.right_blank_space
        time_fmt = self._get_time_format(data_manager.timeframe)
        
        last_drawn_x = chart_width + 80
        
        for i in range(right_idx, left_idx - 1, -1):
            x_center = CoordinateEngine.index_to_x(i, data_length, scroll, t_space, r_blank, chart_width)
            
            if x_center < 0:
                break
                
            if last_drawn_x - x_center >= 80:
                time_str = data_list[i]['time'].strftime(time_fmt)
                painter.drawText(int(x_center) - 25, chart_height + 20, time_str)
                last_drawn_x = x_center