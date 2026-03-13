from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel
from PySide6.QtGui import QPainter, QWheelEvent, QColor
from PySide6.QtCore import Qt, QPoint, Signal

from pylightcharts.core.data_manager import DataManager
from pylightcharts.core.viewport import Viewport
from pylightcharts.toolbar import ChartToolbar
from pylightcharts.views.candle_view import CandleView
from pylightcharts.views.grid_view import GridView        
from pylightcharts.views.axis_view import AxisView
from pylightcharts.views.crosshair_view import CrosshairView
from pylightcharts.views.tooltip_view import TooltipView
from pylightcharts.views.indicator_view import IndicatorLineView
from pylightcharts.views.volume_view import VolumeView
from pylightcharts.views.live_price_view import LivePriceView

# ==========================================
# INTERNAL CANVAS (Handles the Drawing)
# ==========================================
class _ChartCanvas(QWidget):
    """Internal widget that strictly handles mouse events and rendering."""
    def __init__(self, data_manager: DataManager, viewport: Viewport):
        super().__init__()
        self.data_manager = data_manager
        self.viewport = viewport
        
        # 2. Initialize rendering layers
        self.grid_view = GridView()
        self.volume_view = VolumeView() 
        self.candle_view = CandleView()

        # --- Indicator Layers ---
        self.sma_view = IndicatorLineView("SMA", "#2962FF")   # Blue SMA line
        self.vwap_view = IndicatorLineView("VWAP", "#E0D714") # Yellow VWAP line
        
        self.axis_view = AxisView()
        self.live_price_view = LivePriceView()
        self.crosshair_view = CrosshairView()
        self.tooltip_view = TooltipView()
        
        # 3. Widget Configuration
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.bg_color = "#131722" # Background color
        
        # Interaction State
        self.drag_mode = None
        self.last_mouse_pos = QPoint()

    # ==========================================
    # PYSIDE6 EVENT HANDLERS
    # ==========================================
    def wheelEvent(self, event: QWheelEvent):
        zoom_step = 0.5 if event.angleDelta().y() > 0 else -0.5
        self.viewport.zoom_x(zoom_step)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            chart_w = self.width() - self.viewport.margin_right 
            chart_h = self.height() - self.viewport.margin_bottom
            
            # Simple hit testing for axis vs chart
            if pos.x() > chart_w and pos.y() < chart_h:
                self.drag_mode = 'y_axis'
            elif pos.x() < chart_w and pos.y() > chart_h:
                self.drag_mode = 'x_axis'
            else:
                self.drag_mode = 'chart'
            self.last_mouse_pos = pos

    def mouseDoubleClickEvent(self, event):
        # Reset auto-scale on double click in Y-Axis
        if event.position().toPoint().x() > (self.width() - self.viewport.margin_right):
            self.viewport.set_auto_scale(True)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        
        if self.drag_mode == 'chart':
            dx = pos.x() - self.last_mouse_pos.x()
            dy = pos.y() - self.last_mouse_pos.y()
            self.viewport.pan_x(dx, len(self.data_manager.get_data_list()))
            self.viewport.pan_y(dy, self.height() - self.viewport.margin_bottom)
            self.last_mouse_pos = pos
        elif self.drag_mode == 'x_axis':
            dx = pos.x() - self.last_mouse_pos.x()
            self.viewport.zoom_x(dx * 0.05)
            self.last_mouse_pos = pos
        elif self.drag_mode == 'y_axis':
            dy = pos.y() - self.last_mouse_pos.y()
            self.viewport.zoom_y(dy)
            self.last_mouse_pos = pos
        else:
            self.viewport.update_crosshair(pos.x(), pos.y())
            
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_mode = None

    def leaveEvent(self, event):
        self.viewport.hide_crosshair()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(self.bg_color))

        chart_w = w - self.viewport.margin_right
        chart_h = h - self.viewport.margin_bottom
        
        self.grid_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.volume_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h) 
        self.candle_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        
        self.sma_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.vwap_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        
        self.axis_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.live_price_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.crosshair_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.tooltip_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)


# ==========================================
# MAIN PUBLIC WIDGET (The "React-like" Component)
# ==========================================
class PyLightChartWidget(QWidget):
    
    # --- Hooks for the Main App ---
    historical_data_requested = Signal(str, int) 
    indicator_requested = Signal(str) 

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.data_manager = DataManager()
        self.viewport = Viewport()
        self.current_symbol = "AAPL" 
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.toolbar = ChartToolbar()
        self.main_layout.addWidget(self.toolbar)
        
        self.canvas = _ChartCanvas(self.data_manager, self.viewport)
        self.main_layout.addWidget(self.canvas)
        
        self.data_manager.data_changed.connect(self.canvas.update)
        self.viewport.viewport_changed.connect(self.canvas.update)
        
        self.toolbar.timeframe_changed.connect(self._handle_tf_changed)
        self.toolbar.indicator_requested.connect(self.toggle_indicator)

    def _handle_tf_changed(self, tf_seconds):
        self.data_manager.set_timeframe(tf_seconds)
        self.enable_buffering()
        self.historical_data_requested.emit(self.current_symbol, tf_seconds)

    # ==========================================
    # PUBLIC API
    # ==========================================
    def change_symbol(self, symbol: str):
        self.current_symbol = symbol
        self.enable_buffering()
        self.historical_data_requested.emit(symbol, self.data_manager.timeframe)

    def enable_buffering(self):
        self.data_manager.enable_buffering()

    def apply_historical_data(self, ib_bars: list):
        self.data_manager.apply_historical_data(ib_bars)

    def update_tick(self, ib_ticker):
        """Pass an ib_async.Ticker or raw dict directly in here."""
        self.data_manager.update_tick(ib_ticker)

    def set_timeframe(self, seconds):
        self.toolbar.set_timeframe(seconds)

    def toggle_indicator(self, ind_code: str):
        if ind_code == "VOL":
            self.canvas.volume_view.visible = not self.canvas.volume_view.visible
            self.canvas.update()
            return

        if ind_code in self.data_manager.active_indicators:
            self.data_manager.remove_indicator(ind_code)
        else:
            params = {"period": 14} if ind_code == "SMA" else {}
            self.data_manager.add_indicator(ind_code, params)