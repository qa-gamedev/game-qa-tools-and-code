import ctypes
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from pynput import keyboard, mouse

# Скрываем окно консоли в Windows
if sys.platform == "win32":
    hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd_console:
        ctypes.windll.user32.ShowWindow(hwnd_console, 0)

# Константы Win32 API для сквозных кликов
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
    """Окно-маркер для Режима 2."""

    def __init__(self, parent, number, app_ref, x=None, y=None):
        super().__init__(parent)
        self.number = number
        self.app_ref = app_ref
        self.clicks_count = 1

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.85)

        init_x = x - 22 if x is not None else (100 + number * 45)
        init_y = y - 22 if y is not None else 100
        self.geometry(f"44x44+{init_x}+{init_y}")
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

        self.label.bind("<Button-1>", self.start_drag)
        self.label.bind("<B1-Motion>", self.do_drag)
        self.label.bind("<Button-3>", self.show_context_menu)

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
        if self.app_ref.is_running or self.app_ref.is_capturing:
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
        self.root.title("Python AutoClicker Studio")
        self.root.geometry("460x700")
        self.root.attributes("-topmost", True)

        self.markers = []
        self.is_running = False
        self.is_capturing = False
        self.is_recording = False
        self.macro_events = []
        self._ignore_synthetic = False

        self.mouse_ctrl = mouse.Controller()
        self.capture_listener = None
        self.mode3_listener = None
        self.record_listener = None

        # Переменные настроек
        self.delay_var = tk.StringVar(value="0.5")
        self.auto_stop_var = tk.StringVar(value="10")
        self.use_auto_stop_var = tk.BooleanVar(value=True)  # По умолчанию ВКЛ

        self.mode_var = tk.StringVar(value="mode1")

        # Режим 2 (Маркеры)
        self.m2_use_loop_var = tk.BooleanVar(value=True)
        self.m2_cycles_var = tk.StringVar(value="0")

        # Режим 3 (Умножитель)
        self.m3_multi_count_var = tk.StringVar(value="3")

        # Режим 4 (Макросы)
        self.m4_use_loop_var = tk.BooleanVar(value=True)
        self.m4_cycles_var = tk.StringVar(value="0")

        self._build_ui()
        self._start_hotkey_listener()
        self._start_mode3_listener()

    def _build_ui(self):
        # ==========================================
        # 1. ОБЩИЕ НАСТРОЙКИ (ВВЕРХУ)
        # ==========================================
        gen_frame = ttk.LabelFrame(
            self.root, text="⚙️ Общие настройки", padding=10
        )
        gen_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(gen_frame, text="Задержка между действиями (сек):").grid(
            row=0, column=0, sticky="w", pady=3
        )
        ttk.Entry(gen_frame, textvariable=self.delay_var, width=8).grid(
            row=0, column=1, pady=3, sticky="e"
        )

        ttk.Checkbutton(
            gen_frame,
            text="Включить автоотключение по таймеру",
            variable=self.use_auto_stop_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=3)

        ttk.Label(gen_frame, text="Таймер автоотключения (сек):").grid(
            row=2, column=0, sticky="w", pady=3
        )
        ttk.Entry(gen_frame, textvariable=self.auto_stop_var, width=8).grid(
            row=2, column=1, pady=3, sticky="e"
        )

        # ==========================================
        # 2. РЕЖИМЫ РАБОТЫ И ИХ НАСТРОЙКИ
        # ==========================================
        modes_main_frame = ttk.LabelFrame(
            self.root, text="🎯 Выбор и настройки режима", padding=10
        )
        modes_main_frame.pack(fill="x", padx=10, pady=5)

        # --- РЕЖИМ 1 ---
        ttk.Radiobutton(
            modes_main_frame,
            text="Режим 1: Автоклик по текущему курсору",
            value="mode1",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(anchor="w", pady=(2, 0))

        self.mode1_sub = ttk.Frame(modes_main_frame, padding=(20, 2, 0, 8))
        self.mode1_sub.pack(fill="x")
        ttk.Label(
            self.mode1_sub,
            text="Кликает в точку, где находится мышь, с указанной задержкой.",
            foreground="gray",
        ).pack(anchor="w")

        # --- РЕЖИМ 2 ---
        ttk.Radiobutton(
            modes_main_frame,
            text="Режим 2: Маршрут по маркерам",
            value="mode2",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(anchor="w", pady=(5, 0))

        self.mode2_sub = ttk.Frame(modes_main_frame, padding=(20, 2, 0, 8))
        self.mode2_sub.pack(fill="x")

        m2_loop_box = ttk.Frame(self.mode2_sub)
        m2_loop_box.pack(fill="x", pady=2)
        ttk.Checkbutton(
            m2_loop_box, text="Зациклить", variable=self.m2_use_loop_var
        ).pack(side="left")
        ttk.Label(m2_loop_box, text="  Циклов (0 = ∞):").pack(side="left")
        ttk.Entry(m2_loop_box, textvariable=self.m2_cycles_var, width=6).pack(
            side="left"
        )

        btn_box1 = ttk.Frame(self.mode2_sub)
        btn_box1.pack(fill="x", pady=3)
        self.btn_add = ttk.Button(
            btn_box1, text="+ Добавить", command=self.add_marker
        )
        self.btn_add.pack(side="left", expand=True, padx=2)

        self.btn_capture = ttk.Button(
            btn_box1,
            text="🎯 Захват маркеров (СКМ)",
            command=self.toggle_capture_mode,
        )
        self.btn_capture.pack(side="left", expand=True, padx=2)

        btn_box2 = ttk.Frame(self.mode2_sub)
        btn_box2.pack(fill="x", pady=2)
        self.btn_remove_last = ttk.Button(
            btn_box2, text="Удалить последний", command=self.remove_last_marker
        )
        self.btn_remove_last.pack(side="left", expand=True, padx=2)
        self.btn_clear = ttk.Button(
            btn_box2, text="Очистить все", command=self.clear_markers
        )
        self.btn_clear.pack(side="left", expand=True, padx=2)

        # --- РЕЖИМ 3 ---
        ttk.Radiobutton(
            modes_main_frame,
            text="Режим 3: Умножитель кликов (Буст при вашем клике)",
            value="mode3",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(anchor="w", pady=(5, 0))

        self.mode3_sub = ttk.Frame(modes_main_frame, padding=(20, 2, 0, 8))
        self.mode3_sub.pack(fill="x")

        m3_box = ttk.Frame(self.mode3_sub)
        m3_box.pack(fill="x", pady=2)
        ttk.Label(m3_box, text="Сделать кликов за 1 ваше нажатие:").pack(
            side="left"
        )
        ttk.Entry(
            m3_box, textvariable=self.m3_multi_count_var, width=6
        ).pack(side="left", padx=5)

        # --- РЕЖИМ 4 ---
        ttk.Radiobutton(
            modes_main_frame,
            text="Режим 4: Запись и повтор макроса (Клики + Движения)",
            value="mode4",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(anchor="w", pady=(5, 0))

        self.mode4_sub = ttk.Frame(modes_main_frame, padding=(20, 2, 0, 8))
        self.mode4_sub.pack(fill="x")

        m4_loop_box = ttk.Frame(self.mode4_sub)
        m4_loop_box.pack(fill="x", pady=2)
        ttk.Checkbutton(
            m4_loop_box,
            text="Зациклить воспроизведение",
            variable=self.m4_use_loop_var,
        ).pack(side="left")
        ttk.Label(m4_loop_box, text="  Циклов (0 = ∞):").pack(side="left")
        ttk.Entry(m4_loop_box, textvariable=self.m4_cycles_var, width=6).pack(
            side="left"
        )

        rec_box = ttk.Frame(self.mode4_sub)
        rec_box.pack(fill="x", pady=4)
        self.btn_record = ttk.Button(
            rec_box,
            text="🔴 Начать запись действий",
            command=self.toggle_recording,
        )
        self.btn_record.pack(side="left", expand=True)

        self.macro_status_lbl = ttk.Label(rec_box, text="Записано событий: 0")
        self.macro_status_lbl.pack(side="right", padx=5)

        # ==========================================
        # 3. УПРАВЛЕНИЕ И СТАТУС (ВНИЗУ)
        # ==========================================
        self.status_label = ttk.Label(
            self.root,
            text="Статус: Остановлен [F6]",
            font=("Arial", 11, "bold"),
            foreground="red",
        )
        self.status_label.pack(pady=(10, 4))

        self.toggle_btn = ttk.Button(
            self.root, text="Старт / Стоп (F6)", command=self.toggle_clicking
        )
        self.toggle_btn.pack(pady=4, fill="x", padx=10)

        self._on_mode_change()

    def _set_widget_state(self, container, state):
        for child in container.winfo_children():
            if isinstance(child, (ttk.Frame, tk.Frame)):
                self._set_widget_state(child, state)
            else:
                try:
                    child.config(state=state)
                except tk.TclError:
                    pass

    def _on_mode_change(self):
        """Переключение видимости/активности блоков настроек."""
        if self.is_capturing:
            self.stop_capture_mode()
        if self.is_recording:
            self.stop_recording()

        mode = self.mode_var.get()

        # Активируем/деактивируем блоки в зависимости от выбранного радио-баттона
        self._set_widget_state(
            self.mode1_sub, "normal" if mode == "mode1" else "disabled"
        )
        self._set_widget_state(
            self.mode2_sub, "normal" if mode == "mode2" else "disabled"
        )
        self._set_widget_state(
            self.mode3_sub, "normal" if mode == "mode3" else "disabled"
        )
        self._set_widget_state(
            self.mode4_sub, "normal" if mode == "mode4" else "disabled"
        )

        # Управление видимостью маркеров
        if mode == "mode2":
            for m in self.markers:
                m.deiconify()
        else:
            for m in self.markers:
                m.withdraw()

    # --- РЕЖИМ 2: Захват маркеров ---
    def toggle_capture_mode(self):
        if self.is_running:
            return
        if self.is_capturing:
            self.stop_capture_mode()
        else:
            self.start_capture_mode()

    def start_capture_mode(self):
        self.is_capturing = True
        self.btn_capture.config(text="🛑 Стоп захват")
        self.status_label.config(
            text="ЗАХВАТ: Нажимайте СКМ (колесико) на экране!",
            foreground="orange",
        )

        self.capture_listener = mouse.Listener(
            on_click=self._on_capture_click
        )
        self.capture_listener.start()

    def stop_capture_mode(self):
        self.is_capturing = False
        if self.capture_listener:
            self.capture_listener.stop()
            self.capture_listener = None
        self.btn_capture.config(text="🎯 Захват маркеров (СКМ)")
        self.status_label.config(
            text="Статус: Остановлен [F6]", foreground="red"
        )

    def _on_capture_click(self, x, y, button, pressed):
        if (
            not self.is_capturing
            or not pressed
            or button not in (mouse.Button.middle, mouse.Button.right)
        ):
            return

        win_x = self.root.winfo_rootx()
        win_y = self.root.winfo_rooty()
        win_w = self.root.winfo_width()
        win_h = self.root.winfo_height()

        if win_x <= x <= win_x + win_w and win_y <= y <= win_y + win_h:
            return

        self.root.after(0, lambda: self._add_marker_at_pos(int(x), int(y)))

    def _add_marker_at_pos(self, x, y):
        if self.mode_var.get() != "mode2":
            return
        count = len(self.markers) + 1
        marker = ClickMarker(self.root, count, self, x=x, y=y)
        self.markers.append(marker)

    def add_marker(self):
        if self.mode_var.get() != "mode2":
            return
        count = len(self.markers) + 1
        marker = ClickMarker(self.root, count, self)
        self.markers.append(marker)

    def remove_marker(self, marker):
        if marker in self.markers:
            self.markers.remove(marker)
            marker.destroy()
            self._renumber_markers()

    def remove_last_marker(self):
        if self.markers:
            marker = self.markers.pop()
            marker.destroy()
            self._renumber_markers()

    def clear_markers(self):
        for m in self.markers:
            m.destroy()
        self.markers.clear()

    def _renumber_markers(self):
        for idx, m in enumerate(self.markers, start=1):
            m.set_number(idx)

    # --- РЕЖИМ 3: Умножитель кликов ---
    def _start_mode3_listener(self):
        def on_click(x, y, button, pressed):
            if (
                pressed
                and button == mouse.Button.left
                and self.is_running
                and self.mode_var.get() == "mode3"
            ):
                if not self._ignore_synthetic:
                    threading.Thread(target=self._burst_extra_clicks).start()

        self.mode3_listener = mouse.Listener(on_click=on_click)
        self.mode3_listener.daemon = True
        self.mode3_listener.start()

    def _burst_extra_clicks(self):
        self._ignore_synthetic = True
        try:
            extra = max(1, int(self.m3_multi_count_var.get()) - 1)
        except ValueError:
            extra = 1

        for _ in range(extra):
            if not self.is_running:
                break
            time.sleep(0.01)
            self.mouse_ctrl.click(mouse.Button.left)

        self._ignore_synthetic = False

    # --- РЕЖИМ 4: Запись и повтор ---
    def toggle_recording(self):
        if self.is_running:
            return
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        self.is_recording = True
        self.macro_events.clear()
        self._last_record_time = time.time()

        self.btn_record.config(text="⏹️ Остановить запись")
        self.status_label.config(
            text="ИДЕТ ЗАПИСЬ ДЕЙСТВИЙ МЫШИ...", foreground="orange"
        )

        self.record_listener = mouse.Listener(
            on_click=self._on_record_mouse_click
        )
        self.record_listener.start()

    def stop_recording(self):
        self.is_recording = False
        if self.record_listener:
            self.record_listener.stop()
            self.record_listener = None
        self.btn_record.config(text="🔴 Начать запись действий")
        self.macro_status_lbl.config(
            text=f"Записано событий: {len(self.macro_events)}"
        )
        self.status_label.config(
            text="Статус: Остановлен [F6]", foreground="red"
        )

    def _on_record_mouse_click(self, x, y, button, pressed):
        if not self.is_recording or not pressed:
            return

        now = time.time()
        delay = now - self._last_record_time
        self._last_record_time = now

        self.macro_events.append((x, y, button, delay))
        self.root.after(
            0,
            lambda: self.macro_status_lbl.config(
                text=f"Записано событий: {len(self.macro_events)}"
            ),
        )

    # --- Управление и выполнение ---
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
        if self.is_capturing:
            self.stop_capture_mode()
        if self.is_recording:
            self.stop_recording()

        mode = self.mode_var.get()

        if mode == "mode2" and not self.markers:
            messagebox.showwarning(
                "Ошибка", "Добавьте хотя бы один маркер на экран!"
            )
            return

        if mode == "mode4" and not self.macro_events:
            messagebox.showwarning("Ошибка", "Сначала запишите макрос!")
            return

        self.is_running = True
        self.status_label.config(
            text="Статус: РАБОТАЕТ [F6]", foreground="green"
        )

        if mode == "mode2":
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

            m2_use_loop = self.m2_use_loop_var.get()
            m2_max_cycles = int(self.m2_cycles_var.get())

            m4_use_loop = self.m4_use_loop_var.get()
            m4_max_cycles = int(self.m4_cycles_var.get())
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
        mode = self.mode_var.get()

        while self.is_running:
            if auto_stop_sec and (time.time() - start_time) >= auto_stop_sec:
                self.stop_clicking()
                break

            if mode == "mode1":
                self.mouse_ctrl.click(mouse.Button.left)
                time.sleep(delay)

            elif mode == "mode2":
                for marker in list(self.markers):
                    if not self.is_running:
                        break
                    x, y = marker.get_pos()
                    self.mouse_ctrl.position = (x, y)

                    for _ in range(marker.clicks_count):
                        if not self.is_running:
                            break
                        self.mouse_ctrl.click(mouse.Button.left)
                        time.sleep(0.02)

                    time.sleep(delay)

                current_cycle += 1
                if not m2_use_loop or (
                    m2_max_cycles > 0 and current_cycle >= m2_max_cycles
                ):
                    self.stop_clicking()
                    break

            elif mode == "mode3":
                time.sleep(0.1)

            elif mode == "mode4":
                self._ignore_synthetic = True
                for x, y, btn, event_delay in self.macro_events:
                    if not self.is_running:
                        break
                    time.sleep(event_delay)
                    self.mouse_ctrl.position = (x, y)
                    self.mouse_ctrl.click(btn)

                self._ignore_synthetic = False

                current_cycle += 1
                if not m4_use_loop or (
                    m4_max_cycles > 0 and current_cycle >= m4_max_cycles
                ):
                    self.stop_clicking()
                    break


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()