"""
Индикатор раскладки клавиатуры у курсора мыши.

Маленький полупрозрачный кружок следует за курсором и показывает текущую
раскладку (EN/RU/...) активного окна. Кружок «сквозной» — клики проходят
насквозь и не мешают работе.

Выход: Ctrl+Alt+Q (или закрыть через stop.bat / Диспетчер задач).

Аргументы командной строки:
  --enable-autostart   включить автозапуск при входе в Windows и выйти
  --disable-autostart  выключить автозапуск и выйти
  --autostart-status   показать статус автозапуска и выйти
  --help               показать справку
Без аргументов — обычный запуск индикатора.
"""

import ctypes
from ctypes import wintypes
import os
import sys
import tkinter as tk
import winreg

# --- Настройки внешнего вида ---
SIZE = 16                # диаметр кружка, px
OFFSET_X = 14            # смещение кружка от курсора, px
OFFSET_Y = 14
OPACITY = 0.85           # общая прозрачность (0..1)
TRANSPARENT = "magenta"  # цвет, который станет полностью прозрачным
POLL_MS = 40             # период обновления, мс

# Мягкая пастельная палитра (двухбуквенный ISO-код -> цвет фона)
COLORS = {
    "EN": "#6E9BE6",  # спокойный синий
    "RU": "#E68A8A",  # мягкий коралловый
    "DE": "#E6C173",  # тёплый песочный
    "FR": "#8AA8E6",  # светло-голубой
    "UK": "#E6D27A",  # приглушённый жёлтый
    "ES": "#E6A973",  # мягкий оранжевый
}
DEFAULT_COLOR = "#86C2A1"  # мягкий зелёный для прочих раскладок

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
    buf = ctypes.create_unicode_buffer(16)
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
        self.root.geometry(f"{SIZE}x{SIZE}+0+0")

        self.canvas = tk.Canvas(
            self.root, width=SIZE, height=SIZE,
            bg=TRANSPARENT, highlightthickness=0, bd=0,
        )
        self.canvas.pack()

        pad = 1
        self.oval = self.canvas.create_oval(
            pad, pad, SIZE - pad, SIZE - pad,
            fill=DEFAULT_COLOR, outline="#FFFFFF", width=1,
        )
        self.text = self.canvas.create_text(
            SIZE / 2 + 1, SIZE / 2, text="..",
            fill="#FFFFFF", font=("Segoe UI", 6, "bold"),
        )

        # Прозрачность + сквозные клики (после того как окно создано)
        self.root.update_idletasks()
        try:
            setup_window(self.root.winfo_id())
        except Exception:
            pass

        self._last_code = None
        self.update()

    def update(self):
        # Выход по Ctrl+Alt+Q
        if key_down(VK_CONTROL) and key_down(VK_MENU) and key_down(VK_Q):
            self.root.destroy()
            return

        x, y = get_cursor_pos()
        self.root.geometry(f"{SIZE}x{SIZE}+{x + OFFSET_X}+{y + OFFSET_Y}")

        code = get_active_layout_code()
        if code != self._last_code:
            self._last_code = code
            color = COLORS.get(code, DEFAULT_COLOR)
            self.canvas.itemconfig(self.oval, fill=color)
            self.canvas.itemconfig(self.text, text=code)

        self.root.after(POLL_MS, self.update)

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
