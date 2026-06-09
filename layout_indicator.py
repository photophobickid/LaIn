"""
Индикатор раскладки клавиатуры у курсора мыши.

Маленький полупрозрачный индикатор следует за курсором: нейтральная точка,
цветное кольцо и ripple-волны показывают раскладку (EN/RU/...). Без букв.
Клики проходят насквозь и не мешают работе.

Выход: Ctrl+Alt+Q (или закрыть через stop.bat / Диспетчер задач).

Аргументы командной строки:
  --enable-autostart   включить автозапуск при входе в Windows и выйти
  --disable-autostart  выключить автозапуск и выйти
  --autostart-status   показать статус автозапуска и выйти
  --help               показать справку
Без аргументов — обычный запуск индикатора.
"""

import colorsys
import ctypes
from ctypes import wintypes
import os
import sys
import time
import tkinter as tk
import winreg

# --- Настройки внешнего вида ---
DOT_SIZE = 14            # диаметр центральной точки, px
CANVAS_SIZE = 28         # холст с запасом под ripple-волны
OFFSET_X = 5             # смещение виджета от курсора, px
OFFSET_Y = 5
OPACITY = 0.55           # общая прозрачность (0..1)
TRANSPARENT = "magenta"  # цвет, который станет полностью прозрачным
TICK_MS = 16             # интервал кадра при движении / ripple, мс
TICK_MS_IDLE = 48        # интервал в покое (меньше нагрузка на tk/GDI)
RIPPLE_MS = 580          # длительность одной волны, мс
RIPPLE_DELAY_MS = 290    # задержка второй волны
RIPPLE_FADE_POWER = 1.85 # >1 — быстрее затухание волны
RIPPLE_WIDTH = 1         # толщина кольца ripple, px
ACCENT_RING_WIDTH = 2    # постоянное кольцо раскладки вокруг точки, px
FOLLOW_LERP = 0.26       # плавное следование (под TICK_MS=16)
FOLLOW_SNAP = 0.55       # px — ближе этого к цели, без дрожания
LAYOUT_POLL_MS = 80      # опрос раскладки

# Адаптация к фону через GetPixel — ОТКЛЮЧЕНА (BSOD 0x133, см. GitHub issue)
ADAPTIVE_BG = False
BG_LUMA_FIXED = 200      # фикс. яркость фона для палитры (светлый рабочий стол)

# Оттенок (HSL hue 0..1) для каждой раскладки — одинаковая насыщенность/яркость
HUES = {
    "EN": 0.69,  # indigo
    "RU": 0.97,  # rose
    "DE": 0.11,  # amber
    "FR": 0.55,  # sky
    "UK": 0.75,  # violet
    "ES": 0.07,  # coral
}
DEFAULT_HUE = 0.48  # teal

LUMA_THRESHOLD = 128     # граница «тёмный / светлый» (для палитры)

DOT_R = DOT_SIZE // 2
CENTER = CANVAS_SIZE // 2
RIPPLE_MAX_R = CENTER - 1


def ripple_state(progress):
    """Фаза ripple по keyframes ld-ripple (uiverse.io/Codecite/witty-falcon-85)."""
    if progress < 0.05:
        return 0.0, progress / 0.05
    size_p = (progress - 0.05) / 0.95
    opacity = (1.0 - size_p) ** RIPPLE_FADE_POWER
    return size_p, opacity


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _to_hex(r, g, b):
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def neutral_color(bg_luma):
    """Монохромная точка: светлая на тёмном фоне, тёмная на светлом."""
    if bg_luma < LUMA_THRESHOLD:
        lightness, saturation = 0.93, 0.015
    else:
        lightness, saturation = 0.26, 0.015
    r, g, b = colorsys.hls_to_rgb(0, lightness, saturation)
    return _to_hex(r, g, b)


def ring_accent_color(hue, bg_luma):
    """Контрастное кольцо раскладки — заметнее на типичных фонах."""
    if bg_luma < LUMA_THRESHOLD:
        lightness, saturation = 0.80, 0.72
    else:
        lightness, saturation = 0.32, 0.88
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return _to_hex(r, g, b)


def accent_color(hue, bg_luma, fade=1.0):
    """Цвет раскладки — только для ripple-волн."""
    fade = _clamp(fade)
    if bg_luma < LUMA_THRESHOLD:
        lightness, saturation = 0.72, 0.55
    else:
        lightness, saturation = 0.47, 0.58
    saturation *= fade * 0.75 + 0.25
    if bg_luma < LUMA_THRESHOLD:
        lightness += (1.0 - fade) * 0.12
    else:
        lightness -= (1.0 - fade) * 0.10
    r, g, b = colorsys.hls_to_rgb(hue, _clamp(lightness), _clamp(saturation))
    return _to_hex(r, g, b)

# --- WinAPI ---
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# DPI-awareness, чтобы координаты курсора и окна совпадали
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

LOCALE_SISO639LANGNAME = 0x59

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002

# COLORREF (0x00bbggrr) для magenta = RGB(255, 0, 255)
COLORKEY_REF = 0x00FF00FF

VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_Q = 0x51

user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

_LAYOUT_BUF = ctypes.create_unicode_buffer(16)


def get_cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def get_active_layout_code():
    """Вернуть двухбуквенный код раскладки активного окна, напр. 'EN', 'RU'."""
    hwnd = user32.GetForegroundWindow()
    thread_id = user32.GetWindowThreadProcessId(hwnd, None)
    hkl = user32.GetKeyboardLayout(thread_id)
    langid = hkl & 0xFFFF
    buf = _LAYOUT_BUF
    n = kernel32.GetLocaleInfoW(langid, LOCALE_SISO639LANGNAME, buf, len(buf))
    if n > 0 and buf.value:
        return buf.value.upper()
    return "??"


def setup_window(hwnd):
    """Сделать окно сквозным для кликов и задать прозрачность по цветовому ключу.

    Важно: SetLayeredWindowAttributes вызывается ПОСЛЕ SetWindowLongW, иначе
    стиль сбрасывает атрибуты прозрачности и окно становится непрозрачным.
    """
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    user32.SetLayeredWindowAttributes(
        hwnd, COLORKEY_REF, int(OPACITY * 255), LWA_COLORKEY | LWA_ALPHA
    )


def key_down(vk):
    return user32.GetAsyncKeyState(vk) & 0x8000 != 0


class Indicator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=TRANSPARENT)
        self.root.geometry(f"{CANVAS_SIZE}x{CANVAS_SIZE}+0+0")

        self.canvas = tk.Canvas(
            self.root, width=CANVAS_SIZE, height=CANVAS_SIZE,
            bg=TRANSPARENT, highlightthickness=0, bd=0,
        )
        self.canvas.pack()

        self._bg_luma = BG_LUMA_FIXED
        self._hue = DEFAULT_HUE
        self._core_color = neutral_color(self._bg_luma)
        self._accent_color = ring_accent_color(self._hue, self._bg_luma)
        self._anim_start = time.monotonic()
        self._last_layout_poll = 0.0
        self._last_win_pos = (-99999, -99999)
        self._geo_prefix = f"{CANVAS_SIZE}x{CANVAS_SIZE}+"
        self._pos_x = 0.0
        self._pos_y = 0.0
        self._follow_ready = False
        self._ripples_resting = False
        self._ripple_cache = {}
        cx, cy = CENTER, CENTER
        r = DOT_R

        self.ripple1 = self.canvas.create_oval(
            cx, cy, cx, cy, fill="", outline="", width=RIPPLE_WIDTH,
        )
        self.ripple2 = self.canvas.create_oval(
            cx, cy, cx, cy, fill="", outline="", width=RIPPLE_WIDTH,
        )
        self.core = self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self._core_color, outline=self._accent_color,
            width=ACCENT_RING_WIDTH,
        )

        self.root.update_idletasks()
        try:
            setup_window(self.root.winfo_id())
        except Exception:
            pass

        self._last_code = None
        self.tick()

    def _follow_cursor(self, target_x, target_y):
        if not self._follow_ready:
            self._pos_x = float(target_x)
            self._pos_y = float(target_y)
            self._follow_ready = True

        dx = target_x - self._pos_x
        dy = target_y - self._pos_y
        if abs(dx) < FOLLOW_SNAP and abs(dy) < FOLLOW_SNAP:
            self._pos_x = float(target_x)
            self._pos_y = float(target_y)
        else:
            self._pos_x += dx * FOLLOW_LERP
            self._pos_y += dy * FOLLOW_LERP

        wx = int(round(self._pos_x))
        wy = int(round(self._pos_y))
        if (wx, wy) == self._last_win_pos:
            return
        self.root.geometry(f"{self._geo_prefix}{wx}+{wy}")
        self._last_win_pos = (wx, wy)

    def _update_appearance(self):
        core = neutral_color(self._bg_luma)
        accent = ring_accent_color(self._hue, self._bg_luma)
        if core != self._core_color:
            self._core_color = core
            self.canvas.itemconfig(self.core, fill=core)
        if accent != self._accent_color:
            self._accent_color = accent
            self.canvas.itemconfig(self.core, outline=accent)

    def _ripple_active(self, elapsed_ms):
        for delay in (0, RIPPLE_DELAY_MS):
            progress = (elapsed_ms - delay) / RIPPLE_MS
            if 0 <= progress < 1:
                _, opacity = ripple_state(progress)
                if opacity > 0.02:
                    return True
        return False

    def _draw_ripple(self, oval_id, elapsed_ms, delay_ms):
        progress = (elapsed_ms - delay_ms) / RIPPLE_MS
        if progress < 0 or progress >= 1:
            state = (CENTER, CENTER, CENTER, CENTER, "")
            if self._ripple_cache.get(oval_id) != state:
                self.canvas.coords(oval_id, CENTER, CENTER, CENTER, CENTER)
                self.canvas.itemconfig(oval_id, outline="")
                self._ripple_cache[oval_id] = state
            return

        size_p, opacity = ripple_state(progress)
        if opacity <= 0.02:
            state = (CENTER, CENTER, CENTER, CENTER, "")
            if self._ripple_cache.get(oval_id) != state:
                self.canvas.coords(oval_id, CENTER, CENTER, CENTER, CENTER)
                self.canvas.itemconfig(oval_id, outline="")
                self._ripple_cache[oval_id] = state
            return

        r = DOT_R + size_p * (RIPPLE_MAX_R - DOT_R)
        ripple_color = accent_color(self._hue, self._bg_luma, fade=round(opacity, 2))
        x1, y1 = CENTER - r, CENTER - r
        x2, y2 = CENTER + r, CENTER + r
        state = (x1, y1, x2, y2, ripple_color)
        if self._ripple_cache.get(oval_id) == state:
            return
        self.canvas.coords(oval_id, x1, y1, x2, y2)
        self.canvas.itemconfig(oval_id, outline=ripple_color, stipple="")
        self._ripple_cache[oval_id] = state

    def tick(self):
        if key_down(VK_CONTROL) and key_down(VK_MENU) and key_down(VK_Q):
            self.root.destroy()
            return

        x, y = get_cursor_pos()
        target_x, target_y = x + OFFSET_X, y + OFFSET_Y
        self._follow_cursor(target_x, target_y)

        now = time.monotonic()
        layout_changed = False
        if (now - self._last_layout_poll) * 1000 >= LAYOUT_POLL_MS:
            code = get_active_layout_code()
            self._last_layout_poll = now
            if code != self._last_code:
                self._last_code = code
                self._hue = HUES.get(code, DEFAULT_HUE)
                self._anim_start = time.monotonic()
                self._ripples_resting = False
                self._ripple_cache.clear()
                self._update_appearance()
                layout_changed = True

        elapsed_ms = (time.monotonic() - self._anim_start) * 1000
        ripple_active = self._ripple_active(elapsed_ms)
        if ripple_active:
            self._ripples_resting = False
            self._draw_ripple(self.ripple1, elapsed_ms, 0)
            self._draw_ripple(self.ripple2, elapsed_ms, RIPPLE_DELAY_MS)
        elif not self._ripples_resting:
            self._draw_ripple(self.ripple1, elapsed_ms, 0)
            self._draw_ripple(self.ripple2, elapsed_ms, RIPPLE_DELAY_MS)
            self._ripples_resting = True

        moving = (
            abs(self._pos_x - target_x) >= FOLLOW_SNAP
            or abs(self._pos_y - target_y) >= FOLLOW_SNAP
        )
        interval = TICK_MS if (moving or ripple_active or layout_changed) else TICK_MS_IDLE
        self.root.after(interval, self.tick)

    def run(self):
        self.root.mainloop()


# --- Автозапуск (реестр HKCU\...\Run) ---
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "LayoutIndicator"


def get_run_command():
    """Команда для автозапуска текущей сборки приложения."""
    if getattr(sys, "frozen", False):
        # Собрано в .exe (PyInstaller)
        return f'"{sys.executable}"'
    # Запуск из исходника: используем pythonw, чтобы не было консоли
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    script = os.path.abspath(__file__)
    return f'"{pyw}" "{script}"'


def enable_autostart():
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, get_run_command())


def disable_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, AUTOSTART_NAME)
    except FileNotFoundError:
        pass


def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0,
                            winreg.KEY_QUERY_VALUE) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
    except FileNotFoundError:
        return False


def handle_cli(args):
    """Обработать аргументы. Вернуть True, если приложение должно завершиться."""
    if "--help" in args or "-h" in args:
        print(__doc__)
        return True
    if "--enable-autostart" in args:
        enable_autostart()
        print("Автозапуск включён.")
        return True
    if "--disable-autostart" in args:
        disable_autostart()
        print("Автозапуск выключен.")
        return True
    if "--autostart-status" in args:
        print("включён" if is_autostart_enabled() else "выключен")
        return True
    return False


if __name__ == "__main__":
    if handle_cli(sys.argv[1:]):
        sys.exit(0)
    Indicator().run()
