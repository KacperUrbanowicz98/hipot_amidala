# test_screen.py
"""Ekran testowania Hi-Pot Amidala"""
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import threading
import time
import os
import re
from logger import save_report


class TestScreen:

    def __init__(self, parent, config, serial, model_name, app_ref=None):
        self.parent     = parent
        self.config     = config
        self.serial     = serial
        self.model_name = model_name
        self.app_ref    = app_ref
        self.operator   = "OPERATOR"

        self.device       = None
        self.test_running = False
        self.test_thread  = None
        self.start_time   = None

        self.current_voltage    = 0.0
        self.current_current    = 0.0
        self.elapsed_time       = 0.0
        self.test_result        = None
        self.last_valid_voltage = 0.0
        self.last_valid_current = 0.0

        self.interlock                  = None
        self._prev_interlock_closed     = None
        self._current_interlock_closed  = None
        self._test_completed_called     = False

        # Blokady bezpieczeństwa cyklu testowego.
        # Nowy test jest dozwolony dopiero po sekwencji OPEN -> CLOSED.
        self._lid_open_seen          = False
        self._valid_close_transition = False

        # Pierwszy SN pochodzi z ekranu głównego i jest już zwalidowany.
        self._serial_ready_for_test = True
        self._duplicate_check_done  = True
        self._duplicate_allowed     = True

        self.sn_dialog       = None
        self.sn_entry        = None
        self.sn_result_label = None
        self.sn_status_lbl   = None

        self._recent_results          = []
        self._history_frame           = None
        self._current_sn_is_duplicate = False

    # ------------------------------------------------------------------ #
    # SHOW                                                                 #
    # ------------------------------------------------------------------ #
    def show(self):
        for widget in self.parent.winfo_children():
            widget.destroy()

        self._create_header()

        self.main_frame = tk.Frame(self.parent, bg=self.config.COLOR_BG)
        self.main_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=(20, 60))

        self._create_device_info()
        self._create_test_params()
        self._create_live_display()
        self._create_progress_bar()
        self._create_interlock_status()
        self._create_control_buttons()
        self._create_history_panel()
        self._create_footer()

        self._connect_device()
        self._connect_interlock()

    # ------------------------------------------------------------------ #
    # HEADER / FOOTER                                                      #
    # ------------------------------------------------------------------ #
    def _create_header(self):
        header = tk.Frame(self.parent,
                          bg=self.config.COLOR_PRIMARY, height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(header, text=self.config.WINDOW_TITLE,
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 22, "bold")).pack(
                     side=tk.LEFT, padx=20, pady=15)

        back_border = tk.Frame(header, bg=self.config.COLOR_WHITE,
                               padx=1, pady=1)
        back_border.pack(side=tk.RIGHT, padx=10, pady=15)
        self.back_button = tk.Button(
            back_border, text="← Powrót do menu",
            bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
            font=("Arial", 10, "bold"), relief=tk.FLAT, cursor="hand2",
            padx=10, pady=4, command=self._go_back)
        self.back_button.pack()
        self.back_button.bind("<Enter>",
            lambda e: self.back_button.config(bg="#1a5276"))
        self.back_button.bind("<Leave>",
            lambda e: self.back_button.config(bg=self.config.COLOR_PRIMARY))

    def _create_footer(self):
        footer = tk.Frame(self.parent,
                          bg=self.config.COLOR_PRIMARY, height=40)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)
        tk.Label(footer, text="Autor: Kacper Urbanowicz",
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 10, "bold")).pack(
                     side=tk.RIGHT, padx=20, pady=10)

    def _go_back(self):
        if self.test_running:
            messagebox.showwarning(
                "Test w toku",
                "Nie można wrócić do menu podczas testu!\n"
                "Zatrzymaj test przyciskiem STOP.")
            return
        self._cleanup_and_go_back()

    def _cleanup_and_go_back(self):
        if self.sn_dialog and self.sn_dialog.winfo_exists():
            self.sn_dialog.grab_release()
            self.sn_dialog.destroy()
            self.sn_dialog = None
        if self.interlock:
            self.interlock.disconnect()
        if self.device:
            self.device.disconnect()
        if self.app_ref:
            self.app_ref.show_scan_screen()

    # ------------------------------------------------------------------ #
    # PANELE INFORMACYJNE                                                  #
    # ------------------------------------------------------------------ #
    def _create_device_info(self):
        info_frame = tk.Frame(self.main_frame, bg=self.config.COLOR_WHITE,
                              relief=tk.RAISED, borderwidth=2)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        row = tk.Frame(info_frame, bg=self.config.COLOR_WHITE)
        row.pack(padx=20, pady=12)

        tk.Label(row, text="Model:",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 11, "bold")).grid(
                     row=0, column=0, sticky='w', padx=(0, 8))
        tk.Label(row, text=self.model_name,
                 bg=self.config.COLOR_WHITE, fg="#333333",
                 font=("Arial", 11)).grid(
                     row=0, column=1, sticky='w', padx=(0, 30))

        tk.Label(row, text="S/N:",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 11, "bold")).grid(
                     row=0, column=2, sticky='w', padx=(0, 8))
        self.sn_display_label = tk.Label(
            row, text=self.serial,
            bg=self.config.COLOR_WHITE, fg="#333333",
            font=("Arial", 11))
        self.sn_display_label.grid(row=0, column=3, sticky='w')

    def _create_test_params(self):
        p = self.config.TEST_PROFILE

        params_frame = tk.Frame(self.main_frame, bg=self.config.COLOR_WHITE,
                                relief=tk.RAISED, borderwidth=2)
        params_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(params_frame, text="Parametry testu ACW",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 12, "bold")).pack(pady=(12, 8))

        grid = tk.Frame(params_frame, bg=self.config.COLOR_WHITE)
        grid.pack(padx=20, pady=(0, 12))

        def lbl(row, col, label, value):
            tk.Label(grid, text=label,
                     bg=self.config.COLOR_WHITE, fg="#666666",
                     font=("Arial", 10)).grid(
                         row=row, column=col, sticky='w',
                         padx=(0, 5), pady=3)
            tk.Label(grid, text=value,
                     bg=self.config.COLOR_WHITE, fg="#333333",
                     font=("Arial", 10, "bold")).grid(
                         row=row, column=col+1, sticky='w',
                         padx=(0, 30), pady=3)

        total = p['ramp_time'] + p['dwell'] + p['ramp_dn']
        lbl(0, 0, "Napięcie:",     f"{p['voltage'] / 1000:.2f} kV")
        lbl(0, 2, "Tryb:",         p['type'])
        lbl(1, 0, "Limit prądu:",  f"{p['limit_low']:.3f} – {p['limit_high']:.3f} mA")
        lbl(1, 2, "Czas całk.:",   f"{total:.1f} s")
        lbl(2, 0, "Ramp up:",      f"{p['ramp_time']:.1f} s")
        lbl(2, 2, "Dwell:",        f"{p['dwell']:.1f} s")
        lbl(3, 0, "Częstotliw.:",  f"{p['frequency']} Hz")
        lbl(3, 2, "Arc Sense:",    str(p['arc_sense']))

    # ------------------------------------------------------------------ #
    # LIVE DISPLAY                                                         #
    # ------------------------------------------------------------------ #
    def _create_live_display(self):
        display_frame = tk.Frame(self.main_frame, bg=self.config.COLOR_WHITE,
                                 relief=tk.RAISED, borderwidth=2)
        display_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tk.Label(display_frame, text="Pomiary na żywo",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 12, "bold")).pack(pady=(12, 8))

        grid = tk.Frame(display_frame, bg=self.config.COLOR_WHITE)
        grid.pack(expand=True, pady=15)

        for col, (title, attr, fg) in enumerate([
            ("NAPIĘCIE", "voltage_label", self.config.COLOR_PRIMARY),
            ("PRĄD",     "current_label", self.config.COLOR_ACCENT),
            ("CZAS",     "time_label",    "#333333"),
        ]):
            f = tk.Frame(grid, bg=self.config.COLOR_WHITE)
            f.grid(row=0, column=col, padx=40)
            tk.Label(f, text=title,
                     bg=self.config.COLOR_WHITE, fg="#666666",
                     font=("Arial", 10)).pack()
            lbl = tk.Label(f, text="0",
                           bg=self.config.COLOR_WHITE, fg=fg,
                           font=("Arial", 32, "bold"))
            lbl.pack(pady=5)
            setattr(self, attr, lbl)

        self.voltage_label.config(text="0 V")
        self.current_label.config(text="0.00 mA")
        self.time_label.config(text="0.0 s")

    # ------------------------------------------------------------------ #
    # PASEK POSTĘPU                                                        #
    # ------------------------------------------------------------------ #
    def _create_progress_bar(self):
        pf = tk.Frame(self.main_frame, bg=self.config.COLOR_BG)
        pf.pack(fill=tk.X, pady=(0, 10))

        self.status_label = tk.Label(
            pf, text="Gotowy do rozpoczęcia testu",
            bg=self.config.COLOR_BG, fg="#666666", font=("Arial", 11))
        self.status_label.pack(pady=(0, 6))

        self.progress_canvas = tk.Canvas(
            pf, height=30, bg=self.config.COLOR_WHITE,
            highlightthickness=1, highlightbackground="#cccccc")
        self.progress_canvas.pack(fill=tk.X)
        self.progress_rect = self.progress_canvas.create_rectangle(
            0, 0, 0, 30, fill=self.config.COLOR_ACCENT, outline="")

    # ------------------------------------------------------------------ #
    # INTERLOCK                                                            #
    # ------------------------------------------------------------------ #
    def _create_interlock_status(self):
        self.interlock_frame = tk.Frame(
            self.main_frame, bg="#fff8e1",
            relief=tk.RAISED, borderwidth=2)
        self.interlock_frame.pack(fill=tk.X, pady=(0, 8))

        self.interlock_label = tk.Label(
            self.interlock_frame,
            text="⏳ Łączenie z interlockiem (Arduino)...",
            bg="#fff8e1", fg="#FF9800", font=("Arial", 11, "bold"))
        self.interlock_label.pack(pady=8)

    def _connect_interlock(self):
        if not getattr(self.config, "INTERLOCK_ENABLED", True):
            self.interlock_label.config(
                text="⚠ Interlock wyłączony — tryb ręczny",
                fg="#FF9800", bg="#fff8e1")
            self.start_button.config(state="normal")
            return

        port = getattr(self.config, "INTERLOCK_PORT", None)
        if not port:
            self.interlock_label.config(
                text="⚠ Brak portu Arduino — tryb ręczny",
                fg="#FF9800", bg="#fff8e1")
            self.start_button.config(state="normal")
            return

        from interlock import InterlockMonitor
        baud = getattr(self.config, "INTERLOCK_BAUDRATE", 9600)
        self.interlock = InterlockMonitor(port=port, baudrate=baud)

        if self.interlock.connect():
            self.interlock.set_on_change(self._on_interlock_change)
            self.interlock.start_monitoring()
            self.interlock_label.config(
                text="⏳ Oczekiwanie na stan klapy...",
                fg="#FF9800", bg="#fff8e1")
            self.start_button.config(state="disabled")
        else:
            self.interlock_label.config(
                text=f"✗ Błąd połączenia z Arduino ({port}) — tryb ręczny",
                fg=self.config.COLOR_ERROR, bg="#ffebee")
            self.interlock_frame.config(bg="#ffebee")
            self.start_button.config(state="normal")

    def _on_interlock_change(self, closed):
        try:
            self.parent.after(0, lambda: self._apply_interlock_state(closed))
        except Exception:
            pass

    def _interlock_enforced(self) -> bool:
        """True, gdy interlock jest aktywny i połączony."""
        return bool(
            getattr(self.config, "INTERLOCK_ENABLED", True)
            and self.interlock
            and self.interlock.connected
        )

    def _attempt_safe_start(self) -> bool:
        """
        Jedyna bramka automatycznego startu.

        W trybie interlock wymagane są jednocześnie:
        - poprawny, zatwierdzony SN,
        - zakończona kontrola duplikatu,
        - aktualny stan CLOSED,
        - świeże przejście OPEN -> CLOSED.
        """
        if self.test_running:
            return False
        if not self.device or not self.device.connected:
            return False
        if not self._serial_ready_for_test:
            return False
        if not self._duplicate_check_done or not self._duplicate_allowed:
            return False

        if self._interlock_enforced():
            if self._current_interlock_closed is not True:
                self.status_label.config(
                    text="SN zaakceptowany — zamknij klapę, aby rozpocząć test",
                    fg="#FF9800")
                return False
            if not self._valid_close_transition:
                self.status_label.config(
                    text="⛔ Otwórz klapę, wymień urządzenie i zamknij ją ponownie",
                    fg=self.config.COLOR_ERROR)
                return False

            self._start_test()
            return True

        # Tryb ręczny: nigdy nie uruchamiaj testu automatycznie po skanie.
        self.start_button.config(state="normal")
        self.status_label.config(
            text="SN zaakceptowany — naciśnij START TEST",
            fg="#FF9800")
        return False

    def _apply_interlock_state(self, closed):
        self._current_interlock_closed = closed

        if closed is None:
            self._valid_close_transition = False
            self.interlock_label.config(
                text="⚠ Utracono połączenie z Arduino — tryb ręczny",
                fg="#FF9800", bg="#fff8e1")
            self.interlock_frame.config(bg="#fff8e1")
            if not self.test_running and self._serial_ready_for_test:
                self.start_button.config(state="normal")
            return

        if closed:
            # Sam stan CLOSED nie może wystarczyć do startu. Akceptujemy
            # wyłącznie rzeczywistą zmianę OPEN -> CLOSED.
            if self._prev_interlock_closed is not False or not self._lid_open_seen:
                self._valid_close_transition = False
                self.interlock_label.config(
                    text="🔒 Klapa ZAMKNIĘTA — przed nowym testem otwórz ją i zamknij ponownie",
                    fg="#FF9800", bg="#fff8e1")
                self.interlock_frame.config(bg="#fff8e1")
                self.start_button.config(state="disabled")
                self._prev_interlock_closed = True
                return

            # Ważne przejście OPEN -> CLOSED. Jest jednorazowe i zostanie
            # skonsumowane przez _start_test().
            self._valid_close_transition = True
            self._lid_open_seen = False
            self.interlock_label.config(
                text="🔒 Klapa ZAMKNIĘTA — sprawdzam gotowość testu...",
                fg=self.config.COLOR_ACCENT, bg="#e8f5e9")
            self.interlock_frame.config(bg="#e8f5e9")
            self._prev_interlock_closed = True

            if self.sn_dialog and self.sn_dialog.winfo_exists():
                if not self._try_auto_confirm_sn():
                    self._valid_close_transition = False
                    return

            self._attempt_safe_start()
            return

        # Stan OPEN uzbraja dokładnie jeden następny start po zamknięciu.
        self._lid_open_seen = True
        self._valid_close_transition = False
        self._prev_interlock_closed = False
        self.interlock_label.config(
            text="🔓 Klapa OTWARTA — włóż urządzenie, zeskanuj SN i zamknij klapę",
            fg=self.config.COLOR_ERROR, bg="#ffebee")
        self.interlock_frame.config(bg="#ffebee")

        if self.test_running:
            self.test_running = False
            if self.device:
                self.device.stop_test()
            self.start_button.config(state='disabled')
            self.stop_button.config(state='disabled')
            self.back_button.config(state='normal')
            self.status_label.config(
                text="⛔ Test przerwany — klapa została otwarta!",
                fg=self.config.COLOR_ERROR)
            messagebox.showwarning(
                "Test przerwany",
                "Klapa została otwarta podczas testu!\n"
                "Test został automatycznie zatrzymany.\n\n"
                "Zeskanuj poprawny SN i zamknij klapę ponownie.",
                parent=self.parent)
        else:
            self.start_button.config(state="disabled")

    # ------------------------------------------------------------------ #
    # PRZYCISKI                                                            #
    # ------------------------------------------------------------------ #
    def _create_control_buttons(self):
        bf = tk.Frame(self.main_frame, bg=self.config.COLOR_BG)
        bf.pack(fill=tk.X, pady=(0, 8))

        self.start_button = tk.Button(
            bf, text="START TEST",
            bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
            font=("Arial", 16, "bold"), height=2, relief=tk.FLAT,
            cursor="hand2", command=self._start_test)
        self.start_button.pack(side=tk.LEFT, expand=True,
                               fill=tk.X, padx=(0, 5))

        self.stop_button = tk.Button(
            bf, text="STOP",
            bg=self.config.COLOR_ERROR, fg=self.config.COLOR_WHITE,
            font=("Arial", 16, "bold"), height=2, relief=tk.FLAT,
            cursor="hand2", state="disabled", command=self._stop_test)
        self.stop_button.pack(side=tk.LEFT, expand=True,
                              fill=tk.X, padx=5)

        self.next_sn_button = tk.Button(
            bf, text="➜ Następny SN",
            bg="#607D8B", fg=self.config.COLOR_WHITE,
            font=("Arial", 16, "bold"), height=2, relief=tk.FLAT,
            cursor="hand2", state="disabled",
            command=self._open_sn_dialog_manually)
        self.next_sn_button.pack(side=tk.LEFT, expand=True,
                                 fill=tk.X, padx=(5, 0))

    # ------------------------------------------------------------------ #
    # HISTORIA                                                             #
    # ------------------------------------------------------------------ #
    def _create_history_panel(self):
        outer = tk.Frame(self.main_frame, bg=self.config.COLOR_WHITE,
                         relief=tk.RAISED, borderwidth=2)
        outer.pack(fill=tk.X, pady=(0, 0))

        top = tk.Frame(outer, bg=self.config.COLOR_WHITE)
        top.pack(fill=tk.X, padx=10, pady=(5, 2))

        tk.Label(top, text="Ostatnie wyniki",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT)

        # Nagłówek tabeli
        hdr = tk.Frame(outer, bg=self.config.COLOR_PRIMARY)
        hdr.pack(fill=tk.X, padx=10, pady=(2, 0))
        for text, width in [("Czas", 8), ("Numer seryjny", 22),
                             ("Model", 16), ("Wynik", 7)]:
            tk.Label(hdr, text=text,
                     bg=self.config.COLOR_PRIMARY,
                     fg=self.config.COLOR_WHITE,
                     font=("Arial", 8, "bold"),
                     width=width, anchor="center",
                     pady=2).pack(side=tk.LEFT)

        self._history_frame = tk.Frame(outer, bg=self.config.COLOR_WHITE)
        self._history_frame.pack(fill=tk.X, padx=10, pady=(1, 5))
        self._refresh_history()

    def _refresh_history(self):
        if not self._history_frame or \
                not self._history_frame.winfo_exists():
            return
        for w in self._history_frame.winfo_children():
            w.destroy()

        if not self._recent_results:
            tk.Label(self._history_frame,
                     text="Brak wyników w tej sesji",
                     bg=self.config.COLOR_WHITE, fg="#aaaaaa",
                     font=("Arial", 8, "italic")).pack(pady=3)
            return

        for idx, entry in enumerate(reversed(self._recent_results)):
            bg        = "#f5f5f5" if idx % 2 == 0 else self.config.COLOR_WHITE
            row       = tk.Frame(self._history_frame, bg=bg)
            row.pack(fill=tk.X)
            result_fg = (self.config.COLOR_ACCENT
                         if entry["result"] == "PASS"
                         else self.config.COLOR_ERROR)
            dup_marker = " ⚠" if entry.get("duplicate") else ""

            for text, width, fg in [
                (entry["time"],                   8,  "#666666"),
                (entry["serial"] + dup_marker,   22,
                 "#FF9800" if entry.get("duplicate") else "#333333"),
                (entry["model"],                 16,  "#333333"),
                (entry["result"],                 7,  result_fg),
            ]:
                tk.Label(row, text=text, bg=bg, fg=fg,
                         font=("Arial", 8), width=width,
                         anchor="center", pady=2).pack(side=tk.LEFT)

    def _add_recent_result(self, serial, model, result, duplicate=False):
        self._recent_results.append({
            "time":      datetime.now().strftime("%H:%M:%S"),
            "serial":    serial,
            "model":     model,
            "result":    result,
            "duplicate": duplicate,
        })
        if len(self._recent_results) > 5:
            self._recent_results = self._recent_results[-5:]
        self._refresh_history()

    # ------------------------------------------------------------------ #
    # POŁĄCZENIE Z URZĄDZENIEM                                             #
    # ------------------------------------------------------------------ #
    def _connect_device(self):
        try:
            from hipot_device import ChromaHiPotDevice
            self.device = ChromaHiPotDevice(
                port=self.config.DEFAULT_COM_PORT,
                baudrate=self.config.DEFAULT_BAUDRATE)
            self.status_label.config(
                text="Łączenie z urządzeniem Hi-Pot...", fg="#FF9800")
            if self.device.connect():
                self._configure_device()
            else:
                self.status_label.config(
                    text="✗ Błąd połączenia z urządzeniem!",
                    fg=self.config.COLOR_ERROR)
                self.start_button.config(state="disabled")
        except Exception as e:
            self.status_label.config(
                text=f"✗ Błąd: {e}", fg=self.config.COLOR_ERROR)
            self.start_button.config(state="disabled")

    def _configure_device(self):
        try:
            self.device.clear_steps()
            self.device.configure_acw(self.config.TEST_PROFILE)
            self.status_label.config(
                text="✓ Urządzenie skonfigurowane i gotowe",
                fg=self.config.COLOR_ACCENT)
        except Exception as e:
            self.status_label.config(
                text=f"✗ Błąd konfiguracji: {e}",
                fg=self.config.COLOR_ERROR)

    # ------------------------------------------------------------------ #
    # LOGIKA TESTU                                                         #
    # ------------------------------------------------------------------ #
    def _start_test(self):
        if self.test_running:
            return

        # Obrona ostatniej linii: nawet przypadkowe wywołanie tej metody
        # nie ominie interlocka ani kontroli numeru seryjnego.
        if self._interlock_enforced():
            if self._current_interlock_closed is not True:
                self.status_label.config(
                    text="⛔ Start zablokowany — klapa jest otwarta",
                    fg=self.config.COLOR_ERROR)
                return
            if not self._valid_close_transition:
                self.status_label.config(
                    text="⛔ Start zablokowany — wymagane otwarcie i ponowne zamknięcie klapy",
                    fg=self.config.COLOR_ERROR)
                return
            if not self._serial_ready_for_test:
                self.status_label.config(
                    text="⛔ Start zablokowany — brak zatwierdzonego SN",
                    fg=self.config.COLOR_ERROR)
                return
            if not self._duplicate_check_done or not self._duplicate_allowed:
                self.status_label.config(
                    text="⏳ Start zablokowany — trwa kontrola numeru seryjnego",
                    fg="#FF9800")
                return

            # Przejście OPEN -> CLOSED jest jednorazowe.
            self._valid_close_transition = False

        self._test_completed_called = False
        self.test_running = True
        self.start_time   = time.time()

        self.sn_display_label.config(text=self.serial)
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.back_button.config(state="disabled")
        self.next_sn_button.config(state="disabled")
        self.status_label.config(text="🔄 Test w toku...", fg="#FF9800")

        self.test_thread = threading.Thread(
            target=self._run_test_background, daemon=True)
        self.test_thread.start()

    def _run_test_background(self):
        try:
            self.device.start_test()
            p          = self.config.TEST_PROFILE
            total_time = p['ramp_time'] + p['dwell'] + p['ramp_dn']

            time.sleep(1.5)
            if not self.test_running:
                return

            while self.test_running:
                status  = self.device.get_status()
                elapsed = time.time() - self.start_time

                if status == "STOPPED" and elapsed >= 2.0:
                    break

                measurements = self.device.read_measurements()
                if measurements:
                    v = measurements['output_voltage']
                    i = measurements['measure_current'] * 1000  # A → mA
                    self.current_voltage = v
                    self.current_current = i
                    if 0 < v < 1e6:
                        self.last_valid_voltage = v
                    if 0 < i < 9999:
                        self.last_valid_current = i

                self.elapsed_time = time.time() - self.start_time
                self.parent.after(0, self._update_display)

                if self.elapsed_time > total_time + 5:
                    break

                time.sleep(0.1)

            self.parent.after(0, self._test_completed)

        except Exception as e:
            self.parent.after(0, lambda: self._test_error(str(e)))

    def _update_display(self):
        self.voltage_label.config(text=f"{int(self.current_voltage)} V")
        self.current_label.config(text=f"{self.current_current:.2f} mA")
        self.time_label.config(text=f"{self.elapsed_time:.1f} s")

        p          = self.config.TEST_PROFILE
        total_time = p['ramp_time'] + p['dwell'] + p['ramp_dn']
        progress   = min(self.elapsed_time / total_time, 1.0) \
                     if total_time > 0 else 0
        cw = self.progress_canvas.winfo_width()
        self.progress_canvas.coords(
            self.progress_rect, 0, 0, cw * progress, 30)

    def _test_completed(self):
        if self._test_completed_called:
            return
        self._test_completed_called = True
        self.test_running = False

        # Po każdym zakończonym teście wymuszamy nowy pełny cykl:
        # OPEN -> nowy SN -> CLOSED. Zamknięta klapa po poprzednim teście
        # nie może uruchomić kolejnego urządzenia.
        self._serial_ready_for_test = False
        self._duplicate_check_done  = False
        self._duplicate_allowed     = False
        self._valid_close_transition = False
        self._lid_open_seen          = False

        result, data = self.device.get_test_result()
        self.test_result = result

        self.start_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.back_button.config(state="normal")
        self.next_sn_button.config(state="normal")

        if result == "PASS":
            self.status_label.config(
                text="✓ TEST ZALICZONY (PASS)",
                fg=self.config.COLOR_ACCENT)
        else:
            self.status_label.config(
                text="✗ TEST NIEZALICZONY (FAIL)",
                fg=self.config.COLOR_ERROR)

        # Napięcie i prąd do logu
        OVERFLOW = 9.0e+37
        if data:
            try:
                raw_v  = float(data.get("output_voltage")   or 0)
                raw_mi = float(data.get("measured_current") or 0)
            except (TypeError, ValueError):
                raw_v, raw_mi = 0.0, 0.0
            vtm_val = (raw_v / 1000 if 0 < raw_v < OVERFLOW
                       else self.last_valid_voltage / 1000)
            im_val  = (raw_mi if 0 < raw_mi < 9999
                       else self.last_valid_current)
        else:
            vtm_val = self.last_valid_voltage / 1000
            im_val  = self.last_valid_current

        error_code = str(data.get("error_code", "")) if data else ""

        # Zapis raportu
        try:
            save_report(
                operator   = self.operator,
                program    = self.model_name,
                serial     = self.serial,
                vtm        = vtm_val,
                im         = im_val,
                result     = result,
                error_code = error_code,
                log_dir    = self.config.LOG_DIR,
            )
        except Exception as e:
            print(f"[LOG] Błąd zapisu: {e}")

        self._add_recent_result(
            serial    = self.serial,
            model     = self.model_name,
            result    = result,
            duplicate = self._current_sn_is_duplicate,
        )

        if self._interlock_enforced():
            self.interlock_label.config(
                text="🔒 Test zakończony — otwórz klapę przed następnym testem",
                fg="#FF9800", bg="#fff8e1")
            self.interlock_frame.config(bg="#fff8e1")

        self.parent.after(2000,
            lambda: self._show_next_sn_dialog(result))

    def _test_error(self, msg):
        self.test_running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.back_button.config(state="normal")
        self.next_sn_button.config(state="disabled")
        self.status_label.config(
            text=f"✗ Błąd testu: {msg}", fg=self.config.COLOR_ERROR)

    def _stop_test(self):
        self.test_running = False
        if self.device:
            self.device.stop_test()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.back_button.config(state="normal")
        self.next_sn_button.config(state="disabled")
        self.status_label.config(
            text="⚠ Test przerwany przez użytkownika", fg="#FF9800")

    # ------------------------------------------------------------------ #
    # DUPLIKAT SN                                                          #
    # ------------------------------------------------------------------ #
    def _check_serial_duplicate(self, serial: str) -> dict:
        # Sprawdź w historii sesji
        for entry in self._recent_results:
            if entry["serial"].upper() == serial.upper():
                return {"found": True, "where": "session",
                        "last_time": entry["time"],
                        "last_result": entry["result"]}

        # Sprawdź w plikach logów
        log_dir = getattr(self.config, "LOG_DIR", "logs")
        if not os.path.isdir(log_dir):
            return {"found": False, "where": None,
                    "last_time": None, "last_result": None}

        pattern = re.compile(
            r'^' + re.escape(serial.upper()) + r'_(\d{14})\.txt$',
            re.IGNORECASE)

        matches = []
        try:
            for fname in os.listdir(log_dir):
                m = pattern.match(fname)
                if not m:
                    continue
                try:
                    ts = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
                except ValueError:
                    continue
                matches.append((m.group(1), fname))
        except Exception:
            return {"found": False, "where": None,
                    "last_time": None, "last_result": None}

        if not matches:
            return {"found": False, "where": None,
                    "last_time": None, "last_result": None}

        matches.sort(key=lambda x: x[0], reverse=True)
        latest_ts, latest_fname = matches[0]

        try:
            dt        = datetime.strptime(latest_ts, "%Y%m%d%H%M%S")
            last_time = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            last_time = latest_ts

        last_result = None
        try:
            with open(os.path.join(log_dir, latest_fname),
                      encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().lower().startswith("total result:"):
                        val = line.split(":", 1)[-1].strip().upper()
                        last_result = "PASS" if val == "PASS" else "FAIL"
                        break
        except Exception:
            pass

        return {"found": True, "where": "logs",
                "last_time": last_time, "last_result": last_result}

    # ------------------------------------------------------------------ #
    # OKNO NASTĘPNY SN                                                     #
    # ------------------------------------------------------------------ #
    def _open_sn_dialog_manually(self):
        if self.sn_dialog and self.sn_dialog.winfo_exists():
            self.sn_dialog.lift()
            self.sn_dialog.focus()
            return
        self._show_next_sn_dialog(self.test_result or "PASS")

    def _show_next_sn_dialog(self, result):
        if self.sn_dialog and self.sn_dialog.winfo_exists():
            self._update_sn_dialog(result)
            self.sn_dialog.lift()
            return

        dialog = tk.Toplevel(self.parent)
        dialog.title("Następny numer seryjny")
        dialog.geometry("450x260")
        dialog.configure(bg=self.config.COLOR_WHITE)
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.update_idletasks()
        x = self.parent.winfo_screenwidth()  // 2 - 225
        y = self.parent.winfo_screenheight() // 2 - 130
        dialog.geometry(f"+{x}+{y}")
        self.sn_dialog = dialog

        result_color = (self.config.COLOR_ACCENT if result == "PASS"
                        else self.config.COLOR_ERROR)
        self.sn_result_label = tk.Label(
            dialog, text=f"Ostatni wynik: {result}",
            bg=self.config.COLOR_WHITE, fg=result_color,
            font=("Arial", 13, "bold"))
        self.sn_result_label.pack(pady=(15, 5))

        tk.Frame(dialog, bg="#cccccc", height=1).pack(
            fill=tk.X, padx=20, pady=(0, 12))

        tk.Label(dialog, text="Zeskanuj kolejny numer seryjny:",
                 bg=self.config.COLOR_WHITE, fg="#333333",
                 font=("Arial", 11, "bold")).pack(pady=(0, 5))

        self.sn_entry = tk.Entry(
            dialog, font=("Arial", 14, "bold"), width=28,
            justify="center", relief=tk.SOLID, borderwidth=2)
        self.sn_entry.pack(pady=5, padx=30)
        self.sn_entry.focus()
        self.sn_entry.bind("<Return>", lambda e: self._confirm_next_sn())

        instruction = (
            "Otwórz klapę, wymień urządzenie, zeskanuj SN i zamknij klapę"
            if self._current_interlock_closed is True
            else "Zeskanuj SN i zamknij klapę, aby rozpocząć test"
        )
        self.sn_status_lbl = tk.Label(
            dialog,
            text=instruction,
            bg=self.config.COLOR_WHITE, fg="#888888", font=("Arial", 9))
        self.sn_status_lbl.pack()

        tk.Button(dialog, text="Powrót do menu",
                  bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), width=18, height=1,
                  relief=tk.FLAT, cursor="hand2",
                  command=self._back_from_dialog).pack(pady=12)

    def _update_sn_dialog(self, result):
        result_color = (self.config.COLOR_ACCENT if result == "PASS"
                        else self.config.COLOR_ERROR)
        self.sn_result_label.config(
            text=f"Ostatni wynik: {result}", fg=result_color)
        self.sn_entry.config(state="normal")
        self.sn_entry.delete(0, tk.END)
        instruction = (
            "Otwórz klapę, wymień urządzenie, zeskanuj SN i zamknij klapę"
            if self._current_interlock_closed is True
            else "Zeskanuj SN i zamknij klapę, aby rozpocząć test"
        )
        self.sn_status_lbl.config(
            text=instruction,
            fg="#888888", bg=self.config.COLOR_WHITE)
        self.sn_entry.focus()

    def _try_auto_confirm_sn(self) -> bool:
        from hwid_map import HwidMap
        new_serial = self.sn_entry.get().strip().upper()
        valid, result = HwidMap().validate_serial(new_serial)

        if not valid:
            self.sn_status_lbl.config(
                text=f"✗ {result} — popraw SN i zamknij klapę ponownie",
                fg=self.config.COLOR_ERROR)
            self.sn_entry.config(state="normal")
            self.sn_entry.focus()
            return False

        self._apply_new_serial(new_serial, result)
        self.sn_dialog.grab_release()
        self.sn_dialog.destroy()
        self.sn_dialog = None

        threading.Thread(
            target=self._check_duplicate_async,
            args=(new_serial,), daemon=True).start()
        return True

    def _confirm_next_sn(self):
        from hwid_map import HwidMap
        new_serial = self.sn_entry.get().strip().upper()
        valid, result = HwidMap().validate_serial(new_serial)

        if not valid:
            self.sn_status_lbl.config(
                text=f"✗ {result}", fg=self.config.COLOR_ERROR)
            return

        self._apply_new_serial(new_serial, result)
        self.sn_dialog.grab_release()
        self.sn_dialog.destroy()
        self.sn_dialog = None

        threading.Thread(
            target=self._check_duplicate_async,
            args=(new_serial,), daemon=True).start()

    def _apply_new_serial(self, new_serial: str, model_name: str):
        """Wspólna logika resetu stanu po podaniu nowego SN."""
        self.serial     = new_serial
        self.model_name = model_name
        self._current_sn_is_duplicate = False

        self._serial_ready_for_test = True
        self._duplicate_check_done  = False
        self._duplicate_allowed     = False
        self.start_button.config(state="disabled")

        self.sn_display_label.config(text=self.serial)
        self.test_result        = None
        self.elapsed_time       = 0.0
        self.current_voltage    = 0.0
        self.current_current    = 0.0
        self.last_valid_voltage = 0.0
        self.last_valid_current = 0.0
        self.voltage_label.config(text="0 V")
        self.current_label.config(text="0.00 mA")
        self.time_label.config(text="0.0 s")
        self.progress_canvas.coords(self.progress_rect, 0, 0, 0, 30)
        if self._interlock_enforced():
            if self._current_interlock_closed is True and not self._valid_close_transition:
                msg = "SN zaakceptowany — otwórz klapę i zamknij ją ponownie"
            elif self._current_interlock_closed is False:
                msg = "SN zaakceptowany — zamknij klapę po włożeniu urządzenia"
            else:
                msg = "SN zaakceptowany — oczekiwanie na interlock"
            self.status_label.config(text=msg, fg="#FF9800")
        else:
            self.status_label.config(
                text="Sprawdzanie numeru seryjnego...", fg="#FF9800")

    def _check_duplicate_async(self, serial: str):
        try:
            dup = self._check_serial_duplicate(serial)
            self._current_sn_is_duplicate = dup["found"]

            if dup["found"]:
                where_txt  = ("tej sesji" if dup["where"] == "session"
                              else f"logów ({dup['last_time']})")
                result_txt = (f" (wynik: {dup['last_result']})"
                              if dup["last_result"] else "")

                def show_warning():
                    self.status_label.config(
                        text=f"⚠ DUPLIKAT: SN {serial} był już testowany"
                             f" — {where_txt}{result_txt}",
                        fg="#E65100")
                    ans = messagebox.askyesno(
                        "Duplikat SN!",
                        f"SN {serial} był już testowany!\n"
                        f"{where_txt}{result_txt}\n\n"
                        f"Na pewno chcesz kontynuować?",
                        parent=self.parent)

                    self._duplicate_check_done = True
                    self._duplicate_allowed = bool(ans)

                    if ans:
                        self._attempt_safe_start()
                    else:
                        self._serial_ready_for_test = False
                        self._valid_close_transition = False
                        self.status_label.config(
                            text="Test anulowany — zeskanuj inny numer seryjny",
                            fg=self.config.COLOR_ERROR)
                        self._show_next_sn_dialog(self.test_result or "PASS")

                self.parent.after(0, show_warning)
            else:
                def approve_serial():
                    self._duplicate_check_done = True
                    self._duplicate_allowed = True
                    self._attempt_safe_start()

                self.parent.after(0, approve_serial)

        except Exception as e:
            print(f"[DUP] Błąd: {e}")

            def fail_safe():
                # Błąd kontroli nie może automatycznie uruchomić wysokiego napięcia.
                self._duplicate_check_done = False
                self._duplicate_allowed = False
                self._valid_close_transition = False
                self.start_button.config(state="disabled")
                self.status_label.config(
                    text="⛔ Nie udało się sprawdzić SN — test zablokowany",
                    fg=self.config.COLOR_ERROR)
                messagebox.showerror(
                    "Kontrola numeru seryjnego",
                    "Nie udało się sprawdzić, czy numer seryjny był już testowany.\n"
                    "Test nie został uruchomiony.",
                    parent=self.parent)

            self.parent.after(0, fail_safe)

    def _back_from_dialog(self):
        if self.sn_dialog and self.sn_dialog.winfo_exists():
            self.sn_dialog.grab_release()
            self.sn_dialog.destroy()
            self.sn_dialog = None
        self._cleanup_and_go_back()