"""Toolbar widget providing timeframe selection and indicator controls."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLabel
from PySide6.QtCore import Qt, Signal


class ChartToolbar(QWidget):
    """Toolbar for chart controls (timeframe and indicator selection).
    
    This widget provides:
    1. Timeframe selector: Choose between 1s, 5s, 1m, 5m, 15m, 1H, 1D
    2. Indicator selector: Toggle volume, SMA, VWAP, and other indicators
    
    The toolbar emits signals when the user makes selections, allowing the
    parent chart widget to respond to user interactions.
    """

    # Signals for user interactions
    timeframe_changed = Signal(int)  # Emitted with timeframe in seconds

    def __init__(self, parent=None) -> None:
        """Initialize the toolbar with timeframe and indicator controls.
        
        Args:
            parent: Optional parent QWidget.
        """
        super().__init__(parent)
        self.setFixedHeight(38)

        # Enable background painting for custom QWidget
        # (Without this, the stylesheet background won't render)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "ChartToolbar { background-color: #131722; "
            "border-bottom: 1px solid #2A2E39; }"
        )

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setSpacing(2)  # Tighter spacing
        self.layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # --- TradingView-style Dark Theme Stylesheet ---
        # This stylesheet applies to all combo boxes on this toolbar
        self.combo_style = """
            QComboBox {
                background-color: transparent;
                color: #B2B5BE;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox:hover {
                background-color: #2A2E39;  /* Subtle highlight on hover */
                color: #D1D4DC;
            }
            QComboBox::drop-down {
                border: none; width: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #1E222D;
                color: #D1D4DC;
                border: 1px solid #2A2E39;
                border-radius: 4px;
                selection-background-color: #2962FF;
                selection-color: white;
                outline: none;
            }
        """

        self._build_timeframes()

    def _build_timeframes(self) -> None:
        """Create and configure the timeframe selector combo box."""
        self.tf_combo = QComboBox()
        self.tf_combo.setCursor(Qt.PointingHandCursor)
        self.tf_combo.setStyleSheet(self.combo_style)

        # Add timeframe options with their values in seconds
        timeframes = [
            ("1s", 1),
            ("5s", 5),
            ("1m", 60),
            ("5m", 300),
            ("15m", 900),
            ("1H", 3600),
            ("1D", 86400),
        ]
        for label, value in timeframes:
            self.tf_combo.addItem(label, value)

        # Default to 1m (index 2)
        self.tf_combo.setCurrentIndex(2)
        self.tf_combo.currentIndexChanged.connect(self._on_tf_changed)
        self.layout.addWidget(self.tf_combo)

    def _on_tf_changed(self, index: int) -> None:
        """Handle timeframe selection change.
        
        Args:
            index: Index in the combo box.
        """
        self.timeframe_changed.emit(self.tf_combo.itemData(index))

    def set_timeframe(self, seconds: int) -> None:
        """Programmatically set the timeframe.
        
        Args:
            seconds: Timeframe value in seconds.
        """
        idx = self.tf_combo.findData(seconds)
        if idx >= 0:
            self.tf_combo.setCurrentIndex(idx)