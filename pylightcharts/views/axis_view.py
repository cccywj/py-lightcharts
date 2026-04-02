"""Axis view renders price (Y-axis) and time (X-axis) labels with grid dividers."""
import math

from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt

from pylightcharts.views.base_view import BaseView
from pylightcharts.core.data_manager import DataManager
from pylightcharts.core.viewport import Viewport
from pylightcharts.math.coordinate import CoordinateEngine


class AxisView(BaseView):
    """Renders Y-axis price labels and X-axis time labels with frame borders.
    
    This view handles two independent tasks:
    1. Right margin Y-axis: Price level labels with automatic tick spacing
    2. Bottom margin X-axis: Time labels on wall-clock aligned grid (1m, 5m, 15m, …)
    
    The axis uses "nice" step values to ensure labels are round numbers and
    don't overlap, providing a clean professional appearance.
    """

    def __init__(self) -> None:
        """Initialize the axis view with styling colors and fonts."""
        super().__init__()
        self.text_color = QColor("#B2B5BE")  # Light gray text
        self.axis_line_color = QColor("#2A2E39")  # Dark gray dividers
        self.font = QFont("Trebuchet MS", 9)  # TradingView-style font

    def draw(
        self,
        painter: QPainter,
        viewport: Viewport,
        data_manager: DataManager,
        chart_width: int,
        chart_height: int,
    ) -> None:
        """Render all axis labels and frame dividers.
        
        See BaseView.draw() for parameter documentation.
        """
        painter.setFont(self.font)
        v_mid = viewport.view_mid_price
        v_range = viewport.view_price_range

        # --- STEP 1: Draw Frame Borders (dividing chart from margins) ---
        painter.setPen(QPen(self.axis_line_color, 1, Qt.SolidLine))
        # Vertical divider line
        # painter.drawLine(chart_width, 0, chart_width, chart_height)
        # Horizontal divider line (draws all the way across the widget including the margin)
        painter.drawLine(0, chart_height, chart_width + viewport.margin_right, chart_height)
        
        # --- STEP 2: Draw Y-Axis Text (Price levels on right margin) ---
        painter.setPen(self.text_color)
        display_min = v_mid - (v_range / 2.0)  # Bottom price of viewport
        display_max = v_mid + (v_range / 2.0)  # Top price of viewport

        # Choose tick spacing so labels don't overlap (50px minimum between ticks)
        desired_tick_px = 50
        max_ticks = max(2, min(10, int(chart_height / desired_tick_px)))

        # Calculate a "nice" step value (e.g., 0.5, 1.0, 5.0, 10.0)
        step = CoordinateEngine.calculate_nice_step(v_range, max_ticks)

        # Align ticks to multiples of the step value for professional appearance
        first_tick = math.floor(display_min / step) * step
        last_tick = math.ceil(display_max / step) * step
        num_ticks = int(round((last_tick - first_tick) / step)) + 1

        # Format labels using the data manager's price precision
        prec = data_manager.price_precision
        text_rect_width = max(0, viewport.margin_right - 10)

        for i in range(num_ticks):
            price = first_tick + (i * step)
            price = round(price, prec)  # Avoid floating point artifacts
            y_pixel = CoordinateEngine.price_to_y(price, v_mid, v_range, chart_height)

            if 0 <= y_pixel <= chart_height:
                # Draw price label right-aligned in the margin
                label_rect = (chart_width + 5, int(y_pixel) - 8, text_rect_width, 16)
                painter.drawText(
                    *label_rect,
                    Qt.AlignRight | Qt.AlignVCenter,
                    f"{price:.{prec}f}",
                )

        # --- STEP 3: Draw X-Axis Text (Time labels on bottom margin) ---
        data_list = data_manager.get_data_list()
        data_length = len(data_list)
        if data_length == 0:
            return

        scroll = viewport.scroll_index_offset
        t_space = viewport.total_space
        r_blank = viewport.right_blank_space
        tf_sec = data_manager.timeframe

        i0 = CoordinateEngine.x_to_float_index(
            0, data_length, scroll, t_space, r_blank, chart_width
        )
        i1 = CoordinateEngine.x_to_float_index(
            chart_width, data_length, scroll, t_space, r_blank, chart_width
        )
        t0 = CoordinateEngine.float_index_to_time(i0, data_list, tf_sec)
        t1 = CoordinateEngine.float_index_to_time(i1, data_list, tf_sec)
        span_sec = abs((t1 - t0).total_seconds())
        step_sec = float(
            CoordinateEngine.choose_time_grid_step_seconds(span_sec, chart_width)
        )

        for tick in CoordinateEngine.iter_aligned_time_ticks(t0, t1, step_sec):
            x = CoordinateEngine.time_to_x(
                tick,
                data_list,
                tf_sec,
                data_length,
                scroll,
                t_space,
                r_blank,
                chart_width,
            )
            if 0 <= x <= chart_width:
                time_str = CoordinateEngine.format_time_axis_label(tick, step_sec)
                painter.drawText(int(x) - 25, chart_height + 20, time_str)