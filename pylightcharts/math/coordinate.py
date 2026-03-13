import math

class CoordinateEngine:
    """
    A pure mathematical translation layer. 
    Converts logical Data/Price values into physical X/Y pixel coordinates, and vice versa.
    """

    # ==========================================
    # Y-AXIS: PRICE <-> PIXEL
    # ==========================================

    @staticmethod
    def price_to_y(price: float, view_mid_price: float, view_price_range: float, chart_height: int) -> float:
        """
        Converts a dollar price into a Y-axis pixel coordinate.
        (Remember: Y=0 is the top of the screen in PySide6).
        """
        if view_price_range <= 0 or chart_height <= 0:
            return 0.0
            
        display_min = view_mid_price - (view_price_range / 2.0)
        normalized_position = (price - display_min) / view_price_range
        
        # Invert because UI coordinates go down, but price goes up
        return chart_height - (normalized_position * chart_height)

    @staticmethod
    def y_to_price(y: float, view_mid_price: float, view_price_range: float, chart_height: int) -> float:
        """
        Converts a physical Y-axis pixel (e.g., from a mouse hover) back into a dollar price.
        """
        if view_price_range <= 0 or chart_height <= 0:
            return 0.0
            
        display_min = view_mid_price - (view_price_range / 2.0)
        normalized_position = (chart_height - y) / chart_height
        
        return display_min + (normalized_position * view_price_range)

    # ==========================================
    # X-AXIS: INDEX <-> PIXEL
    # ==========================================

    @staticmethod
    def index_to_x(index: int, data_length: int, scroll_offset: float, total_candle_space: float, 
                   right_blank_space: float, chart_width: int) -> float:
        """
        Converts a data array index (e.g., 45) into an X-axis physical pixel.
        Returns the exact CENTER pixel of the candlestick.
        """
        if data_length == 0:
            return 0.0

        # Where is the exact center of the absolute latest candle on the screen?
        right_anchor_x = chart_width - right_blank_space - (total_candle_space / 2.0)
        
        # How many candles is the requested index away from the latest data?
        # We subtract the scroll offset to handle continuous panning
        candles_from_right = (data_length - 1 - index) - scroll_offset
        
        return right_anchor_x - (candles_from_right * total_candle_space)

    @staticmethod
    def x_to_index(x: float, data_length: int, scroll_offset: float, total_candle_space: float, 
                   right_blank_space: float, chart_width: int) -> int:
        """
        Converts a physical X-axis pixel (e.g., from a mouse click) back into a data array index.
        Returns the closest integer index.
        """
        if data_length == 0 or total_candle_space <= 0:
            return -1

        right_anchor_x = chart_width - right_blank_space - (total_candle_space / 2.0)
        
        # How many candles away from the anchor is this pixel?
        candles_from_right = (right_anchor_x - x) / total_candle_space
        
        # Reverse the math to find the exact float index, then round to nearest integer
        exact_index = (data_length - 1) - scroll_offset - candles_from_right
        
        return int(round(exact_index))

    # ==========================================
    # HELPER BOUNDS
    # ==========================================

    @staticmethod
    def get_candle_rect(center_x: float, open_y: float, close_y: float, candle_width: float) -> tuple[float, float, float, float]:
        """
        Helper method to quickly calculate the X, Y, Width, and Height needed 
        for QPainter.fillRect() to draw the main body of a candlestick.
        """
        rect_x = center_x - (candle_width / 2.0)
        rect_y = min(open_y, close_y)
        rect_height = max(abs(open_y - close_y), 1.0) # Guarantee at least 1px height
        
        return rect_x, rect_y, candle_width, rect_height
    
    @staticmethod
    def calculate_nice_step(price_range: float, max_ticks: int = 5) -> float:
        """Calculates 'clean' human-readable grid intervals (0.1, 0.5, 1, 10, etc.)"""
        if price_range <= 0: return 1.0
        
        rough_step = price_range / max_ticks
        
        # Find the power of 10 magnitude (e.g., 100, 10, 1, 0.1, 0.01)
        magnitude = math.pow(10, math.floor(math.log10(rough_step)))
        normalized_step = rough_step / magnitude
        
        # Snap the normalized step to a 'nice' multiplier
        if normalized_step < 1.5:
            nice_multiplier = 1.0
        elif normalized_step < 3.0:
            nice_multiplier = 2.0
        elif normalized_step < 7.0:
            nice_multiplier = 5.0
        else:
            nice_multiplier = 10.0
            
        return nice_multiplier * magnitude