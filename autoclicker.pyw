import ctypes
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from pynput import keyboard, mouse

# 1. Скрываем окно консоли при запуске в Windows
if sys.platform == "win32":
    hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd_console:
        ctypes.windll.user32.ShowWindow(hwnd_console, 0)  # 0 = SW_HIDE

# Константы Windows API для сквозных кликов
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
GA_ROOT = 2

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SWP_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED


class ClickMarker(tk.Toplevel):
    """Окно-маркер с возможностью индивидуальной настройки кликов и удаления."""

    def __init__(self, parent, number, app_ref):
        super().__init__(parent)
        self.number = number
        self.app_ref = app_ref
        self.clicks_count = 1  # Количество кликов по умолчанию

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.85)
        self.geometry(f"44x44+{100 + number * 45}+{100}")
        self.configure(bg="#e74c3c")

        self.label = tk.Label(
            self,
            text="",
            bg="#e74c3c",
            fg="white",
            font=("Arial", 9, "bold"),
            cursor="fleur",
        )
        self.label.pack(expand=True, fill="both")
        self.update_label()

        # Привязка событий мыши
        self.label.bind("<Button-1>", self.start_drag)
        self.label.bind("<B1-Motion>", self.do_drag)
        self.label.bind("<Button-3>", self.show_context_menu)  # Правая кнопка

    def update_label(self):
        text = (
            f"{self.number}\n[x{self.clicks_count}]"
            if self.clicks_count > 1
            else str(self.number)
        )
        self.label.config(text=text)

    def set_number(self, number):
        self.number = number
        self.update_label()

    def start_drag(self, event):
        self._x = event.x
        self._y = event.y

    def do_drag(self, event):
        x = self.winfo_x() - self._x + event.x
        y = self.winfo_y() - self._y + event.y
        self.geometry(f"+{x}+{y}")

    def get_pos(self):
        return self.winfo_x() + 22, self.winfo_y() + 22

    def show_context_menu(self, event):
        """Контекстное меню настройки маркера по правой кнопке мыши."""
        if self.app_ref.is_running:
            return

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=f"Кликов на этом маркере: {self.clicks_count} (изменить)",
            command=self.change_clicks,
        )
        menu.add_separator()
        menu.add_command(label="Удалить этот маркер", command=self.delete_self)
        menu.post(event.x_root, event.y_root)

    def change_clicks(self):
        val = simpledialog.askinteger(
            "Количество кликов",
            f"Сколько кликов сделать на маркере №{self.number}?",
            parent=self.app_ref.root,
            initialvalue=self.clicks_count,
            minvalue=1,
            maxvalue=999,
        )
        if val is not None:
            self.clicks_count = val
            self.update_label()

    def delete_self(self):
        self.app_ref.remove_marker(self)

    def set_click_through(self, enable=True):
        """Включает/выключает прохождение кликов сквозь маркер в Windows."""
        hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), GA_ROOT)
        if not hwnd:
            hwnd = self.winfo_id()

        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enable:
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            style &= ~WS_EX_TRANSPARENT

        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)


class AutoClickerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Python AutoClicker")
        self.root.geometry("400x450")
        self.root.attributes("-topmost", True)

        self.markers = []
        self.is_running = False
        self.mouse_ctrl = mouse.Controller()

        self._build_ui()
        self._start_hotkey_listener()

    def _build_ui(self):
        self.delay_var = tk.StringVar(value="0.5")
        self.auto_stop_var = tk.StringVar(value="10")
        self.use_auto_stop_var = tk.BooleanVar(value=False)

        self.use_markers_var = tk.BooleanVar(value=True)
        self.use_loop_var = tk.BooleanVar(value=True)
        self.cycles_var = tk.StringVar(value="0")

        # Параметры времени
        frame = ttk.LabelFrame(self.root, text="Параметры клика", padding=10)
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text="Пауза между кликами (сек):").grid(
            row=0, column=0, sticky="w", pady=4
        )
        ttk.Entry(frame, textvariable=self.delay_var, width=8).grid(
            row=0, column=1, pady=4
        )

        ttk.Checkbutton(
            frame,
            text="Включить автоотключение",
            variable=self.use_auto_stop_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)

        ttk.Label(frame, text="Таймер автоотключения (сек):").grid(
            row=2, column=0, sticky="w", pady=4
        )
        ttk.Entry(frame, textvariable=self.auto_stop_var, width=8).grid(
            row=2, column=1, pady=4
        )

        # Режим кликера и циклы
        mode_frame = ttk.LabelFrame(
            self.root, text="Режим кликера", padding=10
        )
        mode_frame.pack(fill="x", padx=10, pady=5)

        ttk.Checkbutton(
            mode_frame,
            text="Использовать маркеры на экране",
            variable=self.use_markers_var,
            command=self._on_toggle_markers_mode,
        ).pack(anchor="w", pady=2)

        # Опции зацикливания
        loop_box = ttk.Frame(mode_frame)
        loop_box.pack(fill="x", pady=4)

        ttk.Checkbutton(
            loop_box, text="Зациклить", variable=self.use_loop_var
        ).pack(side="left")
        ttk.Label(loop_box, text="  Циклов (0 = бесконечно):").pack(side="left")
        ttk.Entry(loop_box, textvariable=self.cycles_var, width=6).pack(
            side="left"
        )

        # Кнопки управления маркерами
        btn_box = ttk.Frame(mode_frame)
        btn_box.pack(fill="x", pady=6)

        self.btn_add = ttk.Button(
            btn_box, text="+ Добавить", command=self.add_marker
        )
        self.btn_add.pack(side="left", expand=True, padx=2)

        self.btn_remove_last = ttk.Button(
            btn_box, text="Удалить последний", command=self.remove_last_marker
        )
        self.btn_remove_last.pack(side="left", expand=True, padx=2)

        self.btn_clear = ttk.Button(
            btn_box, text="Очистить все", command=self.clear_markers
        )
        self.btn_clear.pack(side="left", expand=True, padx=2)

        # Статус и запуск
        self.status_label = ttk.Label(
            self.root,
            text="Статус: Остановлен [F6]",
            font=("Arial", 10, "bold"),
            foreground="red",
        )
        self.status_label.pack(pady=8)

        self.toggle_btn = ttk.Button(
            self.root, text="Старт / Стоп (F6)", command=self.toggle_clicking
        )
        self.toggle_btn.pack(pady=5, fill="x", padx=10)

    def _on_toggle_markers_mode(self):
        state = "normal" if self.use_markers_var.get() else "disabled"
        self.btn_add.config(state=state)
        self.btn_remove_last.config(state=state)
        self.btn_clear.config(state=state)

        for m in self.markers:
            if self.use_markers_var.get():
                m.deiconify()
            else:
                m.withdraw()

    def add_marker(self):
        if not self.use_markers_var.get():
            return
        count = len(self.markers) + 1
        marker = ClickMarker(self.root, count, self)
        self.markers.append(marker)

    def remove_marker(self, marker):
        """Удаляет конкретный маркер и пересчитывает оставшиеся."""
        if marker in self.markers:
            self.markers.remove(marker)
            marker.destroy()
            self._renumber_markers()

    def remove_last_marker(self):
        """Удаляет последний созданный маркер."""
        if self.markers:
            marker = self.markers.pop()
            marker.destroy()
            self._renumber_markers()

    def clear_markers(self):
        for m in self.markers:
            m.destroy()
        self.markers.clear()

    def _renumber_markers(self):
        """Перерасчитывает порядковые номера всех маркеров на экране."""
        for idx, m in enumerate(self.markers, start=1):
            m.set_number(idx)

    def _start_hotkey_listener(self):
        def on_press(key):
            if key == keyboard.Key.f6:
                self.root.after(0, self.toggle_clicking)

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

    def toggle_clicking(self):
        if self.is_running:
            self.stop_clicking()
        else:
            self.start_clicking()

    def start_clicking(self):
        if self.use_markers_var.get() and not self.markers:
            messagebox.showwarning(
                "Ошибка", "Добавьте хотя бы один маркер на экран!"
            )
            return

        self.is_running = True
        self.status_label.config(
            text="Статус: РАБОТАЕТ [F6]", foreground="green"
        )

        if self.use_markers_var.get():
            for m in self.markers:
                m.set_click_through(True)

        threading.Thread(target=self._run_click_loop, daemon=True).start()

    def stop_clicking(self):
        self.is_running = False
        self.root.after(0, self._ui_on_stop)

    def _ui_on_stop(self):
        self.status_label.config(
            text="Статус: Остановлен [F6]", foreground="red"
        )
        for m in self.markers:
            m.set_click_through(False)

    def _run_click_loop(self):
        try:
            delay = float(self.delay_var.get())
            auto_stop = self.use_auto_stop_var.get()
            auto_stop_sec = (
                float(self.auto_stop_var.get()) if auto_stop else None
            )

            use_loop = self.use_loop_var.get()
            max_cycles = int(self.cycles_var.get()) if use_loop else 1
        except ValueError:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Ошибка", "Введите корректные числовые значения!"
                ),
            )
            self.stop_clicking()
            return

        start_time = time.time()
        current_cycle = 0

        while self.is_running:
            # Проверка таймера автоотключения
            if auto_stop_sec and (time.time() - start_time) >= auto_stop_sec:
                self.stop_clicking()
                break

            if self.use_markers_var.get():
                # Проход по всем маркерам
                for marker in list(self.markers):
                    if not self.is_running:
                        break

                    # Выполнение запрашиваемого числа кликов для конкретного маркера
                    for _ in range(marker.clicks_count):
                        if not self.is_running:
                            break
                        x, y = marker.get_pos()
                        self.mouse_ctrl.position = (x, y)
                        self.mouse_ctrl.click(mouse.Button.left)
                        time.sleep(delay)

                current_cycle += 1

                # Проверка завершения циклов
                if not use_loop or (
                    max_cycles > 0 and current_cycle >= max_cycles
                ):
                    self.stop_clicking()
                    break
            else:
                # Режим клика по курсору
                self.mouse_ctrl.click(mouse.Button.left)
                time.sleep(delay)


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()