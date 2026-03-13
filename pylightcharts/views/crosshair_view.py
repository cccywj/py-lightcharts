from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt, QRect

from pylightcharts.views.base_view import BaseView
from pylightcharts.core.data_manager import DataManager
from pylightcharts.core.viewport import Viewport
from pylightcharts.math.coordinate import CoordinateEngine

class CrosshairView(BaseView):
    def __init__(self):
        super().__init__()
        self.crosshair_color = QColor("#9598A1")
        self.label_bg_color = QColor("#2A2E39")
        self.text_color = QColor(Qt.white)
        self.font = QFont("Trebuchet MS", 9)

    def _get_time_format(self, tf_seconds: int) -> str:
        if tf_seconds >= 86400: return '%Y-%m-%d'
        elif tf_seconds >= 60: return '%H:%M'
        else: return '%H:%M:%S'

    def draw(self, painter: QPainter, viewport: Viewport, data_manager: DataManager, 
             chart_width: int, chart_height: int):
        
        # Don't draw if crosshair is hidden or if mouse is in the margins
        if not viewport.crosshair_visible: return
        if viewport.crosshair_x > chart_width or viewport.crosshair_y > chart_height: return
        
        data_list = data_manager.get_data_list()
        data_length = len(data_list)
        if data_length == 0: return

        # 1. Reverse-engineer the mouse X pixel into a Data Index
        hovered_idx = CoordinateEngine.x_to_index(
            viewport.crosshair_x, data_length, viewport.scroll_index_offset, 
            viewport.total_space, viewport.right_blank_space, chart_width
        )
        
        # Clamp index to available data
        hovered_idx = max(0, min(data_length - 1, hovered_idx))
        
        # 2. Convert that Index back into a perfectly centered X pixel (Magnetic Snapping)
        snap_x = CoordinateEngine.index_to_x(
            hovered_idx, data_length, viewport.scroll_index_offset, 
            viewport.total_space, viewport.right_blank_space, chart_width
        )

        painter.setFont(self.font)
        
        # --- Draw Dashed Lines ---
        painter.setPen(QPen(self.crosshair_color, 1, Qt.DashLine))
        painter.drawLine(int(snap_x), 0, int(snap_x), chart_height)
        painter.drawLine(0, int(viewport.crosshair_y), chart_width, int(viewport.crosshair_y))
        
        # --- Draw Y-Axis Price Label ---
        hover_price = CoordinateEngine.y_to_price(
            viewport.crosshair_y, viewport.view_mid_price, 
            viewport.view_price_range, chart_height
        )

        label_width = viewport.margin_right - 8
        painter.fillRect(chart_width, int(viewport.crosshair_y) - 10, label_width, 20, self.label_bg_color)
        prec = data_manager.price_precision
        painter.setPen(QPen(self.text_color))
        painter.drawText(chart_width + 5, int(viewport.crosshair_y) + 4, f"{hover_price:.{prec}f}")

        # --- Draw X-Axis Time Label ---
        time_fmt = self._get_time_format(data_manager.timeframe)
        time_str = data_list[hovered_idx]['time'].strftime(time_fmt)
        
        painter.fillRect(int(snap_x) - 35, chart_height, 70, viewport.margin_bottom, self.label_bg_color)
        painter.setPen(QPen(self.text_color))
        painter.drawText(int(snap_x) - 30, chart_height + 18, time_str)