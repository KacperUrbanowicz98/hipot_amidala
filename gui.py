# gui.py
"""Interfejs graficzny aplikacji Hi-Pot Amidala"""
import tkinter as tk
from config import Config
from admin_panel import AdminPanel


class AmidalaApp:

    def __init__(self, root):
        self.root   = root
        self.config = Config()
        self._setup_window()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._create_main_app()

    def _setup_window(self):
        self.root.title(self.config.WINDOW_TITLE)
        self.root.state("zoomed")
        self.root.configure(bg=self.config.COLOR_BG)

    def _on_closing(self):
        self.root.destroy()

    # ------------------------------------------------------------------ #
    # GŁÓWNA APLIKACJA                                                     #
    # ------------------------------------------------------------------ #
    def _create_main_app(self):
        self._create_header()

        main_frame = tk.Frame(self.root, bg=self.config.COLOR_BG)
        main_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=(20, 60))

        self._create_scan_panel(main_frame)
        self._create_footer()
        self._bind_admin_shortcut()

    def _bind_admin_shortcut(self):
        self._d_press_count = 0
        self._d_press_timer = None
        self.root.bind("<Control-Alt-d>", self._on_config_shortcut)
        self.root.bind("<Control-Alt-D>", self._on_config_shortcut)

    def _on_config_shortcut(self, event=None):
        self._d_press_count += 1
        if self._d_press_timer:
            self.root.after_cancel(self._d_press_timer)
        self._d_press_timer = self.root.after(1000, self._reset_d_counter)
        if self._d_press_count >= 3:
            self._d_press_count = 0
            self._show_password_dialog()

    def _reset_d_counter(self):
        self._d_press_count = 0

    def _show_password_dialog(self):
        pw_win = tk.Toplevel(self.root)
        pw_win.title("Dostęp do konfiguracji")
        pw_win.geometry("400x220")
        pw_win.configure(bg=self.config.COLOR_BG)
        pw_win.resizable(False, False)
        pw_win.transient(self.root)
        pw_win.grab_set()

        frame = tk.Frame(pw_win, bg=self.config.COLOR_WHITE,
                         relief=tk.RAISED, borderwidth=2)
        frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

        tk.Label(frame, text="Dostęp do konfiguracji",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 14, "bold")).pack(pady=(20, 10))

        tk.Label(frame, text="Wprowadź hasło:",
                 bg=self.config.COLOR_WHITE, fg="#333333",
                 font=("Arial", 11)).pack(pady=(10, 5))

        pw_entry = tk.Entry(
            frame, font=("Arial", 12), width=20,
            justify="center", show="*",
            relief=tk.SOLID, borderwidth=2)
        pw_entry.pack(pady=10)
        pw_entry.focus()

        err = tk.Label(frame, text="",
                       bg=self.config.COLOR_WHITE,
                       fg=self.config.COLOR_ERROR,
                       font=("Arial", 9))
        err.pack()

        def check_password():
            if pw_entry.get() == "reconext2026":
                pw_win.destroy()
                self._show_admin_panel()
            else:
                err.config(text="Nieprawidłowe hasło!")
                pw_entry.delete(0, tk.END)
                pw_entry.focus()

        pw_entry.bind("<Return>", lambda e: check_password())

        bf = tk.Frame(frame, bg=self.config.COLOR_WHITE)
        bf.pack(pady=10)
        tk.Button(bf, text="OK",
                  bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
                  font=("Arial", 10, "bold"), width=10,
                  relief=tk.FLAT, cursor="hand2",
                  command=check_password).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="Anuluj",
                  bg="#999999", fg=self.config.COLOR_WHITE,
                  font=("Arial", 10, "bold"), width=10,
                  relief=tk.FLAT, cursor="hand2",
                  command=pw_win.destroy).pack(side=tk.LEFT, padx=5)

    def _show_admin_panel(self):
        AdminPanel(self.root, self.config).show()

    # ------------------------------------------------------------------ #
    # PANEL SKANOWANIA S/N                                                 #
    # ------------------------------------------------------------------ #
    def _create_scan_panel(self, parent):
        center = tk.Frame(parent, bg=self.config.COLOR_BG)
        center.pack(expand=True)

        scan_panel = tk.Frame(center, bg=self.config.COLOR_WHITE,
                              relief=tk.RAISED, borderwidth=2)
        scan_panel.pack(padx=50, pady=50)

        tk.Label(scan_panel, text="Skanowanie numeru seryjnego",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 20, "bold")).pack(pady=(30, 10))

        tk.Label(scan_panel,
                 text="Zeskanuj lub wprowadź numer seryjny (14 lub 17 znaków):",
                 bg=self.config.COLOR_WHITE, fg="#333333",
                 font=("Arial", 12)).pack(pady=(10, 5))

        self.serial_entry = tk.Entry(
            scan_panel, font=("Arial", 18, "bold"), width=28,
            justify="center", relief=tk.SOLID, borderwidth=2)
        self.serial_entry.pack(pady=15, padx=50)
        self.serial_entry.focus()
        self.serial_entry.bind("<Return>", lambda e: self._process_serial())

        self.scan_status_label = tk.Label(
            scan_panel, text="",
            bg=self.config.COLOR_WHITE, font=("Arial", 11))
        self.scan_status_label.pack(pady=5)

        confirm_btn = tk.Button(
            scan_panel, text="POTWIERDŹ",
            bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
            font=("Arial", 14, "bold"), width=20, height=2,
            relief=tk.FLAT, cursor="hand2",
            command=self._process_serial)
        confirm_btn.pack(pady=(10, 30), padx=50)
        confirm_btn.bind("<Enter>",
                         lambda e: confirm_btn.config(bg="#66BB6A"))
        confirm_btn.bind("<Leave>",
                         lambda e: confirm_btn.config(
                             bg=self.config.COLOR_ACCENT))

    def _process_serial(self):
        from hwid_map import HwidMap
        serial = self.serial_entry.get().strip().upper()

        if not serial:
            self.scan_status_label.config(
                text="Wprowadź numer seryjny!",
                fg=self.config.COLOR_ERROR)
            return

        valid, result = HwidMap().validate_serial(serial)

        if not valid:
            self.scan_status_label.config(
                text=f"✗ {result}", fg=self.config.COLOR_ERROR)
            self.serial_entry.delete(0, tk.END)
            self.serial_entry.focus()
            return

        model_name = result
        self.scan_status_label.config(
            text=f"✓ Model: {model_name} | SN: {len(serial)} znaków — OK",
            fg=self.config.COLOR_ACCENT)

        self.root.after(
            800,
            lambda: self._show_test_screen(serial, model_name))

    def _show_test_screen(self, serial, model_name):
        from test_screen import TestScreen
        TestScreen(
            parent     = self.root,
            config     = self.config,
            serial     = serial,
            model_name = model_name,
            app_ref    = self).show()

    # ------------------------------------------------------------------ #
    # POWRÓT DO SKANOWANIA                                                 #
    # ------------------------------------------------------------------ #
    def show_scan_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self._create_header()

        main_frame = tk.Frame(self.root, bg=self.config.COLOR_BG)
        main_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=(20, 60))

        self._create_scan_panel(main_frame)
        self._create_footer()
        self._bind_admin_shortcut()

    # ------------------------------------------------------------------ #
    # HEADER / FOOTER                                                      #
    # ------------------------------------------------------------------ #
    def _create_header(self):
        header = tk.Frame(self.root,
                          bg=self.config.COLOR_PRIMARY, height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=self.config.WINDOW_TITLE,
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 22, "bold")).pack(
                     side=tk.LEFT, padx=20, pady=15)

    def _create_footer(self):
        footer = tk.Frame(self.root,
                          bg=self.config.COLOR_PRIMARY, height=40)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)
        tk.Label(footer, text="Autor: Kacper Urbanowicz",
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 10, "bold")).pack(
                     side=tk.RIGHT, padx=20, pady=10)