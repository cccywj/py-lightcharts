"""Main chart widget module providing the PyLightChartWidget component.

This module contains the complete charting widget hierarchy:
1. _ChartCanvas: Low-level widget handling rendering and mouse/wheel events
2. PyLightChartWidget: High-level public API for application integration
"""
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
from pylightcharts.views.volume_view import VolumeView
from pylightcharts.views.live_price_view import LivePriceView


# ==========================================
# INTERNAL CANVAS (Handles the Drawing)
# ==========================================
class _ChartCanvas(QWidget):
    """Internal widget responsible for painting and handling mouse events.
    
    This class manages all the rendering views and translates user input
    (mouse/wheel) into viewport transformations. It is not meant to be
    used directly; access it through PyLightChartWidget instead.
    \nThe canvas uses a layered drawing approach where each view is responsible
    for one visual component, drawn from back to front (grid → volume → candles →
    indicators → live price → crosshair → tooltip).
    """

    def __init__(self, data_manager: DataManager, viewport: Viewport) -> None:
        """Initialize the chart canvas.
        
        Args:
            data_manager: Central data repository for OHLCV candles and indicators.
            viewport: Viewport state managing zoom, pan, and crosshair position.
        """
        super().__init__()
        self.data_manager = data_manager
        self.viewport = viewport

        # Initialize rendering layers in back-to-front order
        self.grid_view = GridView()
        self.volume_view = VolumeView()
        self.candle_view = CandleView()

        # Overlay layers
        self.axis_view = AxisView()
        self.live_price_view = LivePriceView()
        self.crosshair_view = CrosshairView()
        self.tooltip_view = TooltipView()

        # Configure widget behavior
        self.setMouseTracking(True)  # Get mouseMoveEvents even without button press
        self.setFocusPolicy(Qt.StrongFocus)  # Accept keyboard focus
        self.bg_color = "#131722"  # Dark background

        # Interaction state
        self.drag_mode = None  # 'chart', 'x_axis', 'y_axis', or None
        self.last_mouse_pos = QPoint()

    # ==========================================
    # PYSIDE6 EVENT HANDLERS
    # ==========================================
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for horizontal zoom.
        
        Args:
            event: Qt wheel event containing scroll delta.
        """
        # Positive delta = zoom in (smaller candles), negative = zoom out
        zoom_step = 0.5 if event.angleDelta().y() > 0 else -0.5
        self.viewport.zoom_x(zoom_step)

    def mousePressEvent(self, event) -> None:
        """Handle mouse button press to start drag interactions.
        
        Identifies which area was clicked and sets drag mode:
        - Y-axis margin: Vertical zoom
        - X-axis margin: Horizontal zoom
        - Main chart: Pan
        
        Args:
            event: Qt mouse event.
        """
        if event.button() == Qt.LeftButton:
            pos = event.position()
            px, py = int(pos.x()), int(pos.y())
            chart_w = self.width() - self.viewport.margin_right
            chart_h = self.height() - self.viewport.margin_bottom

            # Simple hit testing for axis vs chart area
            if px > chart_w and py < chart_h:
                self.drag_mode = "y_axis"
            elif px < chart_w and py > chart_h:
                self.drag_mode = "x_axis"
            elif px > chart_w and py > chart_h:
                self.drag_mode = None  # Do nothing in the empty corner intersection
            else:
                self.drag_mode = "chart"
            self.last_mouse_pos = pos

    def mouseDoubleClickEvent(self, event) -> None:
        """Handle double-click to reset.
        
        Double-clicking on the chart area snaps to the live edge.
        Double-clicking on the Y-axis enables auto-scaling to fit visible data.
        
        Args:
            event: Qt mouse event.
        """
        # Reset auto-scale on double click in Y-Axis, and return to home anywhere else
        pos = event.position().toPoint()
        chart_w = self.width() - self.viewport.margin_right
        
        if pos.x() > chart_w:
            # Double click the Y-Axis margin -> Reset Price Auto-Scale
            self.viewport.set_auto_scale(True)
        else:
            # Double click the Chart area -> Snap to the live edge!
            self.viewport.reset_to_home()

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse movement for dragging and crosshair updates.
        
        Updates crosshair position and applies viewport transformations
        based on the current drag mode.
        
        Args:
            event: Qt mouse event.
        """
        pos = event.position().toPoint()

        if self.drag_mode == "chart":
            # Pan the chart
            dx = pos.x() - self.last_mouse_pos.x()
            dy = pos.y() - self.last_mouse_pos.y()
            self.viewport.pan_x(dx, len(self.data_manager.get_data_list()))
            self.viewport.pan_y(dy, self.height() - self.viewport.margin_bottom)
            self.last_mouse_pos = pos
        elif self.drag_mode == "x_axis":
            # Horizontal zoom
            dx = pos.x() - self.last_mouse_pos.x()
            self.viewport.zoom_x(dx * 0.05)
            self.last_mouse_pos = pos
        elif self.drag_mode == "y_axis":
            # Vertical zoom
            dy = pos.y() - self.last_mouse_pos.y()
            self.viewport.zoom_y(dy)
            self.last_mouse_pos = pos
        else:
            # Update crosshair position
            self.viewport.update_crosshair(pos.x(), pos.y())

        self.update()  # Trigger repaint

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse button release to end drag interactions.
        
        Args:
            event: Qt mouse event.
        """
        self.drag_mode = None

    def leaveEvent(self, event) -> None:
        """Handle mouse leaving the widget to hide the crosshair.
        
        Args:
            event: Qt event.
        """
        self.viewport.hide_crosshair()

    def paintEvent(self, event) -> None:
        """Render the complete chart in layers from back to front.
        
        Each view is responsible for rendering one visual component.
        Called automatically when update() is invoked.
        
        Args:
            event: Qt paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # Smooth edges

        data_length = len(self.data_manager.get_data_list())
        self.viewport.track_live_edge(data_length)

        w, h = self.width(), self.height()
        # Fill background
        painter.fillRect(0, 0, w, h, QColor(self.bg_color))

        chart_w = w - self.viewport.margin_right
        chart_h = h - self.viewport.margin_bottom

        painter.setClipRect(0, 0, chart_w, chart_h)

        # Draw layers from back to front
        self.grid_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.volume_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.candle_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)

        painter.setClipping(False)

        self.axis_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.live_price_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.crosshair_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)
        self.tooltip_view.draw(painter, self.viewport, self.data_manager, chart_w, chart_h)


# ==========================================
# MAIN PUBLIC WIDGET (The "React-like" Component)
# ==========================================
class PyLightChartWidget(QWidget):
    """Main chart widget providing a complete charting solution.
    
    This is the primary public API for integrating the chart into an application.
    It manages the toolbar, canvas, and data flow between the application and
    the rendering system.
    
    Signals:
        historical_data_requested: Emitted when the chart needs historical data.
            Emits (symbol: str, timeframe: int) where timeframe is in seconds.
        indicator_requested: Emitted when an indicator is toggled.
            Emits (indicator_code: str) where code is 'SMA', 'VOL', 'VWAP', etc.
    
    Example Usage:
        >>> from PySide6.QtWidgets import QApplication
        >>> app = QApplication([])
        >>> chart = PyLightChartWidget()
        >>> chart.change_symbol("AAPL")
        >>> chart.apply_historical_data([{...}, {...}])  # Pass OHLCV data
        >>> chart.update_tick({"bid": 150.0, "ask": 150.1, ...})  # Live data
    """

    # Signals for parent application communication
    historical_data_requested = Signal(str, int)  # (symbol, timeframe_s)

    def __init__(self, parent=None) -> None:
        """Initialize the chart widget.
        
        Args:
            parent: Optional parent QWidget.
        """
        super().__init__(parent)

        # Core components
        self.data_manager = DataManager()
        self.viewport = Viewport()
        self.current_symbol = "AAPL"

        # Layout setup
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # No padding
        self.main_layout.setSpacing(0)  # No spacing

        # Add toolbar
        self.toolbar = ChartToolbar()
        self.main_layout.addWidget(self.toolbar)

        # Add canvas
        self.canvas = _ChartCanvas(self.data_manager, self.viewport)
        self.main_layout.addWidget(self.canvas)

        # Connect signals for repainting
        self.data_manager.data_changed.connect(self.canvas.update)
        self.viewport.viewport_changed.connect(self.canvas.update)
        

        # Connect toolbar signals
        self.toolbar.timeframe_changed.connect(self._handle_tf_changed)

    def _handle_tf_changed(self, tf_seconds: int) -> None:
        """Handle timeframe selection change from the toolbar.
        
        Args:
            tf_seconds: New timeframe in seconds.
        """
        self.data_manager.set_timeframe(tf_seconds)
        self.enable_buffering()
        self.historical_data_requested.emit(self.current_symbol, tf_seconds)
        self.viewport.reset_to_home()

    # ==========================================
    # PUBLIC API
    # ==========================================
    def change_symbol(self, symbol: str) -> None:
        """Switch to a new symbol and request historical data.
        
        Args:
            symbol: Ticker symbol (e.g., 'AAPL', 'ES', 'EURUSD').
        """
        self.current_symbol = symbol
        self.enable_buffering()
        self.historical_data_requested.emit(symbol, self.data_manager.timeframe)

    def enable_buffering(self) -> None:
        """Enable live tick buffering. Call this before requesting history."""
        self.data_manager.enable_buffering()

    def apply_historical_data(self, ib_bars: list) -> None:
        """Load historical OHLCV data into the chart.
        
        Accepts either general data or IB Async bar format. Should be called
        after requesting historical data and receiving it from a data source.
        \n        Args:
            ib_bars: List of OHLCV dictionaries. Each should have:
                - 'time': datetime.datetime (UTC-aware)
                - 'open': float
                - 'high': float
                - 'low': float
                - 'close': float
                - 'volume': int
        """
        self.data_manager.apply_historical_data(ib_bars)

    def update_tick(self, ib_ticker: dict) -> None:
        """Update the chart with a live market tick.
        
        This can be called from a real-time data feed. If called before
        historical data is loaded, ticks are buffered automatically.
        \n        Args:
            ib_ticker: Tick dictionary with:
                - 'time': datetime.datetime (UTC-aware)
                - 'bid': float (or use 'last' for price)
                - 'ask': float (optional)
                - 'volume': int (optional)
        """
        self.data_manager.update_tick(ib_ticker)

    def set_timeframe(self, seconds: int) -> None:
        """Programmatically set the timeframe.
        
        Args:
            seconds: Timeframe in seconds (e.g., 60 for 1-minute).
        """
        self.toolbar.set_timeframe(seconds)

    def toggle_volume(self) -> None:
        """Toggle the volume bars overlay on/off."""
        self.canvas.volume_view.visible = not self.canvas.volume_view.visible
        self.canvas.update()