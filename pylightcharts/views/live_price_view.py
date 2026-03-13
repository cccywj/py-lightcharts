from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt

from pylightcharts.views.base_view import BaseView
from pylightcharts.math.coordinate import CoordinateEngine

class LivePriceView(BaseView):
    def __init__(self):
        super().__init__()
        self.bull_color = QColor("#089981") # TradingView Green
        self.bear_color = QColor("#F23645") # TradingView Red
        self.text_color = QColor(Qt.white)
        self.font = QFont("Trebuchet MS", 9, QFont.Bold)

    def draw(self, painter: QPainter, viewport, data_manager, chart_width: int, chart_height: int):
        data_list = data_manager.get_data_list()
        if not data_list:
            return
            
        # Get the absolute latest candle
        latest_candle = data_list[-1]
        last_price = latest_candle['close']
        
        # Calculate its physical Y coordinate
        y = CoordinateEngine.price_to_y(
            last_price, viewport.view_mid_price, viewport.view_price_range, chart_height
        )
        
        # Only draw if the price is vertically visible on the screen
        if 0 <= y <= chart_height:
            is_bull = latest_candle['close'] >= latest_candle['open']
            color = self.bull_color if is_bull else self.bear_color
            
            # 1. Draw the dashed line across the chart
            painter.setPen(QPen(color, 1, Qt.DashLine))
            painter.drawLine(0, int(y), chart_width, int(y))
            
            # 2. Draw the filled price tag background on the Y-Axis margin
            label_width = viewport.margin_right - 8
            painter.fillRect(chart_width, int(y) - 10, label_width, 20, color)
            
            # 3. Draw the white price text
            prec = data_manager.price_precision
            painter.setPen(QPen(self.text_color))
            painter.setFont(self.font)
            painter.drawText(chart_width + 5, int(y) + 4, f"{last_price:.{prec}f}")