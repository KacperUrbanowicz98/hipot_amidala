# test_screen.py
"""Ekran testowania Hi-Pot Amidala"""
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import queue
import threading
import time
import traceback
from logger import save_report
from safety_rules import (
    MIN_PRESENCE_CURRENT_MA,
    validate_acw_profile,
    validate_pass_evidence,
)


class TestScreen:

    def __init__(self, parent, config, serial, model_name, app_ref=None):
        self.parent     = parent
        self.config     = config
        self.serial     = serial
        self.model_name = model_name
        self.app_ref    = app_ref
        self.operator   = "OPERATOR"
        # Profil jest zamrozony dla calej sesji ekranu testowego. Zmiana ustawien
        # w panelu nie moze zmienic progow w trakcie aktywnego cyklu.
        self.test_profile = validate_acw_profile(dict(config.TEST_PROFILE))

        self.device       = None
        self.test_running = False
        self._result_pending = False
        self.test_thread  = None
        self.start_time   = None
        self._device_configured = False
        self._test_aborted = False
        self._cycle_active_seen = False
        self._cycle_load_seen = False
        self._cycle_max_voltage = 0.0
        self._cycle_max_current_ma = 0.0
        self._cycle_in_range_samples = 0
        self._cycle_overcurrent_seen = False
        self._cycle_terminal_seen = False
        self._run_id = 0

        self._closed = False
        self._ui_queue: queue.Queue = queue.Queue()
        self._ui_poll_after_id = None
        self._next_dialog_after_id = None
        self._report_threads: list[threading.Thread] = []

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

        # Pierwszy SN został już zwalidowany pod kątem długości i mapy HWID.
        self._serial_ready_for_test = True

        self.sn_dialog       = None
        self.sn_entry        = None
        self.sn_result_label = None
        self.sn_status_lbl   = None

        self._recent_results          = []
        self._history_frame           = None

    # ------------------------------------------------------------------ #
    # SHOW                                                                 #
    # ------------------------------------------------------------------ #
    def show(self):
        if self.app_ref is not None:
            self.app_ref.current_test_screen = self
        self._start_ui_poll()
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


    def _start_ui_poll(self):
        if self._closed:
            return
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                if not self._closed:
                    try:
                        callback()
                    except tk.TclError:
                        if not self._closed:
                            print("[UI] Callback pominiety po zamknieciu okna")
                    except Exception as exc:
                        print(f"[UI] Krytyczny blad callbacku: {exc}")
                        traceback.print_exc()
                        try:
                            if self.device:
                                self.device.stop_test()
                        except Exception:
                            pass
                        self._test_error(
                            f"Wewnetrzny blad interfejsu: {exc}"
                        )
        except queue.Empty:
            pass
        if not self._closed:
            self._ui_poll_after_id = self.parent.after(25, self._start_ui_poll)

    def _post_ui(self, callback):
        if not self._closed:
            self._ui_queue.put(callback)

    def shutdown(self):
        """Fail-safe zamkniecie ekranu: STOP, rozlaczenie i anulowanie callbackow."""
        if self._closed:
            return
        self._closed = True
        self._test_aborted = True
        self.test_running = False
        self._result_pending = False
        self._run_id += 1

        for after_id in (self._ui_poll_after_id, self._next_dialog_after_id):
            if after_id:
                try:
                    self.parent.after_cancel(after_id)
                except Exception:
                    pass
        self._ui_poll_after_id = None
        self._next_dialog_after_id = None

        if self.sn_dialog and self.sn_dialog.winfo_exists():
            try:
                self.sn_dialog.grab_release()
            except Exception:
                pass
            self.sn_dialog.destroy()
            self.sn_dialog = None

        try:
            if self.device:
                self.device.stop_test()
        except Exception:
            pass
        try:
            if self.interlock:
                self.interlock.disconnect()
        except Exception:
            pass
        try:
            if self.device:
                self.device.disconnect(send_stop=False)
        except Exception:
            pass

        # Daj zapisom raportu lacznie maksymalnie sekunde na zakonczenie.
        self._report_threads = [t for t in self._report_threads if t.is_alive()]
        join_deadline = time.monotonic() + 1.0
        for thread in self._report_threads:
            remaining = join_deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)

        if self.app_ref is not None and self.app_ref.current_test_screen is self:
            self.app_ref.current_test_screen = None

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
        tk.Label(footer, text=f"Wersja {self.config.APP_VERSION} — audyt bezpieczeństwa",
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 9, "bold")).pack(
                     side=tk.LEFT, padx=20, pady=10)
        tk.Label(footer, text="Autor: Kacper Urbanowicz",
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 10, "bold")).pack(
                     side=tk.RIGHT, padx=20, pady=10)

    def _go_back(self):
        if self.test_running or self._result_pending:
            messagebox.showwarning(
                "Cykl w toku",
                "Nie można wrócić do menu podczas testu ani finalizacji wyniku.\n"
                "Poczekaj na wyświetlenie wyniku lub zatrzymaj aktywny test.")
            return
        self._cleanup_and_go_back()

    def _cleanup_and_go_back(self):
        self.shutdown()
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
        p = self.test_profile

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
        presence_min = float(p.get('presence_min_current', MIN_PRESENCE_CURRENT_MA))
        effective_low = max(float(p['limit_low']), presence_min)
        lbl(0, 0, "Napięcie:",     f"{p['voltage'] / 1000:.2f} kV")
        lbl(0, 2, "Tryb:",         p['type'])
        lbl(1, 0, "Limit Chromy:", f"{effective_low:.3f} – {p['limit_high']:.3f} mA")
        lbl(1, 2, "Min. spec.:",   f"{p['limit_low']:.3f} mA")
        lbl(2, 0, "Próg obecności:", f"{presence_min:.3f} mA")
        lbl(2, 2, "Czas całk.:",   f"{total:.1f} s")
        lbl(3, 0, "Ramp up:",      f"{p['ramp_time']:.1f} s")
        lbl(3, 2, "Dwell:",        f"{p['dwell']:.1f} s")
        lbl(4, 0, "Ramp down:",    f"{p['ramp_dn']:.1f} s")
        lbl(4, 2, "Częstotliw.:",  f"{p['frequency']} Hz (ust. Chroma)")
        lbl(5, 0, "Arc Sense:",    f"{p['arc_sense']} (ust. Chroma)")
        lbl(5, 2, "Continuity:",   f"{p['continuity']} (ust. Chroma)")

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
                text="⛔ Interlock programowy wyłączony — test zablokowany",
                fg=self.config.COLOR_ERROR, bg="#ffebee")
            self.interlock_frame.config(bg="#ffebee")
            self.start_button.config(state="disabled")
            return

        port = getattr(self.config, "INTERLOCK_PORT", None)
        if not port:
            self.interlock_label.config(
                text="⛔ Brak portu Arduino — test zablokowany",
                fg=self.config.COLOR_ERROR, bg="#ffebee")
            self.interlock_frame.config(bg="#ffebee")
            self.start_button.config(state="disabled")
            return

        from interlock import InterlockMonitor
        baud = getattr(self.config, "INTERLOCK_BAUDRATE", 9600)
        self.interlock = InterlockMonitor(
            port=port,
            baudrate=baud,
            heartbeat_timeout=2.0,
        )

        if self.interlock.connect():
            self.interlock.set_on_change(self._on_interlock_change)
            self.interlock.start_monitoring()
            self.interlock_label.config(
                text="⏳ Oczekiwanie na aktualny stan klapy...",
                fg="#FF9800", bg="#fff8e1")
            self.start_button.config(state="disabled")
        else:
            self.interlock_label.config(
                text=f"⛔ Brak komunikacji z Arduino ({port}) — test zablokowany",
                fg=self.config.COLOR_ERROR, bg="#ffebee")
            self.interlock_frame.config(bg="#ffebee")
            self.start_button.config(state="disabled")

    def _on_interlock_change(self, closed):
        self._post_ui(lambda: self._apply_interlock_state(closed))

    def _interlock_enforced(self) -> bool:
        """True, gdy konfiguracja wymaga programowego interlocka."""
        return bool(getattr(self.config, "INTERLOCK_ENABLED", True))

    def _interlock_ready(self) -> bool:
        """True wyłącznie przy aktywnym połączeniu i znanym stanie klapy."""
        return bool(
            self._interlock_enforced()
            and self.interlock
            and self.interlock.connected
            and self._current_interlock_closed is not None
        )

    def _attempt_safe_start(self) -> bool:
        """Jedyna bramka automatycznego startu testu."""
        if self.test_running or self._result_pending or self._test_aborted:
            return False
        if not self.device or not self.device.connected:
            self.status_label.config(
                text="⛔ Start zablokowany — brak połączenia z Chroma",
                fg=self.config.COLOR_ERROR)
            return False
        if not self._device_configured:
            self.status_label.config(
                text="⛔ Start zablokowany — Chroma nie jest poprawnie skonfigurowana",
                fg=self.config.COLOR_ERROR)
            return False
        if not self._serial_ready_for_test:
            return False

        if self._interlock_enforced():
            if not self._interlock_ready():
                self.status_label.config(
                    text="⛔ Start zablokowany — brak aktualnego sygnału interlocka",
                    fg=self.config.COLOR_ERROR)
                return False
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

        self.start_button.config(state="disabled")
        self.status_label.config(
            text="⛔ Start zablokowany — interlock programowy musi być aktywny",
            fg=self.config.COLOR_ERROR)
        return False

    def _apply_interlock_state(self, closed):
        self._current_interlock_closed = closed

        if closed is None:
            self._valid_close_transition = False
            self._lid_open_seen = False
            self.start_button.config(state="disabled")
            self.interlock_label.config(
                text="⛔ Utracono komunikację z Arduino — test zablokowany",
                fg=self.config.COLOR_ERROR, bg="#ffebee")
            self.interlock_frame.config(bg="#ffebee")

            if self.test_running:
                self._test_aborted = True
                self.test_running = False
                self._device_configured = False
                self._serial_ready_for_test = False
                if self.device:
                    self.device.stop_test()
                self.stop_button.config(state="disabled")
                self.back_button.config(state="normal")
                self.status_label.config(
                    text="⛔ Test przerwany — utrata komunikacji z interlockiem",
                    fg=self.config.COLOR_ERROR)
                messagebox.showerror(
                    "Utrata interlocka",
                    "Utracono komunikację z Arduino podczas testu.\n"
                    "Test został zatrzymany i kolejne uruchomienie jest zablokowane.",
                    parent=self.parent)
            return

        if closed:
            # Sam stan CLOSED nie wystarcza. Akceptujemy tylko OPEN -> CLOSED.
            if self._prev_interlock_closed is not False or not self._lid_open_seen:
                self._valid_close_transition = False
                self.interlock_label.config(
                    text="🔒 Klapa ZAMKNIĘTA — przed nowym testem otwórz ją i zamknij ponownie",
                    fg="#FF9800", bg="#fff8e1")
                self.interlock_frame.config(bg="#fff8e1")
                self.start_button.config(state="disabled")
                self._prev_interlock_closed = True
                return

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

        # OPEN uzbraja dokładnie jedno następne zamknięcie.
        self._lid_open_seen = True
        self._valid_close_transition = False
        self._prev_interlock_closed = False
        self.interlock_label.config(
            text="🔓 Klapa OTWARTA — włóż urządzenie, zeskanuj SN i zamknij klapę",
            fg=self.config.COLOR_ERROR, bg="#ffebee")
        self.interlock_frame.config(bg="#ffebee")

        if self.test_running:
            if self._cycle_terminal_seen:
                # Tester zakonczyl juz generowanie HV. Nie kasujemy poprawnego
                # wyniku tylko dlatego, ze operator szybko otworzyl klape.
                self.start_button.config(state="disabled")
                self.stop_button.config(state="disabled")
                self.status_label.config(
                    text="⏳ Test zakończony — finalizuję świeży wynik...",
                    fg="#FF9800")
                return

            self._test_aborted = True
            self.test_running = False
            self._device_configured = False
            self._serial_ready_for_test = False
            if self.device:
                self.device.stop_test()
            self.start_button.config(state="disabled")
            self.stop_button.config(state="disabled")
            self.back_button.config(state="normal")
            self.status_label.config(
                text="⛔ Test przerwany — klapa została otwarta!",
                fg=self.config.COLOR_ERROR)
            messagebox.showwarning(
                "Test przerwany",
                "Klapa została otwarta podczas testu!\n"
                "Test został automatycznie zatrzymany.\n\n"
                "Wróć do menu, aby ponownie połączyć i skonfigurować tester.",
                parent=self.parent)
        else:
            self.start_button.config(state="disabled")

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
            for text, width, fg in [
                (entry["time"],   8,  "#666666"),
                (entry["serial"], 22, "#333333"),
                (entry["model"],  16, "#333333"),
                (entry["result"], 7,  result_fg),
            ]:
                tk.Label(row, text=text, bg=bg, fg=fg,
                         font=("Arial", 8), width=width,
                         anchor="center", pady=2).pack(side=tk.LEFT)

    def _add_recent_result(self, serial, model, result):
        self._recent_results.append({
            "time":   datetime.now().strftime("%H:%M:%S"),
            "serial": serial,
            "model":  model,
            "result": result,
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
                baudrate=self.config.DEFAULT_BAUDRATE,
                parity=self.config.DEFAULT_PARITY,
                flow_control=self.config.DEFAULT_FLOW_CONTROL,
            )
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
        self._device_configured = False
        self.start_button.config(state="disabled")
        try:
            self.device.clear_steps()
            self.device.configure_acw(self.test_profile)
            self._device_configured = True
            self.status_label.config(
                text="✓ Urządzenie skonfigurowane i gotowe",
                fg=self.config.COLOR_ACCENT)
            self._attempt_safe_start()
        except Exception as e:
            self._device_configured = False
            self.status_label.config(
                text=f"⛔ Błąd konfiguracji — test zablokowany: {e}",
                fg=self.config.COLOR_ERROR)
            self.start_button.config(state="disabled")

    def _start_test(self):
        if self._closed or self.test_running or self._result_pending or self._test_aborted:
            return

        # Ostatnia linia obrony — obowiązuje także w trybie ręcznym.
        if not self.device or not self.device.connected:
            self.status_label.config(
                text="⛔ Start zablokowany — brak połączenia z Chroma",
                fg=self.config.COLOR_ERROR)
            return
        if not self._device_configured:
            self.status_label.config(
                text="⛔ Start zablokowany — brak potwierdzonej konfiguracji Chromy",
                fg=self.config.COLOR_ERROR)
            return
        if not self._serial_ready_for_test:
            self.status_label.config(
                text="⛔ Start zablokowany — brak zatwierdzonego SN",
                fg=self.config.COLOR_ERROR)
            return

        if not self._interlock_enforced():
            self.status_label.config(
                text="⛔ Start zablokowany — interlock programowy jest wyłączony",
                fg=self.config.COLOR_ERROR)
            return
        if not self._interlock_ready():
            self.status_label.config(
                text="⛔ Start zablokowany — brak aktualnego sygnału interlocka",
                fg=self.config.COLOR_ERROR)
            return
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
        self._valid_close_transition = False

        self._test_completed_called = False
        self._test_aborted = False
        self._result_pending = False
        self._cycle_active_seen = False
        self._cycle_load_seen = False
        self._cycle_max_voltage = 0.0
        self._cycle_max_current_ma = 0.0
        self._cycle_in_range_samples = 0
        self._cycle_overcurrent_seen = False
        self._cycle_terminal_seen = False
        self._run_id += 1
        run_id = self._run_id
        self.test_running = True
        self.start_time = time.monotonic()

        self.sn_display_label.config(text=self.serial)
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.back_button.config(state="disabled")
        self.next_sn_button.config(state="disabled")
        self.status_label.config(
            text="🔄 Uruchamianie nowego cyklu Hi-Pot...", fg="#FF9800"
        )

        self.test_thread = threading.Thread(
            target=self._run_test_background, args=(run_id,), daemon=True)
        self.test_thread.start()

    def _run_test_background(self, run_id):
        try:
            if not self.device.start_test():
                raise RuntimeError(
                    "Chroma nie potwierdziła rozpoczęcia NOWEGO cyklu testowego. "
                    "Wynik LAST nie został użyty."
                )

            # start_test() potwierdził aktywny stan lub świeże narastanie napięcia.
            self._cycle_active_seen = True

            profile = self.test_profile
            target_voltage = float(profile["voltage"])
            low_limit_ma = float(profile["limit_low"])
            presence_min_ma = float(profile.get("presence_min_current", MIN_PRESENCE_CURRENT_MA))
            effective_low_ma = max(low_limit_ma, presence_min_ma)
            high_limit_ma = float(profile["limit_high"])
            print(
                f"[LOAD] Próg obecności: {presence_min_ma:.3f} mA | "
                f"efektywny LOW: {effective_low_ma:.3f} mA"
            )
            total_time = (
                float(profile["ramp_time"])
                + float(profile["dwell"])
                + float(profile["ramp_dn"])
            )
            # Wynik zakończony dużo wcześniej niż profil jest podejrzany/stary.
            minimum_runtime = max(2.0, total_time - 0.75)
            configured_timeout = max(1.0, float(getattr(self.config, "TEST_TIMEOUT", 300)))
            max_runtime = min(configured_timeout, max(total_time + 10.0, 15.0))
            consecutive_comm_errors = 0
            terminal_status = None

            while (
                self.test_running
                and not self._test_aborted
                and not self._closed
                and run_id == self._run_id
            ):
                elapsed = time.monotonic() - self.start_time
                status = self.device.get_status()

                if status == "COMM_ERROR":
                    consecutive_comm_errors += 1
                    if consecutive_comm_errors >= 3:
                        raise RuntimeError(
                            "Utracono komunikację z Chroma podczas testu"
                        )
                    time.sleep(0.15)
                    continue

                consecutive_comm_errors = 0
                if status in ("TESTING", "RUNNING"):
                    self._cycle_active_seen = True

                measurements = self.device.read_measurements()
                if measurements:
                    voltage = float(measurements["output_voltage"])
                    current_ma = float(measurements["measure_current"]) * 1000.0
                    self.current_voltage = voltage
                    self.current_current = current_ma
                    self._cycle_max_voltage = max(self._cycle_max_voltage, voltage)
                    self._cycle_max_current_ma = max(
                        self._cycle_max_current_ma, current_ma
                    )

                    if voltage >= 50.0:
                        self._cycle_active_seen = True
                    # Potwierdzenie obciążenia musi pochodzić z pomiaru NA ŻYWO,
                    # nie z rejestru LAST poprzedniego urządzenia.
                    if voltage >= target_voltage * 0.90:
                        if effective_low_ma <= current_ma <= high_limit_ma:
                            self._cycle_in_range_samples += 1
                            self._cycle_load_seen = True
                        elif current_ma > high_limit_ma:
                            self._cycle_overcurrent_seen = True

                    if 0 < voltage < 1e6:
                        self.last_valid_voltage = voltage
                    if 0 < current_ma < 9999:
                        self.last_valid_current = current_ma

                self.elapsed_time = elapsed
                self._post_ui(self._update_display)

                if status in ("STOPPED", "STOP", "PASS", "FAIL"):
                    terminal_status = status
                    self._cycle_terminal_seen = True
                    if not self._cycle_active_seen:
                        raise RuntimeError(
                            "Odebrano wynik bez potwierdzenia aktywnego cyklu — "
                            "możliwy stary wynik LAST"
                        )
                    # Wczesny FAIL jest prawidlowym wynikiem ochronnym (np. ARC
                    # lub przekroczenie pradu). Minimalny czas sprawdzamy dopiero
                    # po odczycie wyniku i odrzucamy wylacznie podejrzanie szybki PASS.
                    break

                if elapsed > max_runtime:
                    raise TimeoutError(
                        f"Przekroczono maksymalny czas testu ({max_runtime:.1f} s)"
                    )
                time.sleep(0.10)

            if (
                self._test_aborted
                or not self.test_running
                or self._closed
                or run_id != self._run_id
            ):
                return
            if terminal_status is None:
                raise RuntimeError("Brak jednoznacznego zakończenia bieżącego cyklu")

            result, data = self.device.get_test_result()
            if result not in ("PASS", "FAIL"):
                raise RuntimeError(
                    "Nie udało się pobrać jednoznacznego, świeżego wyniku testu"
                )
            if not data.get("fresh_cycle"):
                raise RuntimeError("Wynik nie został przypisany do bieżącego cyklu")
            if result == "PASS" and elapsed < minimum_runtime:
                raise RuntimeError(
                    f"PASS pojawił się zbyt szybko ({elapsed:.1f} s; "
                    f"minimum {minimum_runtime:.1f} s) — wynik odrzucony"
                )

            final_voltage = float(data.get("output_voltage") or 0.0)
            final_current_ma = float(data.get("measured_current") or 0.0)
            validate_pass_evidence(
                result=result,
                terminal_status=terminal_status,
                target_voltage=target_voltage,
                effective_low_ma=effective_low_ma,
                high_limit_ma=high_limit_ma,
                final_voltage=final_voltage,
                final_current_ma=final_current_ma,
                cycle_max_voltage=self._cycle_max_voltage,
                in_range_samples=self._cycle_in_range_samples,
                overcurrent_seen=self._cycle_overcurrent_seen,
            )

            # Wynik jest juz zweryfikowany. Otwarcie klapy po tym punkcie nie moze
            # zmienic zakonczonego cyklu w falszywe "przerwano test".
            self._result_pending = True
            self.test_running = False
            self._post_ui(lambda r=result, d=data: self._test_completed(r, d))

        except Exception as exc:
            if self._test_aborted or self._closed or run_id != self._run_id:
                return
            try:
                self.device.stop_test()
            except Exception:
                pass
            self._post_ui(lambda msg=str(exc): self._test_error(msg))

    def _update_display(self):
        self.voltage_label.config(text=f"{int(self.current_voltage)} V")
        self.current_label.config(text=f"{self.current_current:.2f} mA")
        self.time_label.config(text=f"{self.elapsed_time:.1f} s")

        p          = self.test_profile
        total_time = p['ramp_time'] + p['dwell'] + p['ramp_dn']
        progress   = min(self.elapsed_time / total_time, 1.0) \
                     if total_time > 0 else 0
        cw = self.progress_canvas.winfo_width()
        self.progress_canvas.coords(
            self.progress_rect, 0, 0, cw * progress, 30)

    def _test_completed(self, result, data):
        if self._test_completed_called or self._test_aborted or self._closed:
            self._result_pending = False
            return
        self._test_completed_called = True
        self.test_running = False
        self._result_pending = False

        # Każdy następny test wymaga nowego SN i nowego OPEN -> CLOSED.
        self._serial_ready_for_test = False
        self._valid_close_transition = False
        # Gdy operator zdazyl juz otworzyc klape po fizycznym zakonczeniu HV,
        # zachowujemy to OPEN. Nie wymagamy bezsensownego drugiego otwarcia.
        self._lid_open_seen = self._current_interlock_closed is False
        if self._lid_open_seen:
            self._prev_interlock_closed = False

        self.test_result = result
        self.start_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.back_button.config(state="normal")
        self.next_sn_button.config(state="normal")

        lid_instruction = (
            "zeskanuj następny SN i zamknij klapę"
            if self._current_interlock_closed is False
            else "otwórz klapę"
        )
        if result == "PASS":
            self.status_label.config(
                text=f"✓ TEST ZALICZONY (PASS) — {lid_instruction}",
                fg=self.config.COLOR_ACCENT)
        else:
            self.status_label.config(
                text=f"✗ TEST NIEZALICZONY (FAIL) — {lid_instruction}",
                fg=self.config.COLOR_ERROR)

        overflow = 9.0e37
        try:
            raw_v = float(data.get("output_voltage") or 0)
            raw_mi = float(data.get("measured_current") or 0)
        except (TypeError, ValueError):
            raw_v, raw_mi = 0.0, 0.0

        vtm_val = (
            raw_v / 1000.0
            if 0 < raw_v < overflow
            else self.last_valid_voltage / 1000.0
        )
        im_val = (
            raw_mi if 0 < raw_mi < 9999 else self.last_valid_current
        )
        error_code = str(data.get("error_code", ""))

        # Kopie wartości chronią zapis przed zmianą SN w kolejnym cyklu.
        report_args = {
            "operator": self.operator,
            "program": self.model_name,
            "serial": self.serial,
            "vtm": vtm_val,
            "im": im_val,
            "result": result,
            "error_code": error_code,
            "low_limit": max(
                float(self.test_profile.get("limit_low", 0.05)),
                float(self.test_profile.get("presence_min_current", MIN_PRESENCE_CURRENT_MA)),
            ),
            "high_limit": float(self.test_profile.get("limit_high", 2.5)),
            "log_dir": self.config.LOG_DIR,
        }
        if getattr(self.config, "AUTO_SAVE_RESULTS", True):
            self._report_threads = [
                thread for thread in self._report_threads if thread.is_alive()
            ]
            report_thread = threading.Thread(
                target=self._save_report_background,
                args=(report_args,),
                daemon=True,
            )
            self._report_threads.append(report_thread)
            report_thread.start()

        self._add_recent_result(
            serial=self.serial,
            model=self.model_name,
            result=result,
        )

        if self._interlock_enforced():
            if self._current_interlock_closed is False:
                text = "🔓 Test zakończony — zeskanuj następny SN i zamknij klapę"
                fg, bg = self.config.COLOR_ERROR, "#ffebee"
            else:
                text = "🔒 Test zakończony — otwórz klapę przed następnym testem"
                fg, bg = "#FF9800", "#fff8e1"
            self.interlock_label.config(text=text, fg=fg, bg=bg)
            self.interlock_frame.config(bg=bg)

        # Okno następnego SN pojawia się praktycznie natychmiast.
        self._next_dialog_after_id = self.parent.after(
            300, lambda: None if self._closed else self._show_next_sn_dialog(result)
        )

    def _save_report_background(self, report_args):
        try:
            save_report(**report_args)
        except Exception as exc:
            print(f"[LOG] Błąd zapisu raportu: {exc}")
            self._post_ui(
                lambda error=str(exc): messagebox.showerror(
                    "Błąd zapisu raportu",
                    f"Nie udało się zapisać raportu ani kopii awaryjnej:\n{error}",
                    parent=self.parent,
                )
            )

    def _test_error(self, msg):
        if self._closed:
            return
        self._test_aborted = True
        self.test_running = False
        self._result_pending = False
        self._device_configured = False
        self._serial_ready_for_test = False
        self._valid_close_transition = False
        self._cycle_terminal_seen = False

        try:
            if self.device:
                self.device.disconnect()
        except Exception:
            pass

        self.start_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.back_button.config(state="normal")
        self.next_sn_button.config(state="disabled")
        self.status_label.config(
            text=f"⛔ Błąd testu — dalsze testy zablokowane: {msg}",
            fg=self.config.COLOR_ERROR)
        messagebox.showerror(
            "Błąd testu Hi-Pot",
            f"{msg}\n\nDalsze testy zostały zablokowane. "
            "Wróć do menu i połącz urządzenie ponownie.",
            parent=self.parent)

    def _stop_test(self):
        if self._closed:
            return
        if self._result_pending:
            self.status_label.config(
                text="⏳ Wynik jest finalizowany — STOP nie jest już wymagany",
                fg="#FF9800",
            )
            return
        self._test_aborted = True
        self.test_running = False
        self._device_configured = False
        self._serial_ready_for_test = False
        self._valid_close_transition = False
        self._cycle_terminal_seen = False
        if self.device:
            self.device.stop_test()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.back_button.config(state="normal")
        self.next_sn_button.config(state="disabled")
        self.status_label.config(
            text="⚠ Test przerwany przez użytkownika — wymagany nowy cykl",
            fg="#FF9800")


    def _open_sn_dialog_manually(self):
        if self.sn_dialog and self.sn_dialog.winfo_exists():
            self.sn_dialog.lift()
            self.sn_dialog.focus()
            return
        self._show_next_sn_dialog(self.test_result or "BRAK")

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
        dialog.protocol("WM_DELETE_WINDOW", self._back_from_dialog)
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

        self._attempt_safe_start()

    def _apply_new_serial(self, new_serial: str, model_name: str):
        """Wspólna logika resetu stanu po podaniu nowego SN."""
        self.serial = new_serial
        self.model_name = model_name
        self._test_aborted = False
        self._cycle_active_seen = False
        self._cycle_load_seen = False
        self._cycle_max_voltage = 0.0
        self._cycle_max_current_ma = 0.0
        self._cycle_in_range_samples = 0
        self._cycle_overcurrent_seen = False
        self._cycle_terminal_seen = False

        self._serial_ready_for_test = True
        self.start_button.config(state="disabled")
        self.next_sn_button.config(state="disabled")

        self.sn_display_label.config(text=self.serial)
        self.test_result = None
        self.elapsed_time = 0.0
        self.current_voltage = 0.0
        self.current_current = 0.0
        self.last_valid_voltage = 0.0
        self.last_valid_current = 0.0
        self.voltage_label.config(text="0 V")
        self.current_label.config(text="0.00 mA")
        self.time_label.config(text="0.0 s")
        self.progress_canvas.coords(self.progress_rect, 0, 0, 0, 30)

        if self._interlock_enforced():
            if not self._interlock_ready():
                message = "SN zaakceptowany — oczekiwanie na interlock"
            elif self._current_interlock_closed is True and not self._valid_close_transition:
                message = "SN zaakceptowany — otwórz klapę i zamknij ją ponownie"
            elif self._current_interlock_closed is False:
                message = "SN zaakceptowany — zamknij klapę po włożeniu urządzenia"
            else:
                message = "SN zaakceptowany — gotowy do uruchomienia"
            self.status_label.config(text=message, fg="#FF9800")
        else:
            self.status_label.config(
                text="SN zaakceptowany — naciśnij START TEST", fg="#FF9800")


    def _back_from_dialog(self):
        if self.sn_dialog and self.sn_dialog.winfo_exists():
            self.sn_dialog.grab_release()
            self.sn_dialog.destroy()
            self.sn_dialog = None
        self._cleanup_and_go_back()