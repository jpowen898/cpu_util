import numpy as np
import pyqtgraph as pg
import psutil
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QLabel,
                              QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from collections import deque

from helpers import (
    HISTORY,
    N_CORES,
    get_cpu_limits,
    get_cpu_temperature_c,
    get_fan_rpm,
    get_freqs,
    get_ram_utilization_percent,
)


# =============================================================================
# FlowGrid — reflows children into columns that fit the available width
# =============================================================================
class FlowGrid(QWidget):
    """A container that arranges child widgets in a grid, reflowing the
    number of columns to fit the current width."""

    ROW_HEIGHT = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._grid = QGridLayout(self)
        self._grid.setSpacing(2)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._item_min_width = 200
        self._cols = 1
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

    def add_item(self, widget):
        self._items.append(widget)
        self._grid.addWidget(widget, len(self._items) - 1, 0)

    def set_item_min_width(self, w):
        self._item_min_width = w

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self):
        if not self._items:
            return
        available = self.width()
        cols = max(1, available // self._item_min_width)
        if cols == self._cols:
            return
        self._cols = cols
        for i, widget in enumerate(self._items):
            r, c = divmod(i, cols)
            self._grid.removeWidget(widget)
            self._grid.addWidget(widget, r, c)
        self._update_fixed_height()

    def _update_fixed_height(self):
        rows = (len(self._items) + self._cols - 1) // self._cols
        self.setFixedHeight(rows * self.ROW_HEIGHT + 4)

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow()
        self._update_fixed_height()


# =============================================================================
# BasePanel — subclass this to add new monitoring panels
# =============================================================================
class BasePanel(QWidget):
    """
    Base class for a monitoring panel.
    Subclass and override update_data() to create new panels.
    Each panel owns its own plot area and key/legend area.
    """

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)

        if title:
            title_label = QLabel(title)
            title_label.setFont(QFont("sans-serif", 12, QFont.Weight.Bold))
            title_label.setStyleSheet("color: #e0e0e0; padding: 2px 0px;")
            self._layout.addWidget(title_label)

    def update_data(self):
        """Called every tick by MainWindow. Override in subclasses."""
        raise NotImplementedError


# =============================================================================
# CpuThroughputPanel — stacked effective‑GHz chart + per‑core key
# =============================================================================
class CpuThroughputPanel(BasePanel):

    def __init__(self, parent=None):
        super().__init__(
            "CPU Effective Throughput  (Utilization × Frequency)", parent
        )

        self.colors = self._generate_colors(N_CORES)

        # --- Data buffers ---
        self.eff_history = [
            deque([0.0] * HISTORY, maxlen=HISTORY) for _ in range(N_CORES)
        ]
        self.freq_total_history = deque([0.0] * HISTORY, maxlen=HISTORY)
        self.x = np.arange(HISTORY)

        # --- Plot widget ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#1e1e1e")
        self.plot_widget.showGrid(x=False, y=True, alpha=0.15)
        self.plot_widget.setLabel("left", "GHz (effective)")
        self.plot_widget.setLabel("bottom", "Time")
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.hideButtons()
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.plot_widget.setMinimumHeight(100)
        self._layout.addWidget(self.plot_widget, stretch=1)

        # Stacked area: N+1 boundary curves, N fill regions
        baseline = np.zeros(HISTORY)
        self.curves = []
        for _ in range(N_CORES + 1):
            curve = pg.PlotCurveItem(self.x, baseline, pen=pg.mkPen(None))
            self.plot_widget.addItem(curve)
            self.curves.append(curve)

        self.fills = []
        for i in range(N_CORES):
            c = self.colors[i]
            brush = pg.mkBrush(c.red(), c.green(), c.blue(), 160)
            fill = pg.FillBetweenItem(
                self.curves[i], self.curves[i + 1], brush=brush
            )
            self.plot_widget.addItem(fill)
            self.fills.append(fill)

        # Frequency line (white dashed)
        self.freq_line = self.plot_widget.plot(
            self.x, baseline,
            pen=pg.mkPen(color="w", width=2, style=Qt.PenStyle.DashLine),
            name="Total Freq (GHz)",
        )

        # --- Key / legend panel ---
        key_container = QWidget()
        key_vlayout = QVBoxLayout(key_container)
        key_vlayout.setContentsMargins(4, 2, 4, 2)
        key_vlayout.setSpacing(2)

        # Per-core flow grid (reflows columns on resize)
        self.core_grid = FlowGrid()
        mono = QFont("monospace", 9)
        label_width = QFontMetrics(mono).horizontalAdvance(
            "\u25A0 CPU00: 100.0% @ 5.80 GHz"
        ) + 30  # swatch + padding
        self.core_grid.set_item_min_width(label_width)

        self.core_labels = []
        for i in range(N_CORES):
            label = QLabel()
            label.setFont(mono)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setStyleSheet("color: white;")
            self.core_labels.append(label)
            self.core_grid.add_item(label)
        key_vlayout.addWidget(self.core_grid)

        # Totals label
        self.totals_label = QLabel()
        self.totals_label.setFont(QFont("monospace", 10, QFont.Weight.Bold))
        self.totals_label.setStyleSheet("color: #00ffaa; padding: 2px 0px;")
        self.totals_label.setWordWrap(True)
        key_vlayout.addWidget(self.totals_label)

        key_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._layout.addWidget(key_container, stretch=0)

        # Seed labels with zeroes
        self._update_labels(
            [0.0] * N_CORES,
            [0.0] * N_CORES,
            0.0,
            0.0,
            0.0,
            0.0,
            "CPU Limited: No",
        )

    # ----- helpers ----------------------------------------------------------

    @staticmethod
    def _generate_colors(n):
        colors = []
        for i in range(n):
            color = QColor.fromHsvF(i / n, 0.7, 0.85)
            colors.append(color)
        return colors

    def _update_labels(
        self,
        utils,
        freqs,
        total_util,
        total_eff,
        total_freq,
        total_max,
        limit_text,
    ):
        for i in range(N_CORES):
            hex_color = self.colors[i].name()
            self.core_labels[i].setText(
                f'<span style="color:{hex_color}; font-size:14px;">&#9632;</span> '
                f"CPU{i}: {utils[i]:5.1f}% @ {freqs[i]:.2f} GHz"
            )
        self.totals_label.setText(
            f"CPU Utilization: {total_util:.1f}%  |  "
            f"Effective Utilization: {total_eff:.1f}%  |  "
            f"Freq: {total_freq:.1f} / {total_max:.1f} GHz\n"
            f"{limit_text}"
        )

    # ----- update (called each tick) ----------------------------------------

    def update_data(self):
        utils = psutil.cpu_percent(percpu=True)
        freqs, max_freqs = get_freqs()
        cap_freqs, hw_max_freqs = get_cpu_limits()

        total_freq = sum(freqs)
        total_max = sum(max_freqs)

        eff_values = []
        for i in range(N_CORES):
            eff = (utils[i] / 100.0) * freqs[i]
            self.eff_history[i].append(eff)
            eff_values.append(eff)

        self.freq_total_history.append(total_freq)

        # Update stacked area curves (cumulative from bottom)
        cumulative = np.zeros(HISTORY)
        for i in range(N_CORES):
            cumulative = cumulative + np.array(self.eff_history[i])
            self.curves[i + 1].setData(self.x, cumulative)

        # Update frequency line
        self.freq_line.setData(self.x, np.array(self.freq_total_history))

        # Update Y axis
        self.plot_widget.setYRange(0, total_max, padding=0.02)
        self.plot_widget.setXRange(0, HISTORY - 1, padding=0)

        # Update key labels
        total_util = sum(utils) / N_CORES
        total_eff = (sum(eff_values) / total_max * 100) if total_max > 0 else 0

        capped_cores = 0
        active_limited_cores = 0
        for i in range(N_CORES):
            cap = cap_freqs[i]
            hw_max = hw_max_freqs[i]
            if hw_max > 0 and cap < (0.98 * hw_max):
                capped_cores += 1
                if utils[i] > 85.0 and freqs[i] >= (0.97 * cap):
                    active_limited_cores += 1

        if active_limited_cores > 0:
            limit_text = (
                f"CPU Limited: Yes  |  Active capped cores: "
                f"{active_limited_cores}  |  Total capped cores: {capped_cores}"
            )
        elif capped_cores > 0:
            limit_text = (
                f"CPU Limited: Cap present  |  Total capped cores: {capped_cores}"
            )
        else:
            limit_text = "CPU Limited: No"

        self._update_labels(
            utils,
            freqs,
            total_util,
            total_eff,
            total_freq,
            total_max,
            limit_text,
        )


class CpuTemperaturePanel(BasePanel):

    def __init__(self, parent=None):
        super().__init__("CPU Temperature and Fan Speed", parent)

        self.temp_history = deque([np.nan] * HISTORY, maxlen=HISTORY)
        self.fan_history = deque([np.nan] * HISTORY, maxlen=HISTORY)
        self.x = np.arange(HISTORY)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#1e1e1e")
        self.plot_widget.showGrid(x=False, y=True, alpha=0.15)
        self.plot_widget.setLabel("left", "Temp (degC)")
        self.plot_widget.setLabel("bottom", "Time")
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.hideButtons()
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.plot_widget.setMinimumHeight(100)
        self._layout.addWidget(self.plot_widget, stretch=1)

        self.temp_line = self.plot_widget.plot(
            self.x,
            np.array(self.temp_history),
            pen=pg.mkPen(color="#ff8c42", width=2),
            name="CPU Temp (degC)",
        )

        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showAxis("right")
        self.plot_item.getAxis("right").setLabel("Fan (RPM)")
        self.plot_item.getAxis("right").setPen(pg.mkPen("#4db5ff"))
        self.plot_item.getAxis("right").setTextPen(pg.mkPen("#4db5ff"))

        self.fan_view = pg.ViewBox()
        self.plot_item.scene().addItem(self.fan_view)
        self.plot_item.getAxis("right").linkToView(self.fan_view)
        self.fan_view.setXLink(self.plot_item)

        self.fan_line = pg.PlotCurveItem(
            self.x,
            np.array(self.fan_history),
            pen=pg.mkPen(color="#4db5ff", width=2),
            name="Fan (kRPM)",
        )
        self.fan_view.addItem(self.fan_line)
        self.plot_item.vb.sigResized.connect(self._sync_fan_view)
        self._sync_fan_view()

        self.status_label = QLabel("CPU Temp: unavailable  |  Fan: unavailable")
        self.status_label.setFont(QFont("monospace", 10, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #ffb37a; padding: 2px 0px;")
        self._layout.addWidget(self.status_label, stretch=0)

    def _sync_fan_view(self):
        self.fan_view.setGeometry(self.plot_item.vb.sceneBoundingRect())
        self.fan_view.linkedViewChanged(self.plot_item.vb, self.fan_view.XAxis)

    def update_data(self):
        temp_c = get_cpu_temperature_c()
        fan_rpm = get_fan_rpm()

        if temp_c is None:
            self.temp_history.append(np.nan)
            temp_text = "unavailable"
        else:
            self.temp_history.append(temp_c)
            temp_text = f"{temp_c:.1f} degC"

        if fan_rpm is None:
            self.fan_history.append(np.nan)
            fan_text = "unavailable"
        else:
            self.fan_history.append(fan_rpm)
            fan_text = f"{fan_rpm:.0f} RPM"

        y_temp = np.array(self.temp_history)
        y_fan = np.array(self.fan_history)
        self.temp_line.setData(self.x, y_temp)
        self.fan_line.setData(self.x, y_fan)

        self.status_label.setText(f"CPU Temp: {temp_text}  |  Fan: {fan_text}")

        finite_temp = y_temp[np.isfinite(y_temp)]
        if finite_temp.size > 0:
            y_min = max(0.0, float(np.min(finite_temp)) - 5.0)
            y_max = float(np.max(finite_temp)) + 5.0
            if y_max <= y_min:
                y_max = y_min + 1.0
            self.plot_widget.setYRange(y_min, y_max, padding=0.02)
        else:
            self.plot_widget.setYRange(0, 100, padding=0)

        finite_fan = y_fan[np.isfinite(y_fan)]
        if finite_fan.size > 0:
            fan_min = max(0.0, float(np.min(finite_fan)) - 200.0)
            fan_max = float(np.max(finite_fan)) + 200.0
            if fan_max <= fan_min:
                fan_max = fan_min + 100.0
            self.fan_view.setYRange(fan_min, fan_max, padding=0.02)
        else:
            self.fan_view.setYRange(0, 5000, padding=0)

        self.plot_widget.setXRange(0, HISTORY - 1, padding=0)


class RamUtilizationPanel(BasePanel):

    def __init__(self, parent=None):
        super().__init__("RAM Utilization", parent)

        self.ram_history = deque([0.0] * HISTORY, maxlen=HISTORY)
        self.x = np.arange(HISTORY)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#1e1e1e")
        self.plot_widget.showGrid(x=False, y=True, alpha=0.15)
        self.plot_widget.setLabel("left", "RAM (%)")
        self.plot_widget.setLabel("bottom", "Time")
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.hideButtons()
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.plot_widget.setMinimumHeight(100)
        self._layout.addWidget(self.plot_widget, stretch=1)

        self.ram_line = self.plot_widget.plot(
            self.x,
            np.array(self.ram_history),
            pen=pg.mkPen(color="#47d16c", width=2),
            name="RAM (%)",
        )
        self.status_label = QLabel("RAM: 0.0%")
        self.status_label.setFont(QFont("monospace", 10, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #7ee89c; padding: 2px 0px;")
        self._layout.addWidget(self.status_label, stretch=0)

    def update_data(self):
        ram_pct = get_ram_utilization_percent()

        self.ram_history.append(ram_pct)

        y_ram = np.array(self.ram_history)
        self.ram_line.setData(self.x, y_ram)

        self.status_label.setText(f"RAM: {ram_pct:.1f}%")

        self.plot_widget.setXRange(0, HISTORY - 1, padding=0)
        self.plot_widget.setYRange(0, 100, padding=0.05)
