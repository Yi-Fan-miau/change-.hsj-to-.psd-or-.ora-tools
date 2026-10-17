#!/usr/bin/env python3
"""画世界Pro .hsj 转换器（现代深色 tkinter GUI）。

双击或在命令行运行:
    pythonw hsj2psd_gui.py
    pythonw hsj2psd_gui.py 草稿.hsj

转换核心（hsjconv / hsj2psd）保持不变，本文件只负责界面与交互。
"""

from __future__ import annotations

import ctypes
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk
from typing import Callable, Optional

from hsj2psd import convert, load_draft
from hsjconv import (
    CLIP_BOTTOM,
    CLIP_MIDDLE,
    CLIP_TOP,
    HsjError,
    LayerInfo,
)

APP_TITLE = "画世界Pro 草稿转换器"
APP_VERSION = "1.0.0"
FORMAT_LABELS = {"psd": "PSD", "ora": "ORA", "both": "PSD + ORA"}

# ---------------------------------------------------------------- 视觉规范
BG = "#0D0F16"
SURFACE = "#151925"
SURFACE_2 = "#1C2230"
SURFACE_3 = "#232B3C"
FIELD = "#10141E"
BORDER = "#2A3145"
BORDER_SOFT = "#222838"
TEXT = "#EDF1FA"
TEXT_2 = "#C7D0E3"
MUTED = "#98A2B8"
HINT = "#8A94AB"
ACCENT = "#6D4DFF"
ACCENT_HI = "#8B72FF"
ACCENT_DEEP = "#5438DA"
ACCENT_2 = "#2BD9F0"
SUCCESS = "#37D6A0"
WARN = "#F5C451"
ERROR = "#FF7B8A"
PINK = "#FF6BAE"


# ---------------------------------------------------------------- 基础工具
def resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


_IMAGE_CACHE: dict[str, tk.PhotoImage] = {}


def photo(rel: str) -> Optional[tk.PhotoImage]:
    path = resource_path(rel)
    img = _IMAGE_CACHE.get(path)
    if img is None:
        try:
            img = tk.PhotoImage(file=path)
        except tk.TclError:
            return None
        _IMAGE_CACHE[path] = img
    return img


def _enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def _dark_titlebar(window: tk.Misc) -> None:
    """Windows 11 深色标题栏；失败时静默忽略。"""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE 新旧编号
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
        caption = ctypes.c_int(0x0017100E)  # COLORREF #0E1017
        text = ctypes.c_int(0x00F2EEEA)     # COLORREF #EAEEF2
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))
    except Exception:
        pass


def _blend(a: str, b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    ca = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    cb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}"
                         for x, y in zip(ca, cb))


def _round_points(x1: float, y1: float, x2: float, y2: float,
                  r: float, steps: int = 8) -> list[float]:
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts: list[float] = []
    centers = (
        (x2 - r, y1 + r, -90),
        (x2 - r, y2 - r, 0),
        (x1 + r, y2 - r, 90),
        (x1 + r, y1 + r, 180),
    )
    for cx, cy, start in centers:
        for i in range(steps + 1):
            ang = math.radians(start + 90 * i / steps)
            pts.extend((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _row_span(y: float, w: float, h: float, r: float) -> tuple[float, float]:
    if y < r:
        dx = r - math.sqrt(max(0.0, r * r - (r - y) ** 2))
    elif y > h - r:
        dx = r - math.sqrt(max(0.0, r * r - (y - (h - r)) ** 2))
    else:
        dx = 0.0
    return dx, w - dx


def _open_folder(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def _sanitize_filename(name: str) -> str:
    name = name.strip()
    if name.lower().endswith((".psd", ".ora")):
        name = os.path.splitext(name)[0]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name


def _pick_font(root: tk.Misc, candidates: tuple[str, ...]) -> str:
    installed = set(tkfont.families(root))
    for name in candidates:
        if name in installed:
            return name
    return "TkDefaultFont"


# ---------------------------------------------------------------- 自绘控件
class Pill(tk.Canvas):
    def __init__(self, master: tk.Misc, text: str, *, bg: str = SURFACE,
                 fill: str = "#24204A", fg: str = "#C3B6FF",
                 font: tuple = ("Microsoft YaHei UI", 8),
                 pad_x: int = 9, height: int = 22):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         height=height)
        self._fill, self._fg, self._font = fill, fg, font
        self._pad_x, self._height = pad_x, height
        self._text = text
        self._redraw()

    def set(self, text: str) -> None:
        self._text = text
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        f = tkfont.Font(font=self._font)
        w = f.measure(self._text) + self._pad_x * 2
        h = max(self._height, f.metrics("linespace") + 8)
        self.configure(width=w, height=h)
        self.create_polygon(
            _round_points(0, 0, w - 1, h - 1, (h - 1) / 2),
            fill=self._fill, outline="")
        self.create_text(w / 2, h / 2, text=self._text,
                         fill=self._fg, font=self._font, anchor="center")


class CanvasButton(tk.Canvas):
    """圆角按钮：支持主按钮渐变、图标、快捷键提示、键盘焦点。"""

    def __init__(self, master: tk.Misc, text: str,
                 command: Optional[Callable[[], None]] = None, *,
                 variant: str = "secondary", icon: Optional[str] = None,
                 ui: float = 1.0, width: Optional[int] = None,
                 height: Optional[int] = None,
                 font: Optional[tuple] = None, shortcut: str = "",
                 bg: str = SURFACE, radius: Optional[int] = None,
                 icon_size: Optional[int] = None):
        self.ui = ui
        self.variant = variant
        self._text = text
        self._command = command
        self._shortcut = shortcut
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._focused = False
        self._icon_name = icon
        self._icon_size = icon_size or (24 if ui > 1.12 else 20)
        self._font = font or (
            "Microsoft YaHei UI", 10,
            "bold" if variant == "primary" else "normal")
        self._radius = radius if radius is not None else int(10 * ui)
        self._pad = int(16 * ui)
        self._icon = photo(f"assets/icons/{icon}_light_{self._icon_size}.png") \
            if icon else None
        self._icon_muted = photo(
            f"assets/icons/{icon}_muted_{self._icon_size}.png") if icon else None

        f = tkfont.Font(font=self._font)
        content = f.measure(text)
        if self._icon:
            content += self._icon_size + int(8 * ui)
        if shortcut:
            sf = tkfont.Font(family=self._font[0], size=8)
            content += int(12 * ui) + sf.measure(shortcut)
        needed = content + self._pad * 2
        min_h = f.metrics("linespace") + int(10 * ui)
        self._width = max(width, needed) if width is not None else needed
        self._height = (max(height, min_h) if height is not None
                        else max(int(38 * ui), min_h))
        super().__init__(master, width=self._width, height=self._height,
                         bg=bg, highlightthickness=0, bd=0, takefocus=1,
                         cursor="hand2")
        self._bg = bg
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Return>", lambda _e: self.invoke())
        self.bind("<space>", lambda _e: self.invoke())
        self.bind("<Configure>", self._on_configure)
        self._draw()

    # -- public ---------------------------------------------------------
    def invoke(self) -> None:
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self._pressed = self._hover = False
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_text(self, text: str) -> None:
        self._text = text
        self._draw()

    # -- events ---------------------------------------------------------
    def _on_configure(self, event: tk.Event) -> None:
        if (event.width, event.height) != (self._width, self._height):
            self._width, self._height = event.width, event.height
            self._draw()

    def _on_enter(self, _e: tk.Event) -> None:
        if self._enabled:
            self._hover = True
            self._draw()

    def _on_leave(self, _e: tk.Event) -> None:
        self._hover = self._pressed = False
        self._draw()

    def _on_press(self, _e: tk.Event) -> None:
        if not self._enabled:
            return
        self.focus_set()
        self._pressed = True
        self._draw()

    def _on_release(self, event: tk.Event) -> None:
        if not self._enabled:
            return
        was = self._pressed
        self._pressed = False
        inside = 0 <= event.x <= self._width and 0 <= event.y <= self._height
        self._draw()
        if was and inside:
            self.invoke()

    def _on_focus_in(self, _e: tk.Event) -> None:
        self._focused = True
        self._draw()

    def _on_focus_out(self, _e: tk.Event) -> None:
        self._focused = False
        self._draw()

    # -- drawing --------------------------------------------------------
    def _draw(self) -> None:
        self.delete("all")
        w, h = self._width, self._height
        r = min(self._radius, h / 2)
        if self.variant == "primary":
            if not self._enabled:
                top, bottom = "#3A3550", "#302C45"
            elif self._pressed:
                top, bottom = "#5A40CF", "#472FB8"
            elif self._hover:
                top, bottom = "#937BFF", "#674BF4"
            else:
                top, bottom = "#876BFF", "#5B3FE0"
            for y in range(h):
                x1, x2 = _row_span(y + 0.5, w, h, r)
                if x2 > x1:
                    self.create_line(x1, y + 0.5, x2, y + 0.5,
                                     fill=_blend(top, bottom, y / max(1, h - 1)),
                                     width=1)
            # 顶部内侧高光
            self.create_line(r, 1, w - r, 1,
                             fill=_blend(top, "#FFFFFF", 0.22), width=1)
        else:
            if not self._enabled:
                bg, border, fg = SURFACE, BORDER_SOFT, HINT
            elif self.variant == "ghost":
                bg = SURFACE_2 if self._hover else self._bg
                border = SURFACE_3 if self._hover else bg
                fg = TEXT if self._hover else MUTED
            else:
                bg = SURFACE_3 if self._hover else SURFACE_2
                border = "#3A4664" if self._hover else BORDER
                fg = TEXT
            if self._pressed and self._enabled:
                bg = _blend(bg, "#000000", 0.16)
            self.create_polygon(_round_points(0.5, 0.5, w - 0.5, h - 0.5, r),
                                fill=bg, outline=border, width=1)

        if self.variant == "primary":
            fg = "#FFFFFF" if self._enabled else "#8B84A3"
            shortcut_fg = "#D9CEFF" if self._enabled else "#8B84A3"
        else:
            shortcut_fg = HINT
        if not self._enabled and self.variant != "primary":
            fg = HINT

        font = tkfont.Font(font=self._font)
        text_w = font.measure(self._text)
        icon_w = (self._icon_size + int(8 * self.ui)) if self._icon else 0
        short_w = 0
        short_font = tkfont.Font(family=self._font[0], size=8)
        if self._shortcut:
            short_w = int(12 * self.ui) + short_font.measure(self._shortcut)
        total = icon_w + text_w + short_w
        x = (w - total) / 2
        y = h / 2 + (1 if self._pressed and self._enabled else 0)
        if self._icon:
            img = self._icon if self._enabled else (self._icon_muted or self._icon)
            if self.variant != "primary" and not self._enabled:
                img = self._icon_muted or self._icon
            self.create_image(x, y, image=img, anchor="w")
            x += icon_w
        self.create_text(x, y, text=self._text, anchor="w",
                         fill=fg, font=self._font)
        x += text_w
        if self._shortcut:
            x += int(12 * self.ui)
            self.create_text(x, y, text=self._shortcut, anchor="w",
                             fill=shortcut_fg, font=short_font)

        if self._focused:
            self.create_polygon(
                _round_points(1.5, 1.5, w - 1.5, h - 1.5, max(2, r - 1)),
                fill="", outline=ACCENT_2, width=1)


class ToggleSwitch(tk.Canvas):
    def __init__(self, master: tk.Misc, text: str, hint: str,
                 variable: tk.BooleanVar,
                 command: Optional[Callable[[], None]] = None,
                 ui: float = 1.0, bg: str = SURFACE):
        self.ui = ui
        self._text, self._hint = text, hint
        self._var = variable
        self._command = command
        self._hover = False
        self._focused = False
        self._font = ("Microsoft YaHei UI", 9)
        self._hint_font = ("Microsoft YaHei UI", 8)
        self._title_lh = tkfont.Font(font=self._font).metrics("linespace")
        self._hint_lh = tkfont.Font(font=self._hint_font).metrics("linespace")
        height = (int(4 * ui) + self._title_lh + int(2 * ui)
                  + self._hint_lh + int(3 * ui))
        super().__init__(master, height=height, bg=bg,
                         highlightthickness=0, bd=0, takefocus=1,
                         cursor="hand2")
        self._cw = int(340 * ui)
        self._ch = height
        self.configure(width=self._cw)
        self._var.trace_add("write", lambda *_: self._draw())
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", lambda _e: self.toggle())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", self._on_focus)
        self.bind("<FocusOut>", self._on_focus)
        self.bind("<space>", lambda _e: self.toggle())
        self.bind("<Return>", lambda _e: self.toggle())
        self._draw()

    def toggle(self) -> None:
        self._var.set(not self._var.get())
        if self._command:
            self._command()

    def _on_configure(self, event: tk.Event) -> None:
        self._cw, self._ch = event.width, event.height
        self._draw()

    def _on_enter(self, _e: tk.Event) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _e: tk.Event) -> None:
        self._hover = False
        self._draw()

    def _on_focus(self, _e: tk.Event) -> None:
        self._focused = self.focus_get() is self
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._cw, self._ch
        ui = self.ui
        on = self._var.get()
        self.create_text(int(2 * ui), int(2 * ui), text=self._text,
                         anchor="nw", fill=TEXT if on else TEXT_2,
                         font=self._font)
        self.create_text(int(2 * ui),
                         int(2 * ui) + self._title_lh + int(1 * ui),
                         text=self._hint, anchor="nw", fill=HINT,
                         font=self._hint_font)
        tw, th = int(40 * ui), int(20 * ui)
        x2 = w - int(2 * ui)
        x1 = x2 - tw
        y1 = (h - th) / 2
        y2 = y1 + th
        track = ACCENT if on else "#2C3448"
        if on and self._hover:
            track = ACCENT_HI
        elif self._hover:
            track = "#3A4560"
        self.create_polygon(_round_points(x1, y1, x2, y2, th / 2),
                            fill=track, outline="")
        kd = int(14 * ui)
        kx = (x2 - kd - int(3 * ui)) if on else (x1 + int(3 * ui))
        ky = y1 + (th - kd) / 2
        knob = "#FFFFFF" if on else "#AAB3C7"
        self.create_oval(kx, ky, kx + kd, ky + kd, fill=knob, outline="")
        if self._focused:
            self.create_polygon(
                _round_points(0.5, 0.5, w - 0.5, h - 0.5, int(7 * ui)),
                fill="", outline=ACCENT_2, width=1)


class SegmentedControl(tk.Canvas):
    def __init__(self, master: tk.Misc, options: list[tuple[str, str]],
                 variable: tk.StringVar,
                 command: Optional[Callable[[], None]] = None,
                 ui: float = 1.0, bg: str = SURFACE):
        self.ui = ui
        self._items = options
        self._var = variable
        self._command = command
        self._hover = -1
        self._focused = False
        self._rects: list[tuple[float, float]] = []
        seg_font = tkfont.Font(family="Microsoft YaHei UI", size=9,
                               weight="bold")
        height = max(int(40 * ui),
                     seg_font.metrics("linespace") + int(14 * ui))
        super().__init__(master, height=height, bg=bg,
                         highlightthickness=0, bd=0, takefocus=1,
                         cursor="hand2")
        self._cw, self._ch = int(320 * ui), height
        self.configure(width=self._cw)
        self._var.trace_add("write", lambda *_: self._draw())
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", self._on_focus)
        self.bind("<FocusOut>", self._on_focus)
        self.bind("<Left>", lambda _e: self._move(-1))
        self.bind("<Right>", lambda _e: self._move(1))
        self.bind("<space>", lambda _e: self._select(self._var.get()))
        self._draw()

    def _on_configure(self, event: tk.Event) -> None:
        self._cw, self._ch = event.width, event.height
        self._draw()

    def _on_click(self, event: tk.Event) -> None:
        self.focus_set()
        for idx, (x1, x2) in enumerate(self._rects):
            if x1 <= event.x <= x2:
                self._select(self._items[idx][0])
                return

    def _on_motion(self, event: tk.Event) -> None:
        idx = -1
        for i, (x1, x2) in enumerate(self._rects):
            if x1 <= event.x <= x2:
                idx = i
                break
        if idx != self._hover:
            self._hover = idx
            self._draw()

    def _on_leave(self, _e: tk.Event) -> None:
        if self._hover != -1:
            self._hover = -1
            self._draw()

    def _on_focus(self, _e: tk.Event) -> None:
        self._focused = self.focus_get() is self
        self._draw()

    def _select(self, value: str) -> None:
        if value != self._var.get():
            self._var.set(value)
        if self._command:
            self._command()

    def _move(self, delta: int) -> None:
        values = [v for v, _ in self._items]
        try:
            idx = values.index(self._var.get())
        except ValueError:
            idx = 0
        self._select(values[(idx + delta) % len(values)])

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._cw, self._ch
        ui = self.ui
        pad = int(3 * ui)
        self.create_polygon(
            _round_points(0.5, 0.5, w - 0.5, h - 0.5, int(10 * ui)),
            fill="#0F131D", outline=BORDER_SOFT, width=1)
        seg_w = (w - pad * 2) / len(self._items)
        self._rects = []
        font = ("Microsoft YaHei UI", 9, "bold")
        for i, (value, label) in enumerate(self._items):
            x1 = pad + seg_w * i
            x2 = x1 + seg_w
            self._rects.append((x1, x2))
            active = value == self._var.get()
            if active:
                self.create_polygon(
                    _round_points(x1 + 2, pad + 1, x2 - 2, h - pad - 1,
                                  int(8 * ui)),
                    fill=ACCENT, outline=_blend(ACCENT, "#FFFFFF", 0.12),
                    width=1)
                fg = "#FFFFFF"
            else:
                if i == self._hover:
                    self.create_polygon(
                        _round_points(x1 + 2, pad + 2, x2 - 2, h - pad - 2,
                                      int(8 * ui)),
                        fill=SURFACE_2, outline="")
                fg = MUTED
            self.create_text((x1 + x2) / 2, h / 2, text=label,
                             fill=fg, font=font, anchor="center")
        if self._focused:
            self.create_polygon(
                _round_points(1.5, 1.5, w - 1.5, h - 1.5, int(9 * ui)),
                fill="", outline=ACCENT_2, width=1)


class PulseBar(tk.Canvas):
    def __init__(self, master: tk.Misc, ui: float = 1.0,
                 width: int = 200, bg: str = BG):
        self.ui = ui
        self.active = False
        self.phase = 0.0
        self._after: Optional[str] = None
        super().__init__(master, height=int(10 * ui), width=width,
                         bg=bg, highlightthickness=0, bd=0)
        self._cw = width
        self.bind("<Configure>", self._on_configure)
        self._draw()

    def _on_configure(self, event: tk.Event) -> None:
        self._cw = event.width
        self._draw()

    def start(self) -> None:
        if self.active:
            return
        self.active = True
        self.phase = 0.0
        self._tick()

    def stop(self) -> None:
        self.active = False
        if self._after:
            try:
                self.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        self._draw()

    def _tick(self) -> None:
        if not self.active:
            return
        self.phase = (self.phase + 0.022) % 1.35
        self._draw()
        self._after = self.after(22, self._tick)

    def _draw(self) -> None:
        self.delete("all")
        w = max(2, self._cw)
        h = int(self.cget("height"))
        y = h / 2
        self.create_line(3, y, w - 3, y, fill="#2A3245",
                         width=max(3, int(5 * self.ui)), capstyle="round")
        if self.active:
            seg = max(int(28 * self.ui), int(w * 0.24))
            x = self.phase * (w + seg) - seg
            x1, x2 = max(3, x), min(w - 3, x + seg)
            if x2 > x1:
                self.create_line(x1, y, x2, y, fill=ACCENT_2,
                                 width=max(3, int(5 * self.ui)),
                                 capstyle="round")


class Card(tk.Frame):
    def __init__(self, master: tk.Misc, title: str, subtitle: str = "",
                 ui: float = 1.0):
        self.ui = ui
        super().__init__(master, bg=SURFACE, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=BORDER)
        pad = int(16 * ui)
        self.inner = tk.Frame(self, bg=SURFACE)
        self.inner.pack(fill="both", expand=True, padx=pad, pady=int(14 * ui))
        self.header = tk.Frame(self.inner, bg=SURFACE)
        self.header.pack(fill="x", pady=(0, int(10 * ui)))
        self.header.columnconfigure(1, weight=1)
        accent = tk.Frame(self.header, bg=ACCENT, width=max(2, int(3 * ui)))
        accent.grid(row=0, column=0, rowspan=2, sticky="ns",
                    padx=(0, int(9 * ui)))
        tk.Label(self.header, text=title, bg=SURFACE, fg=TEXT,
                 font=("Microsoft YaHei UI", 11, "bold"),
                 anchor="w").grid(row=0, column=1, sticky="w")
        if subtitle:
            tk.Label(self.header, text=subtitle, bg=SURFACE, fg=HINT,
                     font=("Microsoft YaHei UI", 8), anchor="w").grid(
                row=1, column=1, sticky="w", pady=(int(2 * ui), 0))
        else:
            self.header.rowconfigure(1, minsize=int(2 * ui))
        self.header_right = tk.Frame(self.header, bg=SURFACE)
        self.header_right.grid(row=0, column=2, rowspan=2, sticky="e")
        self.body = tk.Frame(self.inner, bg=SURFACE)
        self.body.pack(fill="both", expand=True)


class LabeledEntry(tk.Frame):
    def __init__(self, master: tk.Misc, label: str,
                 variable: tk.StringVar, *, ui: float = 1.0,
                 browse_command: Optional[Callable[[], None]] = None,
                 browse_text: str = "浏览", suffix: str = "",
                 label_hint: str = "",
                 on_return: Optional[Callable[[], None]] = None,
                 mono: bool = False):
        self.ui = ui
        super().__init__(master, bg=SURFACE)
        top = tk.Frame(self, bg=SURFACE)
        top.pack(fill="x", pady=(0, int(5 * ui)))
        tk.Label(top, text=label, bg=SURFACE, fg=MUTED,
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(side="left")
        if label_hint:
            tk.Label(top, text=label_hint, bg=SURFACE, fg=HINT,
                     font=("Microsoft YaHei UI", 8), anchor="e").pack(side="right")
        row = tk.Frame(self, bg=SURFACE)
        row.pack(fill="x")
        self.border = tk.Frame(row, bg=FIELD, bd=0,
                               highlightthickness=1,
                               highlightbackground=BORDER,
                               highlightcolor=ACCENT)
        self.border.pack(side="left", fill="x", expand=True)
        family = ("Cascadia Mono", "Consolas") if mono else ("Microsoft YaHei UI",)
        font = (family[0], 10)
        self.entry = tk.Entry(
            self.border, textvariable=variable, relief="flat", bd=0,
            bg=FIELD, fg=TEXT, insertbackground=ACCENT_2,
            selectbackground="#33406A", selectforeground="#FFFFFF",
            font=font, highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True,
                        padx=int(10 * ui), ipady=int(7 * ui))
        if suffix:
            tk.Label(self.border, text=suffix, bg=FIELD, fg=HINT,
                     font=("Microsoft YaHei UI", 8)).pack(
                side="right", padx=(0, int(10 * ui)))
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        if on_return:
            self.entry.bind("<Return>", lambda _e: on_return())
        if browse_command:
            CanvasButton(
                row, browse_text, browse_command, variant="secondary",
                icon="folder", ui=ui, height=int(34 * ui),
                width=int(84 * ui), bg=SURFACE,
            ).pack(side="left", padx=(int(8 * ui), 0))

    def _focus_in(self, _e: tk.Event) -> None:
        self.border.configure(highlightbackground=ACCENT,
                              highlightcolor=ACCENT)

    def _focus_out(self, _e: tk.Event) -> None:
        self.border.configure(highlightbackground=BORDER,
                              highlightcolor=ACCENT)


# ---------------------------------------------------------------- 横幅
class HeaderBanner(tk.Canvas):
    def __init__(self, master: tk.Misc, ui: float,
                 on_about: Callable[[], None], family: str = "Microsoft YaHei UI"):
        self.ui = ui
        self._font_family = family
        self._on_about = on_about
        self._last = (0, 0)
        self._title_font = tkfont.Font(family=family, size=17, weight="bold")
        self._sub_font = tkfont.Font(family=family, size=9)
        self._title_lh = self._title_font.metrics("linespace")
        self._sub_lh = self._sub_font.metrics("linespace")
        header_h = max(
            int(88 * ui),
            self._title_lh + self._sub_lh + int(10 * ui) + int(20 * ui),
            64 + int(20 * ui),
        )
        super().__init__(master, height=header_h, bg=BG,
                         highlightthickness=0, bd=0)
        self._icon = photo("assets/app_icon_64.png")
        self._about_icon = photo("assets/icons/info_light_20.png")
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event: tk.Event) -> None:
        if (event.width, event.height) != self._last:
            self._last = (event.width, event.height)
            self._draw()

    def _glow(self, cx: float, cy: float, rx: float, ry: float,
              color: str, strength: float, base: str) -> None:
        steps = 22
        for i in range(steps, 0, -1):
            t = i / steps
            blend = strength * (1.0 - t) ** 1.7
            if blend <= 0.004:
                continue
            fill = _blend(base, color, blend)
            self.create_oval(cx - rx * t, cy - ry * t,
                             cx + rx * t, cy + ry * t,
                             fill=fill, outline="")

    def _sparkle(self, cx: float, cy: float, r: float, color: str) -> None:
        thin = r * 0.24
        self.create_polygon(
            cx, cy - r, cx + thin, cy - thin, cx + r, cy,
            cx + thin, cy + thin, cx, cy + r, cx - thin, cy + thin,
            cx - r, cy, cx - thin, cy - thin,
            fill=color, outline="")

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._last
        if w < 2 or h < 2:
            return
        ui = self.ui
        top, bottom = "#100E1E", "#181334"
        for y in range(h):
            self.create_line(0, y + 0.5, w, y + 0.5,
                             fill=_blend(top, bottom, y / max(1, h - 1)),
                             width=1)
        self._glow(w * 0.78, h * 0.12, w * 0.26, h * 1.5,
                   "#6B4BFF", 0.30, bottom)
        self._glow(w * 0.96, h * 0.95, w * 0.22, h * 1.2,
                   "#12C9E8", 0.20, bottom)
        self._glow(w * 0.48, h * 1.25, w * 0.42, h * 0.9,
                   "#FF4F9A", 0.08, bottom)
        # 斜向细线与星芒装饰
        self.create_line(w * 0.55, h * 0.02, w * 0.78, h * 0.98,
                         fill=_blend(bottom, "#FFFFFF", 0.045), width=1)
        self.create_line(w * 0.60, h * 0.02, w * 0.83, h * 0.98,
                         fill=_blend(bottom, "#FFFFFF", 0.03), width=1)
        self._sparkle(w * 0.69, h * 0.28, 5 * ui,
                      _blend(bottom, "#FFFFFF", 0.35))
        self._sparkle(w * 0.73, h * 0.66, 3 * ui,
                      _blend(bottom, ACCENT_2, 0.55))

        # 品牌区（按字体行高排版，避免高 DPI 下重叠）
        left = int(24 * ui)
        if self._icon:
            self.create_image(left, h / 2, image=self._icon, anchor="w")
        tx = left + 64 + int(16 * ui)
        show_sub = w > 760 * ui
        gap = int(4 * ui)
        group_h = self._title_lh + (gap + self._sub_lh if show_sub else 0)
        top = (h - group_h) / 2
        self.create_text(tx, top, text=APP_TITLE, anchor="nw",
                         fill="#F7F9FF", font=self._title_font)
        if show_sub:
            self.create_text(
                tx, top + self._title_lh + gap, anchor="nw",
                fill="#B4BCD4", font=self._sub_font,
                text="HSJ → PSD / ORA  ·  保留图层、混合模式与剪贴蒙版  ·  本地离线")

        # 右侧：版本胶囊 + 关于
        right = w - int(22 * ui)
        about_font = tkfont.Font(family=self._font_family, size=9)
        about_w = int(20 + 8 * ui) + about_font.measure("关于") + int(28 * ui)
        about_h = max(int(30 * ui),
                      about_font.metrics("linespace") + int(10 * ui))
        ay1 = (h - about_h) / 2
        ax1 = right - about_w
        self.create_polygon(
            _round_points(ax1, ay1, right, ay1 + about_h, about_h / 2),
            fill="", outline="#47425F", width=1, tags="about_bg")
        if self._about_icon:
            self.create_image(ax1 + int(13 * ui), h / 2,
                              image=self._about_icon, anchor="w",
                              tags="about_bg")
        self.create_text(ax1 + about_w - int(13 * ui), h / 2, text="关于",
                         anchor="e", fill="#D7DDF0",
                         font=(self._font_family, 9), tags="about_bg")
        self.tag_bind("about_bg", "<Button-1>", lambda _e: self._on_about())
        self.tag_bind("about_bg", "<Enter>",
                      lambda _e: self.configure(cursor="hand2"))
        self.tag_bind("about_bg", "<Leave>",
                      lambda _e: self.configure(cursor=""))
        if w > 820 * ui:
            vtext = f"v{APP_VERSION} · 本地离线"
            vfont = tkfont.Font(family=self._font_family, size=8)
            vw = vfont.measure(vtext) + int(42 * ui)
            vh = max(int(28 * ui),
                     vfont.metrics("linespace") + int(8 * ui))
            vx2 = ax1 - int(10 * ui)
            vx1 = vx2 - vw
            vy1 = (h - vh) / 2
            self.create_polygon(
                _round_points(vx1, vy1, vx2, vy1 + vh, vh / 2),
                fill="#201B3C", outline="#352E5B", width=1)
            self.create_oval(vx1 + int(12 * ui), h / 2 - int(2.5 * ui),
                             vx1 + int(17 * ui), h / 2 + int(2.5 * ui),
                             fill=SUCCESS, outline="")
            self.create_text(vx1 + int(23 * ui), h / 2, text=vtext,
                             anchor="w", fill="#C9BEFF",
                             font=(self._font_family, 8))
        self.create_line(0, h - 1, w, h - 1, fill="#2B2550", width=1)


# ---------------------------------------------------------------- 对话框
class ModernDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, message: str, *,
                 kind: str = "info", confirm: bool = False,
                 ok_text: str = "确定", cancel_text: str = "取消",
                 ui: float = 1.0, width: int = 500):
        super().__init__(parent)
        self.result = False
        self.ui = ui
        self.title(title)
        self.configure(bg=BORDER)
        self.resizable(False, False)
        self.transient(parent)
        self.overrideredirect(True)
        colors = {"info": ACCENT_2, "success": SUCCESS,
                  "warning": WARN, "error": ERROR}
        symbols = {"info": "i", "success": "✓", "warning": "!", "error": "×"}
        accent = colors.get(kind, ACCENT_2)
        sym = symbols.get(kind, "i")

        shell = tk.Frame(self, bg=SURFACE, bd=0,
                         highlightthickness=1, highlightbackground=BORDER)
        shell.pack(fill="both", expand=True)
        tk.Frame(shell, bg=accent, height=max(2, int(2 * ui))).pack(fill="x")

        title_font = tkfont.Font(family="Microsoft YaHei UI", size=10,
                                 weight="bold")
        bar_h = max(int(36 * ui),
                    title_font.metrics("linespace") + int(16 * ui))
        bar = tk.Frame(shell, bg=SURFACE_2, height=bar_h)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar_icon = photo("assets/app_icon_20.png")
        if bar_icon:
            tk.Label(bar, image=bar_icon, bg=SURFACE_2).pack(
                side="left", padx=(int(12 * ui), int(8 * ui)))
        drag_label = tk.Label(bar, text=title, bg=SURFACE_2, fg=TEXT,
                              font=title_font, anchor="w")
        drag_label.pack(side="left")
        close = tk.Label(bar, text="✕", bg=SURFACE_2, fg=MUTED,
                         font=("Microsoft YaHei UI", 10),
                         padx=int(10 * ui), cursor="hand2")
        close.pack(side="right", fill="y")
        close.bind("<Button-1>", lambda _e: self._cancel())
        close.bind("<Enter>", lambda _e: close.configure(
            fg=ERROR, bg=SURFACE_3))
        close.bind("<Leave>", lambda _e: close.configure(
            fg=MUTED, bg=SURFACE_2))
        self._drag_offset = (0, 0)
        for widget in (bar, drag_label):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        body = tk.Frame(shell, bg=SURFACE)
        body.pack(fill="both", expand=True, padx=int(24 * ui),
                  pady=int(22 * ui))
        head = tk.Frame(body, bg=SURFACE)
        head.pack(fill="x")
        sym_font = tkfont.Font(family="Microsoft YaHei UI", size=15,
                               weight="bold")
        icon_px = max(int(40 * ui), sym_font.metrics("linespace")
                      + int(14 * ui))
        icon = tk.Canvas(head, width=icon_px, height=icon_px,
                         bg=SURFACE, highlightthickness=0, bd=0)
        icon.pack(side="left", anchor="n")
        icon.create_oval(1, 1, icon_px - 1, icon_px - 1,
                         fill=_blend(SURFACE, accent, 0.16),
                         outline=_blend(SURFACE, accent, 0.34), width=1)
        icon.create_text(icon_px / 2, icon_px / 2, text=sym, fill=accent,
                         font=sym_font)
        text_col = tk.Frame(head, bg=SURFACE)
        text_col.pack(side="left", fill="both", expand=True,
                      padx=(int(12 * ui), 0))
        tk.Label(text_col, text=message, bg=SURFACE, fg=TEXT_2,
                 font=("Microsoft YaHei UI", 9), justify="left",
                 anchor="w", wraplength=int(width * 0.74 * ui)).pack(fill="x")

        row = tk.Frame(body, bg=SURFACE)
        row.pack(fill="x", pady=(int(18 * ui), 0))
        ok_btn = CanvasButton(row, ok_text, self._ok, variant="primary",
                              ui=ui, height=int(34 * ui), width=int(108 * ui),
                              bg=SURFACE)
        ok_btn.pack(side="right")
        if confirm:
            CanvasButton(row, cancel_text, self._cancel,
                         variant="secondary", ui=ui, height=int(34 * ui),
                         width=int(96 * ui), bg=SURFACE).pack(
                side="right", padx=(0, int(8 * ui)))
        self._ok_btn = ok_btn
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._ok())
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = parent.winfo_rootx() + max(0, (pw - w) // 2)
        y = parent.winfo_rooty() + max(0, (ph - h) // 2)
        self.geometry(f"+{x}+{y}")
        self.after(60, self._activate)

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_offset = (event.x_root - self.winfo_x(),
                             event.y_root - self.winfo_y())

    def _drag_move(self, event: tk.Event) -> None:
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _activate(self) -> None:
        try:
            self.deiconify()
            self.attributes("-topmost", True)
            self.lift()
            self.update_idletasks()
            self.grab_set()
            self.focus_force()
            self._ok_btn.focus_set()
        except tk.TclError:
            pass

    def _ok(self) -> None:
        self.result = True
        self.destroy()

    def _cancel(self) -> None:
        self.result = False
        self.destroy()

    def show(self) -> bool:
        self.wait_window(self)
        return self.result


# ---------------------------------------------------------------- 主程序
class ConverterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.busy = False
        self.queue: queue.Queue = queue.Queue()
        self.last_outdir: Optional[str] = None
        self._roots: list[LayerInfo] = []

        dpi = root.winfo_fpixels("1i") / 96.0
        self.ui = min(max(dpi, 1.0), 1.20)
        self.family = _pick_font(root, ("Microsoft YaHei UI", "Microsoft YaHei",
                                       "Segoe UI", "TkDefaultFont"))
        self.mono = _pick_font(root, ("Cascadia Mono", "Consolas",
                                     "Courier New", "TkFixedFont"))

        self.input_var = tk.StringVar()
        self.outdir_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.fmt_var = tk.StringVar(value="psd")
        self.bg_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)
        self.open_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="就绪")
        self.info_var = tk.StringVar(
            value="选择 .hsj 草稿后，这里会显示画布尺寸与图层信息")
        self.target_var = tk.StringVar(value="选择草稿并填写输出目录后显示。")
        self.preview_kind_var = tk.StringVar(value="")

        self._setup_style()
        self._build_ui()
        self._bind_events()
        self._set_icons()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, lambda: _dark_titlebar(self.root))
        self.root.after(100, self._poll_queue)
        self._set_status("就绪", "idle")
        self._append_log("就绪。选择 .hsj 文件后即可查看图层并转换。", "info")

    # ---------------------------------------------------------------- 样式
    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                     "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(family=self.family, size=10)
            except tk.TclError:
                pass
        try:
            tkfont.nametofont("TkHeadingFont").configure(weight="bold")
        except tk.TclError:
            pass

        row_font = tkfont.Font(family=self.family, size=9)
        rowheight = row_font.metrics("linespace") + int(12 * self.ui)
        style.configure(
            "Treeview", background=SURFACE, fieldbackground=SURFACE,
            foreground=TEXT, borderwidth=0, relief="flat",
            rowheight=rowheight, font=(self.family, 9))
        style.map(
            "Treeview",
            background=[("selected", "#303C60")],
            foreground=[("selected", "#FFFFFF")])
        style.configure(
            "Treeview.Heading", background=SURFACE_2, foreground=MUTED,
            borderwidth=0, relief="flat", padding=(int(6 * self.ui),
                                                   int(6 * self.ui)),
            font=(self.family, 8, "bold"))
        style.map(
            "Treeview.Heading",
            background=[("active", SURFACE_3)],
            foreground=[("active", TEXT)])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        for orient in ("Vertical", "Horizontal"):
            style.configure(
                f"{orient}.TScrollbar", background="#2C3448",
                troughcolor=SURFACE, bordercolor=SURFACE, arrowcolor=MUTED,
                relief="flat", borderwidth=0,
                width=max(9, int(10 * self.ui)))
            style.map(
                f"{orient}.TScrollbar",
                background=[("active", "#3E4A6A")],
                arrowcolor=[("active", TEXT)])

    def _apply_geometry(self) -> None:
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        ui = self.ui
        width = min(int(1160 * ui), int(sw * 0.94))
        height = min(int(900 * ui), int(sh * 0.92))
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2 - int(10 * ui))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(int(980 * ui), sw - 80),
                          min(int(720 * ui), sh - 100))

    def _set_icons(self) -> None:
        try:
            ico = photo("assets/app_icon_128.png")
            if ico:
                self.root.iconphoto(True, ico)
            if sys.platform == "win32":
                self.root.iconbitmap(resource_path("assets", "app_icon.ico"))
        except Exception:
            pass

    # ---------------------------------------------------------------- 布局
    def _build_ui(self) -> None:
        ui = self.ui
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self._apply_geometry()

        self.header = HeaderBanner(self.root, ui, self._show_about,
                                   self.family)
        self.header.pack(fill="x")

        content = tk.Frame(self.root, bg=BG)
        content.pack(fill="both", expand=True,
                     padx=int(20 * ui), pady=(int(14 * ui), int(10 * ui)))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        self.content = content

        self._build_file_card(content)
        self._build_middle(content)
        self._build_log_card(content)
        self._build_status(content)
        self._fit_window()

    def _fit_window(self) -> None:
        """按控件实际需求确定窗口大小，避免高 DPI 下内容被裁切。"""
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        ui = self.ui
        w = min(max(int(1120 * ui), self.root.winfo_reqwidth() + int(8 * ui)),
                int(sw * 0.96))
        h = min(max(int(820 * ui), self.root.winfo_reqheight() + int(8 * ui)),
                int(sh * 0.94))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - int(8 * ui))
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min(self.root.winfo_reqwidth(), sw - 60),
                          min(self.root.winfo_reqheight(), sh - 90))

    def _build_file_card(self, parent: tk.Frame) -> None:
        ui = self.ui
        card = Card(parent, "草稿文件",
                    "画世界Pro 3.4.6 导出的 .hsj · 转换全程在本机完成",
                    ui)
        card.grid(row=0, column=0, sticky="ew")
        CanvasButton(card.header_right, "打开输出目录", self._open_outdir,
                     variant="ghost", icon="folder", ui=ui,
                     height=int(30 * ui), bg=SURFACE,
                     width=int(128 * ui)).pack(side="right")

        body = card.body
        body.columnconfigure(0, weight=1)
        LabeledEntry(
            body, "输入草稿", self.input_var, ui=ui,
            browse_command=self._browse_input, label_hint=".hsj",
            on_return=self._load_layers,
        ).grid(row=0, column=0, sticky="ew", pady=(0, int(10 * ui)))

        row = tk.Frame(body, bg=SURFACE)
        row.grid(row=1, column=0, sticky="ew")
        row.columnconfigure(0, weight=3)
        row.columnconfigure(1, weight=2)
        LabeledEntry(
            row, "输出目录", self.outdir_var, ui=ui,
            browse_command=self._browse_outdir,
        ).grid(row=0, column=0, sticky="ew", padx=(0, int(12 * ui)))
        LabeledEntry(
            row, "文件名", self.name_var, ui=ui,
            suffix=".psd / .ora", label_hint="不含扩展名",
            on_return=self._start_convert,
        ).grid(row=0, column=1, sticky="ew")

    def _build_middle(self, parent: tk.Frame) -> None:
        ui = self.ui
        middle = tk.Frame(parent, bg=BG)
        middle.grid(row=1, column=0, sticky="nsew", pady=(int(12 * ui), 0))
        middle.rowconfigure(0, weight=1)
        middle.columnconfigure(0, weight=0, minsize=int(430 * ui))
        middle.columnconfigure(1, weight=1)
        self.middle = middle

        self._build_settings_card(middle)
        self._build_layers_card(middle)

    def _build_settings_card(self, parent: tk.Frame) -> None:
        ui = self.ui
        card = Card(parent, "转换设置", "输出格式与合成选项", ui)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, int(12 * ui)))
        body = card.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(5, weight=1)
        self.settings_card = card

        tk.Label(body, text="输出格式", bg=SURFACE, fg=MUTED,
                 font=("Microsoft YaHei UI", 8), anchor="w").grid(
            row=0, column=0, sticky="w", pady=(0, int(5 * ui)))
        self.format_seg = SegmentedControl(
            body, [("psd", "PSD"), ("ora", "ORA"), ("both", "两者")],
            self.fmt_var, command=self._update_targets, ui=ui, bg=SURFACE)
        self.format_seg.grid(row=1, column=0, sticky="ew")
        tk.Label(
            body, text="PSD 兼容 Photoshop / Krita · ORA 兼容 Krita / GIMP",
            bg=SURFACE, fg=HINT, font=("Microsoft YaHei UI", 8),
            anchor="w", justify="left", wraplength=int(340 * ui)).grid(
            row=2, column=0, sticky="w", pady=(int(6 * ui), 0))

        tk.Frame(body, bg=BORDER_SOFT, height=1).grid(
            row=3, column=0, sticky="ew", pady=int(10 * ui))

        toggles = tk.Frame(body, bg=SURFACE)
        toggles.grid(row=4, column=0, sticky="ew")
        ToggleSwitch(
            toggles, "包含背景色图层", "按画布底色生成最底层背景",
            self.bg_var, command=self._on_bg_toggle, ui=ui).pack(fill="x")
        ToggleSwitch(
            toggles, "覆盖已存在文件", "输出文件已存在时不再询问",
            self.force_var, ui=ui).pack(fill="x")
        ToggleSwitch(
            toggles, "完成后打开输出目录", "转换结束后自动打开文件夹",
            self.open_var, ui=ui).pack(fill="x")

        preview = tk.Frame(body, bg=FIELD, bd=0,
                           highlightthickness=1,
                           highlightbackground=BORDER_SOFT)
        preview.grid(row=6, column=0, sticky="ew", pady=(int(10 * ui), 0))
        phead = tk.Frame(preview, bg=FIELD)
        phead.pack(fill="x", padx=int(10 * ui), pady=(int(7 * ui), 0))
        tk.Label(phead, text="输出预览", bg=FIELD, fg=HINT,
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(side="left")
        tk.Label(phead, textvariable=self.preview_kind_var, bg=FIELD,
                 fg=ACCENT_2, font=("Microsoft YaHei UI", 8, "bold"),
                 anchor="e").pack(side="right")
        self.target_label = tk.Entry(
            preview, textvariable=self.target_var, state="readonly",
            readonlybackground=FIELD, fg=TEXT_2, relief="flat", bd=0,
            font=(self.mono, 8), highlightthickness=0,
            selectbackground="#33406A", selectforeground="#FFFFFF")
        self.target_label.pack(fill="x", padx=int(10 * ui),
                               pady=(int(1 * ui), int(8 * ui)))

        actions = tk.Frame(body, bg=SURFACE)
        actions.grid(row=7, column=0, sticky="ew", pady=(int(12 * ui), 0))
        self.preview_btn = CanvasButton(
            actions, "查看图层", self._load_layers, variant="secondary",
            icon="layers", ui=ui, height=int(38 * ui), width=int(130 * ui),
            bg=SURFACE)
        self.preview_btn.pack(side="left")
        self.convert_btn = CanvasButton(
            actions, "开始转换", self._start_convert, variant="primary",
            icon="convert", ui=ui, height=int(38 * ui),
            width=int(198 * ui), shortcut="F5", bg=SURFACE)
        self.convert_btn.pack(side="right")

    def _build_layers_card(self, parent: tk.Frame) -> None:
        ui = self.ui
        card = Card(parent, "图层结构", "自上而下显示，与画世界Pro 图层面板一致", ui)
        card.grid(row=0, column=1, sticky="nsew")
        self.layers_card = card
        self.count_pill = Pill(card.header_right, "0 层", bg=SURFACE,
                               font=("Microsoft YaHei UI", 8),
                               height=int(22 * ui))
        self.count_pill.pack(side="right")

        body = card.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        info = tk.Frame(body, bg=SURFACE)
        info.grid(row=0, column=0, sticky="ew", pady=(0, int(8 * ui)))
        info_icon = photo("assets/icons/info_muted_20.png")
        if info_icon:
            tk.Label(info, image=info_icon, bg=SURFACE).pack(side="left")
        tk.Label(info, textvariable=self.info_var, bg=SURFACE, fg=MUTED,
                 font=("Microsoft YaHei UI", 8), anchor="w",
                 justify="left", wraplength=int(620 * ui)).pack(
            side="left", padx=(int(6 * ui), 0))

        holder = tk.Frame(body, bg=SURFACE, bd=0,
                          highlightthickness=1,
                          highlightbackground=BORDER_SOFT)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.tree_holder = holder

        columns = ("type", "visible", "opacity", "blend", "clip")
        self.tree = ttk.Treeview(holder, columns=columns, height=7,
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="名称")
        self.tree.heading("type", text="类型")
        self.tree.heading("visible", text="可见")
        self.tree.heading("opacity", text="不透明度")
        self.tree.heading("blend", text="混合模式")
        self.tree.heading("clip", text="剪贴")
        for col in ("type", "visible", "opacity", "blend", "clip"):
            self.tree.heading(col, anchor="center")
        self.tree.column("#0", width=int(250 * ui), minwidth=int(150 * ui),
                         stretch=True)
        self.tree.column("type", width=int(88 * ui), minwidth=int(70 * ui),
                         anchor="center", stretch=False)
        self.tree.column("visible", width=int(60 * ui), minwidth=int(52 * ui),
                         anchor="center", stretch=False)
        self.tree.column("opacity", width=int(100 * ui), minwidth=int(84 * ui),
                         anchor="center", stretch=False)
        self.tree.column("blend", width=int(112 * ui), minwidth=int(96 * ui),
                         anchor="center", stretch=False)
        self.tree.column("clip", width=int(98 * ui), minwidth=int(78 * ui),
                         anchor="center", stretch=False)
        self.tree.tag_configure("odd", background="#161A26")
        self.tree.tag_configure("even", background=SURFACE)
        self.tree.tag_configure("hidden", foreground="#6F7990")
        self.tree.tag_configure("group", foreground="#C3B6FF")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(holder, orient="vertical",
                               command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(holder, orient="horizontal",
                                command=self.tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll.set,
                            xscrollcommand=hscroll.set)

        self._img_group = photo(
            f"assets/icons/folder_accent_{24 if ui > 1.12 else 20}.png")
        self._img_layer = photo(
            f"assets/icons/layers_light_{24 if ui > 1.12 else 20}.png")

        self.empty_label = tk.Label(
            holder, bg=SURFACE, fg=HINT,
            font=("Microsoft YaHei UI", 9), justify="center",
            text="尚未载入草稿\n点击「浏览」选择 .hsj 文件")
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _build_log_card(self, parent: tk.Frame) -> None:
        ui = self.ui
        card = Card(parent, "运行日志", "转换进度与结果", ui)
        card.grid(row=2, column=0, sticky="ew", pady=(int(12 * ui), 0))
        self.log_card = card
        CanvasButton(card.header_right, "清空", self._clear_log,
                     variant="ghost", icon="clear", ui=ui,
                     height=int(28 * ui), width=int(70 * ui),
                     bg=SURFACE).pack(side="right")
        CanvasButton(card.header_right, "复制", self._copy_log,
                     variant="ghost", icon="copy", ui=ui,
                     height=int(28 * ui), width=int(70 * ui),
                     bg=SURFACE).pack(side="right", padx=(0, int(4 * ui)))

        body = card.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        wrap = tk.Frame(body, bg=FIELD, bd=0, highlightthickness=1,
                        highlightbackground=BORDER_SOFT)
        wrap.grid(row=0, column=0, sticky="ew")
        wrap.columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            wrap, height=4, wrap="word", state="disabled",
            bg=FIELD, fg=TEXT_2, relief="flat", bd=0,
            font=(self.family, 9), padx=int(12 * ui), pady=int(8 * ui),
            insertbackground=ACCENT_2, selectbackground="#33406A",
            selectforeground="#FFFFFF", highlightthickness=0)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(wrap, orient="vertical",
                               command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.tag_configure(
            "time", foreground="#6F7990", font=(self.mono, 8))
        self.log_text.tag_configure("info", foreground=TEXT_2)
        self.log_text.tag_configure("ok", foreground="#8FEBD0")
        self.log_text.tag_configure("warn", foreground=WARN)
        self.log_text.tag_configure("error", foreground="#FF9BA5")

    def _build_status(self, parent: tk.Frame) -> None:
        ui = self.ui
        status = tk.Frame(parent, bg=BG)
        status.grid(row=3, column=0, sticky="ew", pady=(int(8 * ui), 0))
        status.columnconfigure(1, weight=1)
        self.status_dot = tk.Canvas(status, width=int(14 * ui),
                                    height=int(14 * ui), bg=BG,
                                    highlightthickness=0, bd=0)
        self.status_dot.grid(row=0, column=0, sticky="w")
        self._dot_id = self.status_dot.create_oval(
            int(4 * ui), int(4 * ui), int(10 * ui), int(10 * ui),
            fill=MUTED, outline="")
        tk.Label(status, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 8), anchor="w").grid(
            row=0, column=1, sticky="w", padx=(int(2 * ui), 0))
        self.progress = PulseBar(status, ui=ui, width=int(180 * ui), bg=BG)
        self.progress.grid(row=0, column=2, sticky="e", padx=(0, int(14 * ui)))
        tk.Label(status, text=f"v{APP_VERSION}", bg=BG, fg="#596178",
                 font=("Microsoft YaHei UI", 8), anchor="e").grid(
            row=0, column=3, sticky="e")

    # ---------------------------------------------------------------- 事件
    def _bind_events(self) -> None:
        for var in (self.input_var, self.outdir_var, self.name_var,
                    self.fmt_var):
            var.trace_add("write", lambda *_: self._update_targets())
        self.root.bind("<Control-o>", lambda _e: self._browse_input())
        self.root.bind("<F5>", lambda _e: self._start_convert())
        self.root.bind("<Control-Return>", lambda _e: self._start_convert())
        self.root.bind("<Control-Shift-O>", lambda _e: self._open_outdir())
        self._update_targets()

    # ---------------------------------------------------------------- 通用
    def _set_status(self, text: str, kind: str = "idle") -> None:
        self.status_var.set(text)
        colors = {"idle": MUTED, "busy": ACCENT_2, "success": SUCCESS,
                  "error": ERROR, "warning": WARN}
        try:
            self.status_dot.itemconfigure(self._dot_id,
                                          fill=colors.get(kind, MUTED))
        except Exception:
            pass

    def _dialog(self, title: str, message: str, *, kind: str = "info",
                confirm: bool = False, ok_text: str = "确定") -> bool:
        return ModernDialog(
            self.root, title, message, kind=kind, confirm=confirm,
            ok_text=ok_text, ui=self.ui).show()

    def _info(self, title: str, message: str, kind: str = "info") -> None:
        self._dialog(title, message, kind=kind)

    def _error(self, title: str, message: str) -> None:
        self._dialog(title, message, kind="error")

    def _confirm(self, title: str, message: str) -> bool:
        return self._dialog(title, message, kind="warning", confirm=True,
                            ok_text="继续")

    def _append_log(self, message: str, level: str = "auto") -> None:
        if level == "auto":
            if any(k in message for k in
                   ("失败", "错误", "Traceback", "Error", "Exception")):
                level = "error"
            elif any(k in message for k in ("警告", "警告:")):
                level = "warn"
            elif any(k in message for k in ("完成", "已读取", "已生成")):
                level = "ok"
            else:
                level = "info"
        if not hasattr(self, "log_text"):
            return
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{stamp}  ", "time")
        self.log_text.insert("end", message + "\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _copy_log(self) -> None:
        text = self.log_text.get("1.0", "end-1c").strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._append_log("日志已复制到剪贴板。", "ok")
        self._set_status("日志已复制", "success")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._append_log("日志已清空。", "info")

    # ---------------------------------------------------------------- 文件
    def _browse_input(self) -> None:
        start = os.path.dirname(self.input_var.get().strip()) or os.getcwd()
        path = filedialog.askopenfilename(
            title="选择画世界Pro导出的 .hsj 草稿",
            initialdir=start,
            filetypes=[("画世界Pro 草稿", "*.hsj"), ("所有文件", "*.*")],
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        path = os.path.abspath(path)
        self.input_var.set(path)
        folder = os.path.dirname(path)
        stem = os.path.splitext(os.path.basename(path))[0]
        self.outdir_var.set(folder)
        self.name_var.set(stem)
        self.last_outdir = folder
        self._clear_layers()
        self._update_targets()
        self._load_layers()

    def _browse_outdir(self) -> None:
        start = (self.outdir_var.get().strip()
                 or os.path.dirname(self.input_var.get().strip())
                 or os.getcwd())
        folder = filedialog.askdirectory(title="选择输出目录", initialdir=start)
        if folder:
            self.outdir_var.set(folder)
            self.last_outdir = folder
            self._update_targets()

    def _open_outdir(self) -> None:
        folder = self.outdir_var.get().strip() or self.last_outdir
        if folder and os.path.isdir(folder):
            _open_folder(folder)
        else:
            self._info("打开输出目录", "输出目录尚不存在，请先选择一个目录。",
                       kind="info")

    def _clear_layers(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._roots = []
        if hasattr(self, "empty_label"):
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")
        if hasattr(self, "count_pill"):
            self.count_pill.set("0 层")

    def _update_targets(self) -> None:
        path = self.input_var.get().strip()
        outdir = self.outdir_var.get().strip()
        name = _sanitize_filename(self.name_var.get()) or (
            os.path.splitext(os.path.basename(path))[0] if path else "")
        fmt = self.fmt_var.get()
        self.preview_kind_var.set(
            {"psd": "PSD", "ora": "ORA", "both": "PSD + ORA"}.get(fmt, ""))
        if not outdir or not name:
            self.target_var.set("选择草稿并填写输出目录后显示。")
            return
        base = os.path.join(outdir, name)
        if fmt == "both":
            text = f"{base}.psd   +   {base}.ora"
        else:
            text = f"{base}.{fmt}"
        if not self.bg_var.get():
            text += "   （不含背景色图层）"
        self.target_var.set(text)

    # ---------------------------------------------------------------- 图层
    def _load_layers(self) -> None:
        path = self.input_var.get().strip()
        if not path:
            self._info("提示", "请先选择一个 .hsj 文件。", kind="info")
            return
        if not os.path.isfile(path):
            self._error("文件不存在", f"找不到文件：\n{path}")
            return
        if self.busy:
            return

        self._clear_layers()
        self._set_status("正在读取图层信息…", "busy")
        self.preview_btn.set_enabled(False)
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            data = load_draft(
                path, with_bg=self.bg_var.get(), load_pixels=False,
                log=self._append_log,
            )
            self._roots = data["roots"]
            draw = data["draw"]
            leaves = self._count_leaves(self._roots)
            self.info_var.set(
                f"画布 {data['width']} × {data['height']} px  ·  {draw.ppi} PPI  ·  "
                f"{leaves} 个图层"
                + (f"  ·  {draw.color_space}" if draw.color_space else ""))
            if data["bg_rgba"]:
                r, g, b, a = data["bg_rgba"]
                self.info_var.set(
                    self.info_var.get() + f"  ·  背景 rgba({r},{g},{b},{a})")
            elif not self.bg_var.get():
                self.info_var.set(self.info_var.get() + "  ·  不含背景图层")
            elif draw.bg_hidden:
                self.info_var.set(self.info_var.get() + "  ·  背景隐藏")
            else:
                self.info_var.set(self.info_var.get() + "  ·  背景透明")
            for layer in reversed(self._roots):
                self._insert_layer("", layer)
            self.empty_label.place_forget()
            self.count_pill.set(f"{leaves} 层")
            self._append_log(
                f"已读取 {os.path.basename(path)}：{leaves} 个图层，"
                f"画布 {data['width']}×{data['height']}", "ok")
            self._set_status("图层信息已加载", "success")
        except Exception as exc:
            self._append_log(f"读取失败：{exc}", "error")
            if not isinstance(exc, (HsjError, OSError, ValueError)):
                self._append_log(traceback.format_exc(), "error")
            self._error("读取失败", str(exc))
            self._set_status("读取失败", "error")
        finally:
            self.preview_btn.set_enabled(True)
            self.root.configure(cursor="")
            self._update_targets()

    def _count_leaves(self, items: list[LayerInfo]) -> int:
        return sum(
            1 if not item.is_group else self._count_leaves(item.children)
            for item in items
        )

    def _insert_layer(self, parent: str, layer: LayerInfo,
                      depth: int = 0) -> None:
        if layer.clip_type == CLIP_BOTTOM and layer.clip_group:
            clip = f"基础组{layer.clip_group}"
        elif layer.clip_type in (CLIP_TOP, CLIP_MIDDLE) and layer.clip_group:
            clip = f"剪贴组{layer.clip_group}"
        else:
            clip = ""
        kind = "组" if layer.is_group else "图层"
        if layer.is_lock_alpha:
            kind += " · 锁"
        values = (
            kind,
            "是" if layer.visible else "否",
            f"{layer.opacity * 100:.0f}%",
            layer.blend_name,
            clip,
        )
        tags = ["odd" if depth % 2 else "even"]
        if not layer.visible:
            tags.append("hidden")
        if layer.is_group:
            tags.append("group")
        image = self._img_group if layer.is_group else self._img_layer
        item = self.tree.insert(
            parent, "end", text=layer.name or "未命名",
            values=values, open=layer.is_group, tags=tuple(tags),
            image=image or "",
        )
        for child in reversed(layer.children):
            self._insert_layer(item, child, depth + 1)

    def _on_bg_toggle(self) -> None:
        self._update_targets()
        if self.input_var.get().strip() and not self.busy:
            self._load_layers()

    # ---------------------------------------------------------------- 转换
    def _start_convert(self) -> None:
        if self.busy:
            return
        path = self.input_var.get().strip()
        if not path or not os.path.isfile(path):
            self._info("提示", "请先选择有效的 .hsj 文件。", kind="warning")
            return
        outdir = self.outdir_var.get().strip()
        if not outdir:
            self._info("提示", "请选择输出目录。", kind="warning")
            return
        name = _sanitize_filename(self.name_var.get())
        if not name:
            name = os.path.splitext(os.path.basename(path))[0]
            self.name_var.set(name)
        fmt = self.fmt_var.get()
        base = os.path.join(outdir, name)
        targets = (
            [base + ".psd", base + ".ora"] if fmt == "both"
            else [base + "." + fmt]
        )
        if not self.force_var.get():
            existing = [t for t in targets if os.path.exists(t)]
            if existing and not self._confirm(
                    "文件已存在",
                    "以下文件已存在，是否覆盖？\n\n" + "\n".join(existing)):
                return

        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as exc:
            self._error("错误", f"无法创建输出目录：\n{exc}")
            return

        self.busy = True
        self.preview_btn.set_enabled(False)
        self.convert_btn.set_enabled(False)
        self.convert_btn.set_text("正在转换…")
        self.progress.start()
        self._set_status("正在转换…", "busy")
        self._append_log("─" * 52, "info")
        self._append_log(
            f"开始转换：{os.path.basename(path)} → "
            f"{FORMAT_LABELS.get(fmt, fmt)}", "info")

        q = self.queue

        def worker() -> None:
            try:
                # convert() 对 psd/ora 使用完整文件路径，both 模式使用前缀
                target = base if fmt == "both" else base + "." + fmt
                outputs = convert(
                    path, target, fmt,
                    with_bg=self.bg_var.get(),
                    force=True,
                    log=lambda msg: q.put(("log", msg)),
                )
                q.put(("done", outputs))
            except Exception as exc:
                q.put(("error", str(exc) or type(exc).__name__,
                       traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._append_log(msg[1])
                elif kind == "done":
                    self._on_done(msg[1])
                elif kind == "error":
                    self._on_error(msg[1], msg[2])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _finish_busy(self) -> None:
        self.busy = False
        self.progress.stop()
        self.preview_btn.set_enabled(True)
        self.convert_btn.set_enabled(True)
        self.convert_btn.set_text("开始转换")

    def _on_done(self, outputs: list[str]) -> None:
        self._finish_busy()
        self._set_status("转换完成", "success")
        self._append_log("转换完成：", "ok")
        for out in outputs:
            self._append_log(f"  {out}", "ok")
        self.last_outdir = self.outdir_var.get().strip()
        if self.open_var.get() and self.last_outdir:
            _open_folder(self.last_outdir)
        self._dialog(
            "转换完成",
            "已生成以下文件：\n\n" + "\n".join(outputs) +
            "\n\n可直接用 Photoshop / Krita / GIMP 打开。",
            kind="success", ok_text="好的")

    def _on_error(self, message: str, tb: str) -> None:
        self._finish_busy()
        self._set_status("转换失败", "error")
        self._append_log(f"转换失败：{message}", "error")
        if tb:
            self._append_log(tb, "error")
        self._error("转换失败", message)

    # ---------------------------------------------------------------- 窗口
    def _show_about(self) -> None:
        self._dialog(
            "关于",
            f"{APP_TITLE}  v{APP_VERSION}\n\n"
            "把画世界Pro 的 .hsj 多图层草稿转换为 PSD / ORA，保留图层像素、"
            "名称、顺序、可见性、不透明度、混合模式与剪贴蒙版。\n\n"
            "转换在本机离线完成，不会上传任何草稿内容。\n\n"
            "快捷键\n"
            "Ctrl+O  选择草稿      F5 / Ctrl+Enter  开始转换\n"
            "Ctrl+Shift+O  打开输出目录\n\n"
            "技术说明\n"
            "PSD 中的图层组会扁平化；ORA 中的剪贴蒙版会烘焙进 alpha。",
            kind="info", ok_text="关闭")

    def _on_close(self) -> None:
        if self.busy:
            if not self._confirm("正在转换", "转换正在进行，确定要退出吗？"):
                return
        self.root.destroy()


def main() -> int:
    _enable_dpi_awareness()
    root = tk.Tk()
    app = ConverterApp(root)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.isfile(args[0]):
        start = os.path.abspath(args[0])
        root.after(180, lambda: app.open_path(start))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
