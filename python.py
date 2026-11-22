"""
Unicode Permutation Program Generator — Visual Edition v2 (PySide6)

pip install PySide6
"""

import math
import random
import sys
import time
from collections import deque
from itertools import islice, permutations

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QFontMetricsF, QLinearGradient,
    QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QMainWindow, QPlainTextEdit, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

MAX_CP = 0x10FFF8

PALETTE = ["#5b8cff", "#a56bff", "#ff5b9e", "#ff9e4d",
           "#3fd0a4", "#4dd2ff", "#ffe14d", "#ff6b6b"]

ACCENT, ACCENT2 = QColor(PALETTE[0]), QColor(PALETTE[1])


def C(hexstr, alpha=255):
    c = QColor(hexstr)
    c.setAlpha(alpha)
    return c


def rgba(c, a):
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


def rounded_top_path(x, y, w, h, r):
    r = max(0.0, min(r, w / 2, h))
    p = QPainterPath()
    p.moveTo(x, y + h)
    p.lineTo(x, y + r)
    p.quadTo(x, y, x + r, y)
    p.lineTo(x + w - r, y)
    p.quadTo(x + w, y, x + w, y + r)
    p.lineTo(x, y + h) if False else p.lineTo(x + w, y + h)
    p.closeSubpath()
    return p


def char_label(cp):
    ch = chr(cp)
    return ch if ch.isprintable() else f"U+{cp:04X}"


def fmt_num(v):
    return f"{int(round(v)):,}"


def fmt_short(v):
    for div, suf in ((1_000_000, "M"), (1_000, "k")):
        if v >= div:
            return f"{v / div:.1f}{suf}"
    return f"{v:.0f}"


def fmt_eta(sec):
    sec = int(max(0, sec))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m left"
    if m:
        return f"{m}m {s:02d}s left"
    return f"{s}s left"


def mono_font(size, bold=False):
    f = QFont("Consolas")
    f.setStyleHint(QFont.Monospace)
    f.setPointSize(size)
    f.setBold(bold)
    return f


def paint_panel(p, w, h, radius=12):
    p.setPen(QPen(QColor("#232a3f"), 1))
    p.setBrush(QColor("#11141d"))
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)


def panel_title(p, w, text, badge=None):
    f = QFont(p.font()); f.setPointSize(9); f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#7c86ad"))
    p.drawText(QRectF(16, 9, w - 32, 14), Qt.AlignLeft | Qt.AlignVCenter, text)
    if badge:
        p.setPen(QColor("#4a5478"))
        f2 = QFont(p.font()); f2.setPointSize(8)
        p.setFont(f2)
        p.drawText(QRectF(16, 9, w - 32, 14), Qt.AlignRight | Qt.AlignVCenter, badge)


# ═══════════════════════════════════════════════════════════════════
#  HISTOGRAM
# ═══════════════════════════════════════════════════════════════════
class HistogramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self.labels, self.disp, self.target, self.pulse = [], [], [], []
        self.raw, self.wlen = [], 1
        self.title, self.hover = "CHARACTER FREQUENCY", -1

    def set_labels(self, labels):
        n = len(labels)
        self.labels = list(labels)
        self.disp, self.target, self.pulse = [0.0] * n, [0.0] * n, [0.0] * n
        self.raw, self.wlen = [0] * n, 1
        self.update()

    def set_title(self, t):
        if t != self.title:
            self.title = t
            self.update()

    def set_targets(self, values):
        m = max(values, default=0) or 1
        self.target = [v / m for v in values]

    def set_stats(self, counts, wlen):
        self.raw, self.wlen = list(counts), max(1, wlen)

    def pulse_char(self, i):
        if 0 <= i < len(self.pulse):
            self.pulse[i] = 1.0

    def step(self, ease=0.22, decay=0.88):
        for i in range(len(self.disp)):
            self.disp[i] += (self.target[i] - self.disp[i]) * ease
            self.pulse[i] *= decay
        self.update()

    def _geom(self):
        mL, mR, mT, mB = 48, 20, 36, 46
        return QRectF(mL, mT, max(10, self.width() - mL - mR),
                      max(10, self.height() - mT - mB))

    def mouseMoveEvent(self, e):
        g, n = self._geom(), len(self.labels)
        i = -1
        if n and g.left() <= e.position().x() <= g.right():
            i = max(0, min(n - 1, int((e.position().x() - g.left()) / (g.width() / n))))
        if i != self.hover:
            self.hover = i
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        paint_panel(p, w, h)
        panel_title(p, w, self.title, f"window {fmt_num(self.wlen)}")

        g = self._geom()
        base = g.bottom()
        n = len(self.labels)

        f_s = QFont(p.font()); f_s.setPointSize(8)
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = base - g.height() * frac
            p.setFont(f_s)
            p.setPen(QPen(QColor("#1c2133"), 1))
            p.drawLine(QPointF(g.left(), y), QPointF(g.right(), y))
            p.setPen(QColor("#525c80"))
            p.drawText(QRectF(0, y - 7, g.left() - 8, 14),
                       Qt.AlignRight | Qt.AlignVCenter, f"{frac * 100:.0f}%")

        if n == 0:
            p.setPen(QColor("#4a5275"))
            p.drawText(self.rect(), Qt.AlignCenter, "Waiting for data…")
            p.end()
            return

        bw = g.width() / n
        bar_w = bw * 0.62
        f_val = QFont(p.font()); f_val.setPointSize(8); f_val.setBold(True)
        f_lab = QFont(p.font()); f_lab.setPointSize(8)

        if 0 <= self.hover < n:  # hover column band
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 8))
            p.drawRect(QRectF(g.left() + self.hover * bw, g.top(), bw, g.height()))

        for i in range(n):
            cx = g.left() + i * bw + bw / 2
            frac = max(0.0, min(1.0, self.disp[i]))
            pulse = self.pulse[i]
            bh = g.height() * frac
            x = cx - bar_w / 2
            col = QColor(PALETTE[i % len(PALETTE)])

            if bh > 2:  # reflection
                rh = min(16, bh * 0.3)
                rg = QLinearGradient(x, base + 2, x, base + 2 + rh)
                rg.setColorAt(0, C(col.name(), 55))
                rg.setColorAt(1, C(col.name(), 0))
                p.fillRect(QRectF(x, base + 2, bar_w, rh), QBrush(rg))

            sg = QRadialGradient(cx, base, bar_w)  # ground shadow
            sg.setColorAt(0, QColor(0, 0, 0, 90))
            sg.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(cx - bar_w, base - 3, bar_w * 2, 6), QBrush(sg))

            if bh > 0.5:
                path = rounded_top_path(x, base - bh, bar_w, bh, 6)
                grad = QLinearGradient(x, base - bh, x, base)
                grad.setColorAt(0, col.lighter(145))
                grad.setColorAt(0.55, col)
                grad.setColorAt(1, col.darker(155))
                p.fillPath(path, grad)

                gloss = QLinearGradient(x, base - bh, x, base - bh * 0.35)
                gloss.setColorAt(0, QColor(255, 255, 255, 55))
                gloss.setColorAt(1, QColor(255, 255, 255, 0))
                p.fillPath(rounded_top_path(x + bar_w * 0.14, base - bh,
                                            bar_w * 0.72, bh * 0.65, 5), gloss)

                if pulse > 0.03:
                    for k in range(2):
                        pen = QPen(C(col.name(), int(100 * pulse * (1 - k * 0.4))))
                        pen.setWidthF(2 + k * 3)
                        p.setPen(pen); p.setBrush(Qt.NoBrush)
                        p.drawPath(path)
                if i == self.hover:
                    pen = QPen(QColor(255, 255, 255, 190)); pen.setWidthF(1.6)
                    p.setPen(pen); p.setBrush(Qt.NoBrush); p.drawPath(path)

                if bh > 18:  # value pill
                    txt = f"{frac * 100:.0f}%"
                    fm = QFontMetricsF(f_val)
                    pw = fm.horizontalAdvance(txt) + 12
                    pill = QRectF(cx - pw / 2, base - bh - 20, pw, 15)
                    p.setPen(Qt.NoPen)
                    p.setBrush(C("#1b2032", 235))
                    p.drawRoundedRect(pill, 7, 7)
                    p.setPen(QColor("#e8ecff")); p.setFont(f_val)
                    p.drawText(pill, Qt.AlignCenter, txt)

            p.setFont(f_lab)
            p.setPen(QColor(col.name()) if (pulse > 0.15 or i == self.hover)
                     else QColor("#7c86ad"))
            p.drawText(QRectF(g.left() + i * bw, base + 8, bw, 32),
                       Qt.AlignHCenter | Qt.AlignTop, self.labels[i])

        p.setPen(QPen(QColor("#333c5c"), 1.4))
        p.drawLine(QPointF(g.left(), base), QPointF(g.right(), base))

        if 0 <= self.hover < n:  # tooltip
            cnt = self.raw[self.hover]
            txt = (f"{self.labels[self.hover]}   {fmt_num(cnt)}   "
                   f"{cnt / self.wlen * 100:.1f}% of window")
            fm = QFontMetricsF(f_val)
            tw = fm.horizontalAdvance(txt) + 20
            tx = max(8, min(w - tw - 8, g.left() + self.hover * bw + bw / 2 - tw / 2))
            box = QRectF(tx, 28, tw, 22)
            p.setPen(Qt.NoPen); p.setBrush(C("#05070d", 240))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(C(PALETTE[self.hover % len(PALETTE)])); p.setFont(f_val)
            p.drawText(box, Qt.AlignCenter, txt)
        p.end()


# ═══════════════════════════════════════════════════════════════════
#  SPEED CHART (throughput)
# ═══════════════════════════════════════════════════════════════════
class SpeedChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.samples = deque(maxlen=160)
        self.phase = 0.0
        self.current = 0.0

    def add_sample(self, v):
        v = max(0.0, v)
        self.samples.append(v)
        self.current = v

    def step(self):
        self.phase += 0.045
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        paint_panel(p, w, h)

        mL, mR, mT, mB = 46, 14, 34, 18
        g = QRectF(mL, mT, max(10, w - mL - mR), max(10, h - mT - mB))
        pts = list(self.samples)
        ceil = (max(pts) * 1.15) if pts else 1.0
        if ceil <= 0:
            ceil = 1.0

        f_s = QFont(p.font()); f_s.setPointSize(8)
        for frac in (0.0, 0.5, 1.0):
            y = g.bottom() - g.height() * frac
            p.setFont(f_s)
            p.setPen(QPen(QColor("#1c2133"), 1))
            p.drawLine(QPointF(g.left(), y), QPointF(g.right(), y))
            p.setPen(QColor("#525c80"))
            p.drawText(QRectF(0, y - 7, g.left() - 8, 14),
                       Qt.AlignRight | Qt.AlignVCenter, fmt_short(ceil * frac))

        accent = QColor(PALETTE[5])
        if len(pts) >= 2:
            def X(i):
                return g.left() + g.width() * i / (len(pts) - 1)

            def Y(v):
                return g.bottom() - g.height() * min(1.0, v / ceil)

            path = QPainterPath(QPointF(X(0), Y(pts[0])))
            for i in range(1, len(pts)):
                prev = QPointF(X(i - 1), Y(pts[i - 1]))
                cur = QPointF(X(i), Y(pts[i]))
                path.quadTo(prev, (prev + cur) / 2)
            path.lineTo(QPointF(X(len(pts) - 1), Y(pts[-1])))

            fill = QPainterPath(path)
            fill.lineTo(QPointF(g.right(), g.bottom()))
            fill.lineTo(QPointF(g.left(), g.bottom()))
            vg = QLinearGradient(0, g.top(), 0, g.bottom())
            vg.setColorAt(0, C(accent.name(), 85))
            vg.setColorAt(1, C(accent.name(), 0))
            p.fillPath(fill, vg)

            glow = QPen(C(accent.name(), 70)); glow.setWidthF(6)
            p.setPen(glow); p.setBrush(Qt.NoBrush); p.drawPath(path)
            line = QPen(accent); line.setWidthF(2)
            p.setPen(line); p.drawPath(path)

            last = QPointF(X(len(pts) - 1), Y(pts[-1]))
            halo_r = 7 + 3 * math.sin(self.phase * 2 * math.pi)
            hg = QRadialGradient(last, halo_r * 2)
            hg.setColorAt(0, C(accent.name(), 160))
            hg.setColorAt(1, C(accent.name(), 0))
            p.setPen(Qt.NoPen); p.setBrush(QBrush(hg))
            p.drawEllipse(last, halo_r * 2, halo_r * 2)
            p.setBrush(QColor("white"))
            p.drawEllipse(last, 3.2, 3.2)

        f_t = QFont(p.font()); f_t.setPointSize(9); f_t.setBold(True)
        p.setFont(f_t); p.setPen(QColor("#7c86ad"))
        p.drawText(QRectF(16, 9, w - 32, 14), Qt.AlignLeft | Qt.AlignVCenter,
                   "THROUGHPUT — permutations / second")

        badge = f"{fmt_short(self.current)}/s"
        fm = QFontMetricsF(f_t)
        bwid = fm.horizontalAdvance(badge) + 16
        box = QRectF(w - bwid - 14, 7, bwid, 18)
        p.setPen(Qt.NoPen); p.setBrush(C("#1b2032", 235))
        p.drawRoundedRect(box, 9, 9)
        p.setPen(accent); p.setFont(f_t)
        p.drawText(box, Qt.AlignCenter, badge)
        p.end()


# ═══════════════════════════════════════════════════════════════════
#  HEATMAP — character × position
# ═══════════════════════════════════════════════════════════════════
class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.n = 0
        self.labels = []
        self.disp, self.target, self.raw = [], [], []
        self.hover = (-1, -1)
        self._cells = None

    def set_size(self, n, labels):
        self.n = n
        self.labels = list(labels)
        self.disp = [[0.0] * n for _ in range(n)]
        self.target = [[0.0] * n for _ in range(n)]
        self.raw = [[0] * n for _ in range(n)]
        self.hover = (-1, -1)
        self.update()

    def set_matrix(self, counts2d):
        m = max((max(row) for row in counts2d), default=0) or 1
        for i in range(self.n):
            for j in range(self.n):
                self.target[i][j] = counts2d[i][j] / m
                self.raw[i][j] = counts2d[i][j]

    def step(self, ease=0.20):
        for i in range(self.n):
            for j in range(self.n):
                self.disp[i][j] += (self.target[i][j] - self.disp[i][j]) * ease
        self.update()

    def mouseMoveEvent(self, e):
        hit = (-1, -1)
        if self._cells:
            x0, y0, cs, gap, n = self._cells
            j = int((e.position().x() - x0) // (cs + gap))
            i = int((e.position().y() - y0) // (cs + gap))
            if 0 <= i < n and 0 <= j < n:
                hit = (i, j)
        if hit != self.hover:
            self.hover = hit
            self.update()

    def leaveEvent(self, e):
        self.hover = (-1, -1)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        paint_panel(p, w, h)
        panel_title(p, w, "POSITION MAP — character × position")

        n = self.n
        if n == 0:
            p.setPen(QColor("#4a5275"))
            p.drawText(self.rect(), Qt.AlignCenter, "Waiting for data…")
            p.end()
            return

        mL, mT, mR, mB = 56, 34, 16, 14
        avail_w, avail_h = w - mL - mR, h - mT - mB
        gap = 4
        cs = max(8, min(avail_w / n - gap, avail_h / n - gap))
        block_w, block_h = n * cs + (n - 1) * gap, n * cs + (n - 1) * gap
        x0 = mL + (avail_w - block_w) / 2
        y0 = mT + (avail_h - block_h) / 2
        self._cells = (x0, y0, cs, gap, n)

        f_s = QFont(p.font()); f_s.setPointSize(8)
        p.setFont(f_s)
        for j in range(n):  # column labels
            p.setPen(QColor("#525c80"))
            p.drawText(QRectF(x0 + j * (cs + gap), y0 - 16, cs, 12),
                       Qt.AlignCenter, f"P{j + 1}")
        for i in range(n):  # row labels, palette-colored
            p.setPen(QColor(PALETTE[i % len(PALETTE)]))
            p.drawText(QRectF(8, y0 + i * (cs + gap), mL - 14, cs),
                       Qt.AlignRight | Qt.AlignVCenter, self.labels[i])

        mx_i = mx_j = 0
        mx_v = -1
        for i in range(n):
            for j in range(n):
                if self.raw[i][j] > mx_v:
                    mx_v, mx_i, mx_j = self.raw[i][j], i, j

        for i in range(n):
            col = QColor(PALETTE[i % len(PALETTE)])
            for j in range(n):
                v = max(0.0, min(1.0, self.disp[i][j]))
                r = QRectF(x0 + j * (cs + gap), y0 + i * (cs + gap), cs, cs)
                p.setPen(Qt.NoPen)
                p.setBrush(C(col.name(), int(26 + 226 * v)))
                p.drawRoundedRect(r, 5, 5)
                if v > 0.45 and cs >= 34:
                    p.setPen(QColor(255, 255, 255, 210))
                    p.setFont(f_s)
                    p.drawText(r, Qt.AlignCenter, fmt_short(self.raw[i][j]))

        r = QRectF(x0 + mx_j * (cs + gap) - 1.5, y0 + mx_i * (cs + gap) - 1.5,
                   cs + 3, cs + 3)
        pen = QPen(QColor(255, 255, 255, 150)); pen.setWidthF(1.5)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 6, 6)

        if self.hover != (-1, -1):  # tooltip
            i, j = self.hover
            cnt = self.raw[i][j]
            total = sum(sum(row) for row in self.raw) or 1
            txt = (f"{self.labels[i]} @ P{j + 1}   {fmt_num(cnt)}   "
                   f"{cnt / total * 100:.1f}%")
            f_b = QFont(p.font()); f_b.setPointSize(8); f_b.setBold(True)
            fm = QFontMetricsF(f_b)
            tw = fm.horizontalAdvance(txt) + 20
            tx = max(8, min(w - tw - 8, x0 + j * (cs + gap) - tw / 2))
            box = QRectF(tx, 28, tw, 22)
            p.setPen(Qt.NoPen); p.setBrush(C("#05070d", 240))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(C(PALETTE[i % len(PALETTE)])); p.setFont(f_b)
            p.drawText(box, Qt.AlignCenter, txt)
        p.end()


# ═══════════════════════════════════════════════════════════════════
#  PROGRESS RING
# ═══════════════════════════════════════════════════════════════════
class ProgressRingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 220)
        self.disp, self.target = 0.0, 0.0
        self.total, self.eta, self.done = 0, "—", False
        self.phase = 0.0

    def set_total(self, total):
        self.total = total

    def set_progress(self, generated):
        self.target = generated / self.total if self.total else 0.0

    def set_eta(self, text):
        self.eta = text

    def set_done(self, done):
        self.done = done

    def step(self):
        self.phase += 0.05
        self.disp += (self.target - self.disp) * 0.12
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        paint_panel(p, w, h)
        cx, cy = w / 2, h / 2 + 4
        R = min(w, h) / 2 - 26
        arc_rect = QRectF(cx - R, cy - R, 2 * R, 2 * R)
        penw = 12

        p.setBrush(Qt.NoBrush)
        track = QPen(QColor("#1b2130")); track.setWidthF(penw)
        track.setCapStyle(Qt.RoundCap)
        p.setPen(track)
        p.drawArc(arc_rect, 90 * 16, -360 * 16)

        frac = max(0.0, min(1.0, self.disp))
        if frac > 0.002:
            grad = QConicalGradient(cx, cy, 90)
            grad.setColorAt(0.0, ACCENT)
            grad.setColorAt(1.0, ACCENT2)
            glow = QPen(QBrush(grad), penw + 9, Qt.SolidLine, Qt.RoundCap)
            glow.setColor(C(ACCENT.name(), 45))
            p.setPen(glow)
            p.drawArc(arc_rect, 90 * 16, int(-360 * 16 * frac))
            main = QPen(QBrush(grad), penw, Qt.SolidLine, Qt.RoundCap)
            p.setPen(main)
            p.drawArc(arc_rect, 90 * 16, int(-360 * 16 * frac))
            a = math.radians(90 - 360 * frac)  # knob dot
            kx, ky = cx + R * math.cos(a), cy - R * math.sin(a)
            hg = QRadialGradient(kx, ky, 14)
            hg.setColorAt(0, C(ACCENT.name(), 150))
            hg.setColorAt(1, C(ACCENT.name(), 0))
            p.setPen(Qt.NoPen); p.setBrush(QBrush(hg))
            p.drawEllipse(QPointF(kx, ky), 14, 14)
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(kx, ky), 4, 4)

        if self.done:  # celebration pulse
            alpha = 110 + 90 * math.sin(self.phase * 3)
            pen = QPen(C("#3fd0a4", int(alpha))); pen.setWidthF(2)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), R + 10, R + 10)

        f_big = QFont(p.font()); f_big.setPointSize(21); f_big.setBold(True)
        f_mid = QFont(p.font()); f_mid.setPointSize(8)
        f_eta = QFont(p.font()); f_eta.setPointSize(9); f_eta.setBold(True)

        p.setFont(f_big); p.setPen(QColor("#e8ecff"))
        p.drawText(QRectF(0, cy - 26, w, 26), Qt.AlignCenter, f"{frac * 100:.1f}%")
        p.setFont(f_mid); p.setPen(QColor("#6b75a0"))
        p.drawText(QRectF(0, cy + 2, w, 14), Qt.AlignCenter,
                   f"of n! = {fmt_num(self.total)}")
        p.setFont(f_eta)
        p.setPen(C("#3fd0a4") if self.done else C(ACCENT.name()))
        p.drawText(QRectF(0, cy + 18, w, 16), Qt.AlignCenter,
                   "✓ COMPLETE" if self.done else self.eta)
        p.end()


# ═══════════════════════════════════════════════════════════════════
#  PROGRAM CHIPS — current permutation as colored cards
# ═══════════════════════════════════════════════════════════════════
class ChipsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.labels, self.indices, self.active = [], [], -1
        self.pulse = 0.0
        self.started = False

    def set_perm(self, labels, indices, active):
        self.labels, self.indices, self.active = list(labels), list(indices), active
        self.started = True
        self.pulse = 1.0
        self.update()

    def clear(self):
        self.started = False
        self.active = -1
        self.pulse = 0.0
        self.update()

    def step(self, decay=0.90):
        self.pulse *= decay
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        paint_panel(p, w, h)
        panel_title(p, w, "CURRENT CANDIDATE PROGRAM")

        n = len(self.indices)
        if n == 0 or not self.started:
            p.setPen(QColor("#4a5275"))
            p.drawText(QRectF(0, 30, w, h - 30), Qt.AlignCenter,
                       "press  Start  to stream permutations")
            p.end()
            return

        long_lbl = any(len(s) > 2 for s in self.labels)
        ch_h = 42
        max_cw = 110 if long_lbl else 78
        gap = 10
        cw = min(max_cw, (w - 40 - (n - 1) * gap) / n)
        total = n * cw + (n - 1) * gap
        x0 = (w - total) / 2
        y0 = 32 + (h - 32 - ch_h) / 2

        f_pos = QFont(p.font()); f_pos.setPointSize(7)
        f_ch = mono_font(11 if long_lbl else 17, bold=True)
        for i in range(n):
            x = x0 + i * (cw + gap)
            col = QColor(PALETTE[self.indices[i] % len(PALETTE)])
            chip = QRectF(x, y0, cw, ch_h)
            scale = 1.0 + 0.07 * self.pulse if i == self.active else 1.0
            cx, cy = chip.center().x(), chip.center().y()
            chip = QRectF(cx - cw / 2 * scale, cy - ch_h / 2 * scale,
                          cw * scale, ch_h * scale)

            if i == self.active and self.pulse > 0.05:
                pen = QPen(C(col.name(), int(150 * self.pulse)))
                pen.setWidthF(6)
                p.setPen(pen); p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(chip.adjusted(-2, -2, 2, 2), 12, 12)

            p.setPen(Qt.NoPen)
            p.setBrush(C(col.name(), 36))
            p.drawRoundedRect(chip, 10, 10)
            pen = QPen(C(col.name(), 210))
            pen.setWidthF(2.2 if i == self.active else 1.2)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(chip, 10, 10)

            p.setFont(f_pos); p.setPen(QColor("#5d678c"))
            p.drawText(chip.adjusted(6, 3, -6, -3), Qt.AlignLeft | Qt.AlignTop,
                       f"P{i + 1}")
            p.setFont(f_ch); p.setPen(QColor("#eef1ff"))
            p.drawText(chip, Qt.AlignCenter, self.labels[i])
        p.end()


# ═══════════════════════════════════════════════════════════════════
#  STAT CARD
# ═══════════════════════════════════════════════════════════════════
class StatCard(QWidget):
    def __init__(self, title, color, parent=None):
        super().__init__(parent)
        self.setFixedHeight(62)
        self.title, self.color = title, QColor(color)
        self.value = "—"

    def set_value(self, v):
        if v != self.value:
            self.value = v
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        paint_panel(p, w, h, radius=10)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawRoundedRect(QRectF(12, 14, 4, h - 28), 2, 2)

        f_t = QFont(p.font()); f_t.setPointSize(8)
        f_v = QFont(p.font()); f_v.setPointSize(15); f_v.setBold(True)
        p.setFont(f_t); p.setPen(QColor("#6b75a0"))
        p.drawText(QRectF(26, 9, w - 34, 13), Qt.AlignLeft | Qt.AlignVCenter,
                   self.title)
        p.setFont(f_v); p.setPen(QColor("#e8ecff"))
        p.drawText(QRectF(26, 24, w - 34, 28), Qt.AlignLeft | Qt.AlignVCenter,
                   self.value)
        p.end()


# ═══════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unicode Permutation → Candidate Python Programs")
        self.resize(1180, 960)

        self.gen_timer = QTimer(self)
        self.gen_timer.timeout.connect(self.on_tick)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self.on_anim)

        self.pps, self.last_t, self.done = 0.0, None, False
        self._build_ui()
        self.reset_engine()
        self.anim_timer.start()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        # controls -------------------------------------------------
        row = QHBoxLayout()
        charset = QGroupBox("Character set (Unicode)")
        cf = QFormLayout(charset)
        self.n_spin = QSpinBox(); self.n_spin.setRange(2, 8); self.n_spin.setValue(5)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, MAX_CP); self.start_spin.setValue(1)
        cf.addRow("n (characters)", self.n_spin)
        cf.addRow("Start code point", self.start_spin)
        hint = QLabel("1 → control chars (U+0001…),  33 → !\"#$%…,  97 → abcde…")
        hint.setStyleSheet("color:#6b75a0; font-size:11px;")
        cf.addRow(hint)
        row.addWidget(charset)

        engine = QGroupBox("Generator / animation")
        ef = QFormLayout(engine)
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 50000); self.batch_spin.setValue(800)
        ef.addRow("Batch per tick", self.batch_spin)
        self.interval_slider = QSlider(Qt.Horizontal)
        self.interval_slider.setRange(5, 200); self.interval_slider.setValue(24)
        self.interval_lbl = QLabel("24 ms")
        iv = QHBoxLayout()
        iv.addWidget(self.interval_slider); iv.addWidget(self.interval_lbl)
        holder = QWidget(); holder.setLayout(iv)
        ef.addRow("Tick interval", holder)
        self.window_spin = QSpinBox()
        self.window_spin.setRange(50, 20000); self.window_spin.setValue(500)
        ef.addRow("Sliding window", self.window_spin)
        self.pos_combo = QComboBox()
        self.pos_combo.addItems(["First char", "Last char", "Random position",
                                 "All positions"])
        ef.addRow("Tally position", self.pos_combo)
        self.valid_check = QCheckBox("Syntax-check candidates (compile)")
        ef.addRow(self.valid_check)
        row.addWidget(engine)
        row.addStretch(1)
        root.addLayout(row)

        # buttons --------------------------------------------------
        btns = QHBoxLayout()
        self.start_btn = QPushButton("▶  Start")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.on_toggle)
        step_btn = QPushButton("Step"); step_btn.clicked.connect(self.on_tick)
        reset_btn = QPushButton("Reset"); reset_btn.clicked.connect(self.reset_engine)
        btns.addWidget(self.start_btn)
        btns.addWidget(step_btn)
        btns.addWidget(reset_btn)
        btns.addStretch(1)
        self.state_lbl = QLabel("Ready")
        btns.addWidget(self.state_lbl)
        root.addLayout(btns)

        # stat cards -----------------------------------------------
        cards = QHBoxLayout()
        self.card_gen = StatCard("GENERATED", PALETTE[0])
        self.card_speed = StatCard("THROUGHPUT", PALETTE[5])
        self.card_valid = StatCard("VALID PROGRAMS", PALETTE[4])
        self.card_eta = StatCard("ETA", PALETTE[3])
        for c in (self.card_gen, self.card_speed, self.card_valid, self.card_eta):
            cards.addWidget(c)
        root.addLayout(cards)

        # chips ------------------------------------------------------
        self.chips = ChipsWidget()
        root.addWidget(self.chips)

        # histogram + ring -------------------------------------------
        mid = QHBoxLayout()
        self.hist = HistogramWidget()
        mid.addWidget(self.hist, 1)
        self.ring = ProgressRingWidget()
        mid.addWidget(self.ring, 0, Qt.AlignTop)
        root.addLayout(mid, 1)

        # speed + heatmap --------------------------------------------
        bottom = QHBoxLayout()
        self.speed = SpeedChartWidget()
        bottom.addWidget(self.speed, 1)
        self.heat = HeatmapWidget()
        bottom.addWidget(self.heat, 1)
        root.addLayout(bottom, 1)

        # valid log ----------------------------------------------------
        log_box = QGroupBox("Candidates that are valid Python")
        lv = QVBoxLayout(log_box)
        self.valid_log = QPlainTextEdit()
        self.valid_log.setReadOnly(True)
        self.valid_log.setMaximumHeight(110)
        self.valid_log.setMaximumBlockCount(300)
        self.valid_log.setPlaceholderText("…permutations accepted by compile() appear here")
        lv.addWidget(self.valid_log)
        root.addWidget(log_box)

        # wiring ---------------------------------------------------------
        self.n_spin.valueChanged.connect(self.reset_engine)
        self.start_spin.valueChanged.connect(self.reset_engine)
        self.interval_slider.valueChanged.connect(self.on_interval)
        self.pos_combo.currentTextChanged.connect(lambda _: self.reset_stats())

    # ---------------------------------------------------------------
    def reset_engine(self):
        self.gen_timer.stop()
        self.start_btn.setText("▶  Start")
        n, start = self.n_spin.value(), self.start_spin.value()
        self.chars = [chr(start + i) for i in range(n)]
        self.char_index = {c: i for i, c in enumerate(self.chars)}
        self.labels = [char_label(ord(c)) for c in self.chars]
        self.total = math.factorial(n)
        self.perm_iter = permutations(self.chars)
        self.window = deque()
        self.counts = [0] * n
        self.matrix = [[0] * n for _ in range(n)]
        self.generated = self.valid_count = 0
        self.pps, self.last_t, self.done = 0.0, None, False

        self.hist.set_labels(self.labels)
        self.hist.set_title("CHARACTER FREQUENCY")
        self.hist.set_targets(self.counts)
        self.heat.set_size(n, self.labels)
        self.ring.set_total(self.total)
        self.ring.set_progress(0)
        self.ring.set_done(False)
        self.chips.clear()
        self.valid_log.clear()

        self.card_gen.set_value(f"0 / {fmt_short(self.total)}")
        self.card_speed.set_value("0 /s")
        self.card_valid.set_value("0")
        self.card_eta.set_value("—")
        self.set_state("Ready", PALETTE[4])

    def reset_stats(self):
        if not hasattr(self, "counts"):
            return
        self.gen_timer.stop()
        self.start_btn.setText("▶  Start")
        self.window.clear()
        self.counts = [0] * len(self.chars)
        self.matrix = [[0] * len(self.chars) for _ in range(len(self.chars))]
        self.hist.set_targets(self.counts)
        self.heat.set_matrix(self.matrix)

    def set_state(self, text, color):
        c = QColor(color)
        self.state_lbl.setText(text)
        self.state_lbl.setStyleSheet(
            f"color:{color}; background:{rgba(c, 0.12)};"
            f"border:1px solid {rgba(c, 0.35)}; border-radius:10px;"
            f"padding:3px 12px; font-weight:bold;")

    def on_interval(self, v):
        self.interval_lbl.setText(f"{v} ms")
        if self.gen_timer.isActive():
            self.gen_timer.setInterval(v)

    def on_anim(self):
        self.hist.step()
        self.heat.step()
        self.speed.step()
        self.ring.step()
        self.chips.step()

    def on_toggle(self):
        if self.gen_timer.isActive():
            self.gen_timer.stop()
            self.start_btn.setText("▶  Start")
            self.set_state("Paused", "#ffd866")
        else:
            if self.done:
                self.reset_engine()
            self.last_t = None
            self.gen_timer.start(self.interval_slider.value())
            self.start_btn.setText("⏸  Pause")
            self.set_state("Running", PALETTE[4])

    def on_tick(self):
        batch = self.batch_spin.value()
        W = self.window_spin.value()
        mode = self.pos_combo.currentText()
        check = self.valid_check.isChecked()
        n = len(self.chars)
        consumed = 0
        last_idxs, last_active = None, -1

        for perm in islice(self.perm_iter, batch):
            consumed += 1
            idxs = tuple(self.char_index[c] for c in perm)

            if mode == "First char":
                pi = 0
            elif mode == "Last char":
                pi = n - 1
            elif mode == "Random position":
                pi = random.randrange(n)
            else:
                pi = None  # all positions

            # histogram tally
            if pi is None:
                for ci in idxs:
                    self.counts[ci] += 1
                    self.hist.pulse_char(ci)
            else:
                self.counts[idxs[pi]] += 1
                self.hist.pulse_char(idxs[pi])

            # heatmap tally (always all positions)
            for j, ci in enumerate(idxs):
                self.matrix[ci][j] += 1

            self.window.append((idxs, pi))
            if len(self.window) > W:
                old, old_pi = self.window.popleft()
                if old_pi is None:
                    for ci in old:
                        self.counts[ci] -= 1
                else:
                    self.counts[old[old_pi]] -= 1
                for j, ci in enumerate(old):
                    self.matrix[ci][j] -= 1

            if check:
                try:
                    compile("".join(perm), "<perm>", "exec")
                except Exception:
                    pass
                else:
                    self.valid_count += 1
                    self.valid_log.appendPlainText(repr("".join(perm)))

            last_idxs, last_active = idxs, (pi if pi is not None else -1)

        if consumed == 0:
            self.gen_timer.stop()
            self.start_btn.setText("▶  Start")
            self.done = True
            self.ring.set_done(True)
            self.ring.set_eta("done")
            self.set_state(f"Done — all {self.total:,} generated", PALETTE[4])
            return

        self.generated += consumed
        self.hist.set_targets(self.counts)
        self.hist.set_stats(self.counts, len(self.window))
        self.heat.set_matrix(self.matrix)
        if last_idxs is not None:
            self.chips.set_perm(self.labels, last_idxs, last_active)
        self.ring.set_progress(self.generated)

        now = time.monotonic()
        if self.last_t is not None and now > self.last_t:
            inst = consumed / (now - self.last_t)
            self.pps = inst if self.pps == 0 else 0.85 * self.pps + 0.15 * inst
        self.last_t = now
        self.speed.add_sample(self.pps)

        self.card_gen.set_value(f"{fmt_num(self.generated)} / {fmt_short(self.total)}")
        self.card_speed.set_value(f"{fmt_short(self.pps)}/s")
        self.card_valid.set_value(fmt_num(self.valid_count))
        if self.pps > 0:
            self.card_eta.set_value(fmt_eta((self.total - self.generated) / self.pps))
            self.ring.set_eta(fmt_eta((self.total - self.generated) / self.pps))


STYLESHEET = """
QWidget { background:#0b0d14; color:#dde3f5; font-size:13px; }
QGroupBox { border:1px solid #232a3f; border-radius:10px; margin-top:12px;
            padding:8px; background:#11141d; }
QGroupBox::title { subcontrol-origin: margin; left:12px; padding:0 4px;
                   color:#7c86ad; }
QPushButton { background:#242b42; border:1px solid #333c5c; border-radius:7px;
              padding:6px 16px; }
QPushButton:hover { background:#2e3757; }
QPushButton#primary { background:#5b8cff; border:1px solid #7aa5ff;
                      color:#0b0d14; font-weight:bold; }
QPushButton#primary:hover { background:#7aa0ff; }
QSpinBox, QComboBox { background:#1a1f2e; border:1px solid #333c5c;
                      border-radius:5px; padding:3px 8px; }
QSlider::groove:horizontal { height:4px; background:#333c5c; border-radius:2px; }
QSlider::handle:horizontal { width:13px; margin:-5px 0; border-radius:6px;
                             background:#5b8cff; }
QPlainTextEdit { background:#0e1018; border:1px solid #232a3f; border-radius:8px;
                 font-family:Consolas,monospace; color:#a8d8b9; }
"""


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()