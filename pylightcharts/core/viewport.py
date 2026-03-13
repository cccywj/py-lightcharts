from PySide6.QtCore import QObject, Signal

class Viewport(QObject):
    """
    Manages the camera state of the chart: X-axis zoom/pan and Y-axis zoom/pan.
    Emits a signal whenever the view changes so the UI can trigger a redraw.
    """
    
    viewport_changed = Signal()

    def __init__(self):
        super().__init__()
        
        # --- Layout Margins ---
        self.margin_right = 85    # <-- INCREASE THIS to 85 or 90
        self.margin_bottom = 30   
        self.right_blank_space = 100.0
        
        # --- X-Axis (Time) State ---
        self.default_candle_width = 8.0
        self.candle_width = self.default_candle_width
        self.candle_spacing = 2.0
        self.scroll_index_offset = 0.0  
        
        # --- Y-Axis (Price) State ---
        self.auto_scale = True
        self.view_mid_price = 0.0
        self.view_price_range = 1.0

        # --- Crosshair State ---
        self.crosshair_x = -1.0
        self.crosshair_y = -1.0
        self.crosshair_visible = False

    @property
    def total_space(self) -> float:
        """Helper to get the total pixel width of one candle + its spacing."""
        return self.candle_width + self.candle_spacing

    # ==========================================
    # X-AXIS CONTROLS
    # ==========================================

    def pan_x(self, dx_pixels: float, max_index: int):
        """Shifts the timeline left or right based on pixel movement."""
        shift_in_candles = dx_pixels / self.total_space
        self.scroll_index_offset += shift_in_candles
        
        # Constrain so we don't scroll infinitely into the future or past
        self.scroll_index_offset = max(0.0, min(float(max_index), self.scroll_index_offset))
        self.viewport_changed.emit()

    def zoom_x(self, zoom_step: float):
        """Increases or decreases the width of the candles."""
        self.auto_scale = False # Zooming manually breaks auto-scale
        self.candle_width = max(1.0, min(50.0, self.candle_width + zoom_step))
        self.viewport_changed.emit()

    def get_visible_indices(self, chart_width: int, data_length: int) -> tuple[int, int]:
        """
        Calculates which data array indices are currently visible on screen.
        Returns a tuple of (left_index, right_index).
        """
        if data_length == 0:
            return 0, 0
            
        right_idx = data_length - 1 - int(self.scroll_index_offset)
        
        # How many candles fit in the chart area? Add 2 to ensure smooth edge clipping
        usable_width = chart_width - self.right_blank_space
        max_visible_candles = int(usable_width // self.total_space) + 2 
        
        left_idx = max(0, right_idx - max_visible_candles)
        return left_idx, right_idx

    # ==========================================
    # Y-AXIS CONTROLS
    # ==========================================

    def pan_y(self, dy_pixels: float, chart_height: int):
        """Shifts the price scale up or down based on pixel movement."""
        if self.auto_scale or chart_height <= 0:
            return # Y-panning is disabled if auto-scaling is on
            
        price_per_pixel = self.view_price_range / chart_height
        self.view_mid_price += (dy_pixels * price_per_pixel)
        self.viewport_changed.emit()

    def zoom_y(self, dy_pixels: float):
        """Stretches or compresses the Y-Axis."""
        self.auto_scale = False
        # A standard scale multiplier logic
        self.view_price_range *= (1.0 + dy_pixels * 0.005)
        self.view_price_range = max(0.001, self.view_price_range)
        self.viewport_changed.emit()

    def apply_auto_scale(self, visible_data: list[dict]):
        """
        Inspects the visible candles and perfectly sizes the Y-axis range to fit them.
        Called automatically by the drawing engine if auto_scale is True.
        """
        if not visible_data or not self.auto_scale:
            return
            
        v_min = min(d['low'] for d in visible_data)
        v_max = max(d['high'] for d in visible_data)
        v_range = v_max - v_min if v_max != v_min else 1.0
        
        # Add a 10% padding so candles don't touch the very top/bottom of the window
        self.view_price_range = v_range * 1.1 
        self.view_mid_price = v_min + (v_range / 2.0)

    # ==========================================
    # STATE MANAGEMENT
    # ==========================================

    def reset_to_home(self):
        """Snaps the camera back to the latest candle and turns auto-scale back on."""
        self.auto_scale = True
        self.scroll_index_offset = 0.0
        self.candle_width = self.default_candle_width
        self.viewport_changed.emit()

    def set_auto_scale(self, state: bool):
        self.auto_scale = state
        self.viewport_changed.emit()

    # ==========================================
    # CROSSHAIR
    # ==========================================

    def update_crosshair(self, x: float, y: float):
        """Updates the logical crosshair position and triggers a render."""
        self.crosshair_x = x
        self.crosshair_y = y
        self.crosshair_visible = True
        self.viewport_changed.emit()

    def hide_crosshair(self):
        """Hides the crosshair when the mouse leaves the widget."""
        self.crosshair_visible = False
        self.viewport_changed.emit()