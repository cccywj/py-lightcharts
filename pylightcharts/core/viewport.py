"""
Viewport (camera) state management for financial charts.

Manages the visible portion of the chart:
- X-axis: time/index position and zoom (candle width)
- Y-axis: price range and midpoint (auto-scale or manual)
- Crosshair: mouse cursor position for interaction

The viewport is stateful and independent of data. It allows
smooth panning, zooming, and auto-scaling without modifying
the underlying data.
"""

from typing import Tuple, List, Dict, Any
from PySide6.QtCore import QObject, Signal

class Viewport(QObject):
    """
    Manages the 2D camera/viewport for the chart.
    
    Emits signals when the view changes, triggering UI redraws.
    Handles:
    - X-axis: time scrolling and candle zoom
    - Y-axis: price panning and scaling
    - Auto-scaling: fit Y-axis to visible data range
    - Crosshair: mouse hover position and visibility
    
    Signal:
        viewport_changed: Emitted whenever any viewport parameter changes
    
    Attributes:
        margin_right: Pixels reserved on right for price axis labels
        margin_bottom: Pixels reserved at bottom for time axis labels
        auto_scale: Whether Y-axis auto-fits to visible candles
        candle_width: Width of each candlestick in pixels
        candle_spacing: Gap between candles in pixels
        scroll_index_offset: How far scrolled (in candle units)
        view_mid_price: Center price of visible Y range
        view_price_range: Total price span of visible Y range
    
    Examples:
        >>> vp = Viewport()
        >>> vp.zoom_x(1.0)  # Zoom in on candles
        >>> vp.pan_x(50, data_length=100)  # Pan right 50 pixels
        >>> vp.set_auto_scale(True)  # Auto-fit Y-axis
    """
    
    # Qt signal emitted whenever viewport changes (connected to canvas.update())
    viewport_changed = Signal()

    def __init__(self):
        """Initialize viewport with default layout and view parameters."""
        super().__init__()
        
        # ==========================================
        # LAYOUT MARGINS (pixels)
        # ==========================================
        self.margin_right = 85     # Space for price labels on the right
        self.margin_bottom = 30    # Space for time labels at the bottom
        self.right_blank_space = 0.0  # Inset from chart right (0 = data may use full plot width)
        self.default_right_gap_px = 100.0  # Default empty space to the right of the latest bar (via scroll)
        
        # ==========================================
        # X-AXIS (Time) STATE
        # ==========================================
        self.default_candle_width = 8.0    # Initial width of each candlestick
        self.candle_width = self.default_candle_width  # Current width (can change via zoom)
        self.candle_spacing = 2.0          # Gap between candlesticks
        
        # ==========================================
        # Y-AXIS (Price) STATE
        # ==========================================
        self.auto_scale = True             # Automatically fit Y range to visible data
        self.view_mid_price = 0.0          # Center price of the visible range
        self.view_price_range = 1.0        # Total price span (e.g., 10.0 = $10 price range)

        # ==========================================
        # CROSSHAIR STATE
        # ==========================================
        self.crosshair_x = -1.0            # X-pixel position of crosshair (-1 = hidden)
        self.crosshair_y = -1.0            # Y-pixel position of crosshair
        self.crosshair_visible = False     # Whether crosshair is currently drawn

        self.last_data_length = 0

        self.scroll_index_offset = self._default_scroll_index_offset()

    def _default_scroll_index_offset(self) -> float:
        """Negative scroll so the latest bar sits ~default_right_gap_px left of the plot right edge."""
        ts = self.candle_width + self.candle_spacing
        if ts <= 0:
            return 0.0
        return -self.default_right_gap_px / ts

    @property
    def total_space(self) -> float:
        """
        Total pixel width of one candle plus its spacing.
        
        Used for coordinate transformations between candle indices and pixels.
        
        Returns:
            float: candle_width + candle_spacing
        
        Examples:
            >>> vp.candle_width = 8
            >>> vp.candle_spacing = 2
            >>> vp.total_space
            10.0
        """
        return self.candle_width + self.candle_spacing

    # ==========================================
    # X-AXIS CONTROLS (Time/Index)
    # ==========================================

    def pan_x(self, dx_pixels: float, max_index: int) -> None:
        """
        Pan the chart left or right based on mouse movement.
        
        Converts pixel movement into candle offset and updates scroll_index_offset.
        Panning to the right (into empty / future space) is unbounded below zero.
        Panning into history is still capped when data exists.
        
        Args:
            dx_pixels: Pixel movement (+right, -left)
            max_index: Total number of candles (caps pan into past; ignored if 0)
        
        Examples:
            >>> vp.pan_x(50, max_index=300)  # Move right 50 pixels
            >>> vp.pan_x(-25, max_index=300)  # Move left 25 pixels
        """
        shift_in_candles = dx_pixels / self.total_space
        self.scroll_index_offset += shift_in_candles
        
        if max_index > 0:
            self.scroll_index_offset = min(float(max_index), self.scroll_index_offset)
        self.viewport_changed.emit()

    def zoom_x(self, zoom_step: float) -> None:
        """
        Zoom in or out on the X-axis (adjust candle width).
        
        Changing candle_width makes individual candles wider/narrower,
        allowing you to see more or fewer candles on screen.
        Automatically disables auto_scale since you're taking manual control.
        
        Args:
            zoom_step: Amount to add to candle_width
                      +0.5 = zoom in slightly
                      -0.5 = zoom out slightly
                      Clamped to [1.0, 50.0]
        
        Examples:
            >>> vp.zoom_x(1.0)   # Zoom in (wider candles)
            >>> vp.zoom_x(-1.0)  # Zoom out (narrower candles)
        """
        # self.auto_scale = False  # Manual zoom breaks auto-scale
        self.candle_width = max(1.0, min(50.0, self.candle_width + zoom_step))
        self.viewport_changed.emit()

    def get_visible_indices(self, chart_width: int, data_length: int) -> Tuple[int, int]:
        """
        Calculate which data array indices are currently visible on screen.
        
        Based on the chart width, candle spacing, and current scroll offset,
        determines the range of candles that should be drawn.
        
        Args:
            chart_width: Width of chart area in pixels
            data_length: Total number of candles in dataset
        
        Returns:
            Tuple[int, int]: (left_index, right_index) of visible candles
        
        Note:
            - right_index is always the most recent candle(s)
            - Adds 2 extra candles on edges for smoother clipping
            - With no candles, indices are virtual (right_idx may be negative)
        
        Examples:
            >>> chart_width = 1000
            >>> left, right = vp.get_visible_indices(1000, 300)
            >>> vp.apply_auto_scale(data[left:right+1])
        """
        # The latest candle is always at the right edge (virtual index when panned into future)
        right_idx = data_length - 1 - int(self.scroll_index_offset)
        
        # How many candles fit in the visible area?
        usable_width = chart_width - self.right_blank_space
        max_visible_candles = int(usable_width // self.total_space) + 2 
        
        left_idx = max(0, right_idx - max_visible_candles)
        return left_idx, right_idx

    # ==========================================
    # Y-AXIS CONTROLS (Price)
    # ==========================================

    def pan_y(self, dy_pixels: float, chart_height: int) -> None:
        """
        Pan the price range up or down.
        
        Translates pixel movement into price movement.
        Disabled when auto_scale is enabled (auto-scaling takes precedence).
        
        Args:
            dy_pixels: Pixel movement (+up, -down)
            chart_height: Height of chart area in pixels
        
        Note:
            - Has no effect if auto_scale is True
            - Only works if user manually zooms or pans Y-axis
        
        Examples:
            >>> vp.pan_y(100, chart_height=800)  # Shift up
            >>> vp.pan_y(-50, chart_height=800)  # Shift down
        """
        if self.auto_scale or chart_height <= 0:
            return  # Y-panning disabled if auto-scaling
            
        price_per_pixel = self.view_price_range / chart_height
        self.view_mid_price += (dy_pixels * price_per_pixel)
        self.viewport_changed.emit()

    def zoom_y(self, dy_pixels: float) -> None:
        """
        Zoom in or out on the Y-axis (adjust price scale).
        
        Makes prices spread out more (zoom in) or compress (zoom out).
        Disables auto_scale since you're taking manual control.
        
        Args:
            dy_pixels: Pixel movement for zoom intensity
                      Typically values like ±10 to ±50
        
        Examples:
            >>> vp.zoom_y(-50)  # Compress Y-axis (see more price range)
            >>> vp.zoom_y(50)   # Stretch Y-axis (see less price range)
        """
        self.auto_scale = False
        # Negative pixels = zoom in (smaller range), positive = zoom out (larger range)
        self.view_price_range *= (1.0 + dy_pixels * 0.005)
        self.view_price_range = max(0.001, self.view_price_range)
        self.viewport_changed.emit()

    def apply_auto_scale(self, visible_data: List[Dict[str, Any]]) -> None:
        """
        Automatically fit the Y-axis to visible candle range.
        
        Examines the high/low prices of visible candles and adjusts
        view_price_range and view_mid_price to fit them with padding.
        
        Called automatically by rendering engine every frame if auto_scale is True.
        
        Args:
            visible_data: List of visible candles (each with 'high' and 'low')
        
        Note:
            - Only works if auto_scale is True
            - Adds 10% padding above and below data range for visibility
            - Handles empty data gracefully
        
        Examples:
            >>> visible = dm.get_visible_data(left_idx, right_idx)
            >>> vp.apply_auto_scale(visible)
        """
        if not visible_data or not self.auto_scale:
            return
            
        # Find price extremes in visible data
        v_min = min(d['low'] for d in visible_data)
        v_max = max(d['high'] for d in visible_data)
        v_range = v_max - v_min if v_max != v_min else 1.0
        
        # Add 10% padding so candles don't touch edges
        self.view_price_range = v_range * 1.3
        self.view_mid_price = v_min + (v_range / 2.0)

    # ==========================================
    # STATE MANAGEMENT
    # ==========================================

    def reset_to_home(self) -> None:
        """
        Reset viewport to initial state.
        
        - Snaps to the latest candle with default right gap (see default_right_gap_px)
        - Enables auto-scale (Y-axis fits data)
        - Resets candle width to default
        - Hides crosshair
        """
        self.auto_scale = True
        self.candle_width = self.default_candle_width
        self.scroll_index_offset = self._default_scroll_index_offset()
        self.crosshair_visible = False
        self.viewport_changed.emit()

    def set_auto_scale(self, state: bool) -> None:
        """
        Enable or disable automatic Y-axis scaling.
        
        Args:
            state: True to auto-fit Y-axis to data, False for manual control
        
        Examples:
            >>> vp.set_auto_scale(True)   # Enable auto-fit
            >>> vp.set_auto_scale(False)  # Manual Y-axis control
        """
        self.auto_scale = state
        self.viewport_changed.emit()

    def track_live_edge(self, current_data_length: int):
        """
        Mathematically freezes the historical view when new candles arrive.
        Called every frame before calculating coordinate projections.
        """
        # If a new candle was added to the array
        if self.last_data_length > 0 and current_data_length > self.last_data_length:
            candles_added = current_data_length - self.last_data_length
            
            # If the user has panned away from the live edge (offset > 0), 
            # we push the offset back by the exact number of new candles.
            if self.scroll_index_offset > 0:
                self.scroll_index_offset += candles_added
                
        # If the timeframe changed or data was cleared, reset the offset
        elif current_data_length < self.last_data_length:
            self.scroll_index_offset = self._default_scroll_index_offset()
            
        self.last_data_length = current_data_length

    # ==========================================
    # CROSSHAIR MANAGEMENT
    # ==========================================

    def update_crosshair(self, x: float, y: float) -> None:
        """
        Update crosshair position and make it visible.
        
        Called by mouse move events to track cursor position.
        Used by TooltipView and CrosshairView to show price/time info.
        
        Args:
            x: X-pixel position (0 = left edge)
            y: Y-pixel position (0 = top edge)
        
        Examples:
            >>> def on_mouse_move(event):
            >>>     vp.update_crosshair(event.x(), event.y())
        """
        self.crosshair_x = x
        self.crosshair_y = y
        self.crosshair_visible = True
        self.viewport_changed.emit()

    def hide_crosshair(self) -> None:
        """
        Hide the crosshair.
        
        Called when mouse leaves the chart widget.
        
        Examples:
            >>> def on_mouse_leave(event):
            >>>     vp.hide_crosshair()
        """
        self.crosshair_visible = False
        self.viewport_changed.emit()