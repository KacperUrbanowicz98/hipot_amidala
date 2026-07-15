# admin_panel.py
"""Panel konfiguracji aplikacji Hi-Pot Amidala"""
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from settings_manager import SettingsManager


class AdminPanel:

    def __init__(self, parent, config):
        self.parent   = parent
        self.config   = config
        self.settings = SettingsManager()
        self.window   = None

    # ------------------------------------------------------------------ #
    # SHOW                                                                 #
    # ------------------------------------------------------------------ #
    def show(self):
        self.window = tk.Toplevel(self.parent)
        self.window.title("Panel konfiguracji — Amidala")
        self.window.geometry("860x680")
        self.window.configure(bg=self.config.COLOR_BG)
        self.window.resizable(True, True)
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.update_idletasks()
        x = self.parent.winfo_screenwidth()  // 2 - 430
        y = self.parent.winfo_screenheight() // 2 - 340
        self.window.geometry(f"860x680+{x}+{y}")

        self._create_header()

        main_frame = tk.Frame(self.window, bg=self.config.COLOR_BG)
        main_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=(8, 0))

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(expand=True, fill=tk.BOTH)

        self._create_rs232_tab()
        self._create_interlock_tab()
        self._create_hwid_tab()
        self._create_profile_tab()
        self._create_logs_tab()

        self._create_footer()

    # ------------------------------------------------------------------ #
    # HEADER / FOOTER                                                      #
    # ------------------------------------------------------------------ #
    def _create_header(self):
        hdr = tk.Frame(self.window, bg=self.config.COLOR_PRIMARY, height=55)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Panel konfiguracji",
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 17, "bold")).pack(side=tk.LEFT, padx=20)
        tk.Button(hdr, text="Zamknij",
                  bg=self.config.COLOR_ERROR, fg=self.config.COLOR_WHITE,
                  font=("Arial", 10, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self.window.destroy).pack(
                      side=tk.RIGHT, padx=15, pady=12)

    def _create_footer(self):
        footer = tk.Frame(self.window, bg=self.config.COLOR_PRIMARY, height=35)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)
        tk.Label(footer, text="Autor: Kacper Urbanowicz",
                 bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                 font=("Arial", 9)).pack(side=tk.RIGHT, padx=15, pady=8)

    # ------------------------------------------------------------------ #
    # HELPER                                                               #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _center(win, w, h):
        win.update_idletasks()
        x = win.winfo_screenwidth()  // 2 - w // 2
        y = win.winfo_screenheight() // 2 - h // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    # ================================================================== #
    # ZAKŁADKA 1 — RS232                                                  #
    # ================================================================== #
    def _create_rs232_tab(self):
        frame = tk.Frame(self.notebook, bg=self.config.COLOR_WHITE)
        self.notebook.add(frame, text="  RS232  ")

        tk.Label(frame, text="Konfiguracja RS232 — Chroma Hi-Pot",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 13, "bold")).pack(pady=(18, 10))

        form = tk.Frame(frame, bg=self.config.COLOR_WHITE,
                        relief=tk.RAISED, borderwidth=2)
        form.pack(padx=35, pady=(0, 10), fill=tk.X)

        inner = tk.Frame(form, bg=self.config.COLOR_WHITE)
        inner.pack(padx=25, pady=18)

        def row(r, label, var, values=None):
            tk.Label(inner, text=label,
                     bg=self.config.COLOR_WHITE, fg="#444444",
                     font=("Arial", 11), width=22, anchor="w").grid(
                         row=r, column=0, sticky="w", padx=(0, 12), pady=7)
            if values:
                cb = ttk.Combobox(inner, textvariable=var, values=values,
                                  state="readonly", font=("Arial", 11), width=18)
                cb.grid(row=r, column=1, sticky="w", pady=7)
            else:
                tk.Entry(inner, textvariable=var, font=("Arial", 11), width=20,
                         relief=tk.SOLID, borderwidth=1).grid(
                             row=r, column=1, sticky="w", pady=7)

        self.com_port_var  = tk.StringVar(value=self.config.DEFAULT_COM_PORT)
        self.baudrate_var  = tk.StringVar(value=str(self.config.DEFAULT_BAUDRATE))
        self.parity_var    = tk.StringVar(value=self.config.DEFAULT_PARITY)
        self.flow_ctrl_var = tk.StringVar(value=self.config.DEFAULT_FLOW_CONTROL)

        row(0, "Port COM:",     self.com_port_var)
        row(1, "Baudrate:",     self.baudrate_var,
            ["1200","2400","4800","9600","19200","38400","57600","115200"])
        row(2, "Parity:",       self.parity_var,   ["NONE","ODD","EVEN"])
        row(3, "Flow Control:", self.flow_ctrl_var, ["NONE","RTS/CTS","XON/XOFF"])

        self.rs232_status = tk.Label(
            frame, text="", bg=self.config.COLOR_WHITE, font=("Arial", 10))
        self.rs232_status.pack(pady=(0, 4))

        btn_row = tk.Frame(frame, bg=self.config.COLOR_WHITE)
        btn_row.pack(pady=6)

        tk.Button(btn_row, text="Zapisz ustawienia RS232",
                  bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=22, height=2,
                  command=self._save_rs232).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(btn_row, text="Test połączenia Hi-Pot",
                  bg="#607D8B", fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=22, height=2,
                  command=self._test_rs232).pack(side=tk.LEFT)

        self.rs232_test_result = tk.Label(
            frame, text="", bg=self.config.COLOR_WHITE, font=("Arial", 10))
        self.rs232_test_result.pack(pady=4)

    def _save_rs232(self):
        self.config.DEFAULT_COM_PORT     = self.com_port_var.get().strip()
        self.config.DEFAULT_BAUDRATE     = int(self.baudrate_var.get())
        self.config.DEFAULT_PARITY       = self.parity_var.get()
        self.config.DEFAULT_FLOW_CONTROL = self.flow_ctrl_var.get()
        self.settings.save_config(self.config)
        self.rs232_status.config(
            text="✓ Zapisano — zmiany aktywne od następnego połączenia",
            fg=self.config.COLOR_ACCENT)

    def _test_rs232(self):
        import threading
        self.rs232_test_result.config(text="⏳ Łączenie...", fg="#FF9800")

        def do_test():
            try:
                from hipot_device import ChromaHiPotDevice
                port = self.com_port_var.get().strip()
                baud = int(self.baudrate_var.get())
                dev  = ChromaHiPotDevice(port=port, baudrate=baud)
                ok   = dev.connect()
                if ok:
                    dev.disconnect()
                    self.window.after(0, lambda: self.rs232_test_result.config(
                        text=f"✓ Połączono z Hi-Pot na {port}",
                        fg=self.config.COLOR_ACCENT))
                else:
                    self.window.after(0, lambda: self.rs232_test_result.config(
                        text=f"✗ Brak odpowiedzi na {port}",
                        fg=self.config.COLOR_ERROR))
            except Exception as e:
                self.window.after(0, lambda: self.rs232_test_result.config(
                    text=f"✗ Błąd: {e}", fg=self.config.COLOR_ERROR))

        threading.Thread(target=do_test, daemon=True).start()

    # ================================================================== #
    # ZAKŁADKA 2 — INTERLOCK                                              #
    # ================================================================== #
    def _create_interlock_tab(self):
        frame = tk.Frame(self.notebook, bg=self.config.COLOR_WHITE)
        self.notebook.add(frame, text="  Interlock  ")

        tk.Label(frame, text="Konfiguracja Hardware Interlock — Arduino",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 13, "bold")).pack(pady=(18, 4))

        tk.Label(frame,
                 text="Arduino monitoruje stan klapy (pin 6 → GND).\n"
                      "Zamknięcie klapy startuje test automatycznie.",
                 bg=self.config.COLOR_WHITE, fg="#666666",
                 font=("Arial", 9, "italic"), justify="center").pack(pady=(0, 12))

        form = tk.Frame(frame, bg=self.config.COLOR_WHITE,
                        relief=tk.RAISED, borderwidth=2)
        form.pack(padx=35, pady=(0, 10), fill=tk.X)

        inner = tk.Frame(form, bg=self.config.COLOR_WHITE)
        inner.pack(padx=25, pady=18)

        self.interlock_port_var    = tk.StringVar(
            value=getattr(self.config, "INTERLOCK_PORT", "COM5"))
        self.interlock_baud_var    = tk.StringVar(
            value=str(getattr(self.config, "INTERLOCK_BAUDRATE", 9600)))
        self.interlock_enabled_var = tk.BooleanVar(
            value=getattr(self.config, "INTERLOCK_ENABLED", True))

        def row(r, label, var, values=None):
            tk.Label(inner, text=label,
                     bg=self.config.COLOR_WHITE, fg="#444444",
                     font=("Arial", 11), width=22, anchor="w").grid(
                         row=r, column=0, sticky="w", padx=(0, 12), pady=7)
            if values:
                cb = ttk.Combobox(inner, textvariable=var, values=values,
                                  state="readonly", font=("Arial", 11), width=18)
                cb.grid(row=r, column=1, sticky="w", pady=7)
            else:
                tk.Entry(inner, textvariable=var, font=("Arial", 11), width=20,
                         relief=tk.SOLID, borderwidth=1).grid(
                             row=r, column=1, sticky="w", pady=7)

        row(0, "Port COM Arduino:", self.interlock_port_var)
        row(1, "Baudrate:",         self.interlock_baud_var,
            ["4800","9600","19200","38400","57600","115200"])

        tk.Label(inner, text="Interlock aktywny:",
                 bg=self.config.COLOR_WHITE, fg="#444444",
                 font=("Arial", 11), width=22, anchor="w").grid(
                     row=2, column=0, sticky="w", padx=(0, 12), pady=7)
        tk.Checkbutton(inner, variable=self.interlock_enabled_var,
                       bg=self.config.COLOR_WHITE,
                       activebackground=self.config.COLOR_WHITE,
                       cursor="hand2").grid(row=2, column=1, sticky="w", pady=7)

        tk.Label(inner,
                 text="(odznacz aby używać przycisku START ręcznie)",
                 bg=self.config.COLOR_WHITE, fg="#999999",
                 font=("Arial", 8, "italic")).grid(
                     row=3, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self.interlock_status = tk.Label(
            frame, text="", bg=self.config.COLOR_WHITE, font=("Arial", 10))
        self.interlock_status.pack(pady=(0, 4))

        btn_row = tk.Frame(frame, bg=self.config.COLOR_WHITE)
        btn_row.pack(pady=6)

        tk.Button(btn_row, text="Zapisz ustawienia",
                  bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=20, height=2,
                  command=self._save_interlock).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(btn_row, text="Test Arduino",
                  bg="#607D8B", fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=20, height=2,
                  command=self._test_interlock).pack(side=tk.LEFT)

        self.interlock_test_result = tk.Label(
            frame, text="", bg=self.config.COLOR_WHITE, font=("Arial", 10))
        self.interlock_test_result.pack(pady=4)

        self.interlock_current_label = tk.Label(
            frame, text=self._interlock_current_text(),
            bg=self.config.COLOR_WHITE, fg="#aaaaaa",
            font=("Arial", 8, "italic"))
        self.interlock_current_label.pack(pady=(4, 10))

    def _interlock_current_text(self):
        port    = getattr(self.config, "INTERLOCK_PORT", "COM5")
        baud    = getattr(self.config, "INTERLOCK_BAUDRATE", 9600)
        enabled = getattr(self.config, "INTERLOCK_ENABLED", True)
        status  = "aktywny" if enabled else "wyłączony"
        return f"Aktualnie: {port} @{baud} baud — {status}"

    def _save_interlock(self):
        self.config.INTERLOCK_PORT     = self.interlock_port_var.get().strip()
        self.config.INTERLOCK_BAUDRATE = int(self.interlock_baud_var.get())
        self.config.INTERLOCK_ENABLED  = self.interlock_enabled_var.get()
        self.settings.save_config(self.config)
        self.interlock_current_label.config(text=self._interlock_current_text())
        self.interlock_status.config(
            text="✓ Zapisano — zmiany aktywne po restarcie aplikacji",
            fg=self.config.COLOR_ACCENT)

    def _test_interlock(self):
        port = self.interlock_port_var.get().strip()
        baud = int(self.interlock_baud_var.get())
        self.interlock_test_result.config(
            text=f"⏳ Łączenie z Arduino na {port}...", fg="#FF9800")
        self.window.update()
        import threading
        import time

        def do_test():
            try:
                import serial
                with serial.Serial(port, baud, timeout=2) as s:
                    time.sleep(1.5)
                    s.reset_input_buffer()
                    deadline = time.time() + 2.0
                    line = ""
                    while time.time() < deadline:
                        if s.in_waiting > 0:
                            line = s.readline().decode(
                                "ascii", errors="ignore").strip()
                            break
                        time.sleep(0.05)
                if line in ("OPEN", "CLOSED"):
                    stan = "🔒 ZAMKNIĘTA" if line == "CLOSED" else "🔓 OTWARTA"
                    msg  = f"✓ Arduino odpowiada — klapa: {stan}"
                    fg   = self.config.COLOR_ACCENT
                elif line:
                    msg = f"⚠ Arduino odpowiada, nieznany format: '{line}'"
                    fg  = "#FF9800"
                else:
                    msg = "⚠ Podłączone, brak danych — sprawdź baudrate/szkic"
                    fg  = "#FF9800"
                self.window.after(0, lambda: self.interlock_test_result.config(
                    text=msg, fg=fg))
            except Exception as e:
                self.window.after(0, lambda: self.interlock_test_result.config(
                    text=f"✗ Błąd: {e}", fg=self.config.COLOR_ERROR))

        threading.Thread(target=do_test, daemon=True).start()

    # ================================================================== #
    # ZAKŁADKA 3 — HWID MAP                                               #
    # ================================================================== #
    def _create_hwid_tab(self):
        frame = tk.Frame(self.notebook, bg=self.config.COLOR_WHITE)
        self.notebook.add(frame, text="  HWID Map  ")

        tk.Label(frame, text="Mapa HWID → Model",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 13, "bold")).pack(pady=(18, 4))

        tk.Label(frame,
                 text="Pierwsze 6 znaków S/N (HWID) → przypisany model produktu",
                 bg=self.config.COLOR_WHITE, fg="#666666",
                 font=("Arial", 9)).pack(pady=(0, 8))

        table_frame = tk.Frame(frame, bg=self.config.COLOR_WHITE)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        cols = ("HWID (6 znaków)", "Model")
        self.hwid_tree = ttk.Treeview(
            table_frame, columns=cols, show="headings",
            selectmode="browse", height=10)
        for col, width in zip(cols, [160, 260]):
            self.hwid_tree.heading(col, text=col)
            self.hwid_tree.column(col, width=width, anchor="center")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                            command=self.hwid_tree.yview)
        self.hwid_tree.configure(yscrollcommand=vsb.set)
        self.hwid_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._reload_hwid_tree()

        add_frame = tk.Frame(frame, bg=self.config.COLOR_WHITE,
                             relief=tk.RAISED, borderwidth=2)
        add_frame.pack(fill=tk.X, padx=20, pady=8)

        inner = tk.Frame(add_frame, bg=self.config.COLOR_WHITE)
        inner.pack(padx=15, pady=10)

        tk.Label(inner, text="HWID (6 znaków):",
                 bg=self.config.COLOR_WHITE, fg="#444444",
                 font=("Arial", 10)).grid(
                     row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self._new_hwid_var = tk.StringVar()
        tk.Entry(inner, textvariable=self._new_hwid_var,
                 font=("Arial", 11), width=12,
                 relief=tk.SOLID, borderwidth=1).grid(
                     row=0, column=1, sticky="w", padx=(0, 20), pady=4)

        tk.Label(inner, text="Model:",
                 bg=self.config.COLOR_WHITE, fg="#444444",
                 font=("Arial", 10)).grid(
                     row=0, column=2, sticky="w", padx=(0, 8), pady=4)
        self._new_model_var = tk.StringVar()

        try:
            from hwid_map import HwidMap
            models = HwidMap().get_models_list()
        except Exception:
            models = []

        ttk.Combobox(inner, textvariable=self._new_model_var,
                     values=models, font=("Arial", 11), width=18).grid(
                         row=0, column=3, sticky="w", padx=(0, 15), pady=4)

        tk.Button(inner, text="Dodaj",
                  bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
                  font=("Arial", 10, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=10,
                  command=self._add_hwid).grid(
                      row=0, column=4, padx=(0, 5), pady=4)

        tk.Button(inner, text="Usuń zaznaczony",
                  bg=self.config.COLOR_ERROR, fg=self.config.COLOR_WHITE,
                  font=("Arial", 10, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=16,
                  command=self._remove_hwid).grid(
                      row=0, column=5, pady=4)

        self.hwid_status = tk.Label(
            frame, text="", bg=self.config.COLOR_WHITE, font=("Arial", 9))
        self.hwid_status.pack()

    def _reload_hwid_tree(self):
        try:
            from hwid_map import HwidMap
            for row in self.hwid_tree.get_children():
                self.hwid_tree.delete(row)
            for hwid, model in sorted(HwidMap().get_all().items()):
                self.hwid_tree.insert("", tk.END, values=(hwid, model))
        except Exception:
            pass

    def _add_hwid(self):
        from hwid_map import HwidMap
        hwid  = self._new_hwid_var.get().strip().upper()
        model = self._new_model_var.get().strip()
        ok, msg = HwidMap().add_hwid(hwid, model)
        if not ok:
            self.hwid_status.config(
                text=f"✗ {msg}", fg=self.config.COLOR_ERROR)
            return
        self._new_hwid_var.set("")
        self._new_model_var.set("")
        self._reload_hwid_tree()
        self.hwid_status.config(
            text=f"✓ Dodano: {hwid} → {model}",
            fg=self.config.COLOR_ACCENT)

    def _remove_hwid(self):
        from hwid_map import HwidMap
        sel = self.hwid_tree.selection()
        if not sel:
            self.hwid_status.config(
                text="Zaznacz wiersz do usunięcia.",
                fg=self.config.COLOR_ERROR)
            return
        hwid = self.hwid_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno(
                "Potwierdź", f"Usunąć mapowanie '{hwid}'?",
                parent=self.window):
            return
        if HwidMap().remove_hwid(hwid):
            self._reload_hwid_tree()
            self.hwid_status.config(
                text=f"✓ Usunięto: {hwid}", fg=self.config.COLOR_ACCENT)
        else:
            self.hwid_status.config(
                text=f"✗ Nie znaleziono: {hwid}",
                fg=self.config.COLOR_ERROR)

    # ================================================================== #
    # ZAKŁADKA 4 — PROFIL ACW (edytowalny)                               #
    # ================================================================== #
    def _create_profile_tab(self):
        frame = tk.Frame(self.notebook, bg=self.config.COLOR_WHITE)
        self.notebook.add(frame, text="  Profil ACW  ")

        tk.Label(frame, text="Profil testowy ACW",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 13, "bold")).pack(pady=(18, 4))

        tk.Label(frame,
                 text="Zmiany są zapisywane do amidala_config.json\n"
                      "i aktywne od następnego testu (bez restartu).",
                 bg=self.config.COLOR_WHITE, fg="#888888",
                 font=("Arial", 9, "italic")).pack(pady=(0, 10))

        p    = self.config.TEST_PROFILE
        card = tk.Frame(frame, bg=self.config.COLOR_WHITE,
                        relief=tk.RAISED, borderwidth=2)
        card.pack(padx=35, pady=(0, 10), fill=tk.X)

        inner = tk.Frame(card, bg=self.config.COLOR_WHITE)
        inner.pack(padx=25, pady=18)

        self._pv_voltage    = tk.StringVar(value=str(p['voltage'] / 1000))
        self._pv_limit_high = tk.StringVar(value=str(p['limit_high']))
        self._pv_limit_low  = tk.StringVar(value=str(p['limit_low']))
        self._pv_ramp       = tk.StringVar(value=str(p['ramp_time']))
        self._pv_dwell      = tk.StringVar(value=str(p['dwell']))
        self._pv_ramp_dn    = tk.StringVar(value=str(p['ramp_dn']))
        self._pv_arc        = tk.StringVar(value=str(p['arc_sense']))
        self._pv_freq       = tk.StringVar(value=str(p['frequency']))

        def row(r, label, var, unit, readonly=False):
            tk.Label(inner, text=label,
                     bg=self.config.COLOR_WHITE, fg="#555555",
                     font=("Arial", 10), width=20, anchor="e").grid(
                         row=r, column=0, sticky="e", padx=(0, 8), pady=5)
            state = "disabled" if readonly else "normal"
            bg_e  = "#f0f0f0" if readonly else self.config.COLOR_WHITE
            e = tk.Entry(inner, textvariable=var,
                         font=("Arial", 10, "bold"), width=12,
                         justify="center", relief=tk.SOLID, borderwidth=1,
                         state=state,
                         disabledbackground=bg_e,
                         disabledforeground="#999999")
            e.grid(row=r, column=1, sticky="w", pady=5)
            tk.Label(inner, text=unit,
                     bg=self.config.COLOR_WHITE, fg="#888888",
                     font=("Arial", 9)).grid(
                         row=r, column=2, sticky="w", padx=(5, 0), pady=5)

        row(0, "Test Type:",  tk.StringVar(value="ACW"), "",   readonly=True)
        row(1, "Voltage:",    self._pv_voltage,           "kV")
        row(2, "Max Limit:",  self._pv_limit_high,        "mA")
        row(3, "Min Limit:",  self._pv_limit_low,         "mA")
        row(4, "Ramp Time:",  self._pv_ramp,              "s")
        row(5, "Dwell:",      self._pv_dwell,             "s")
        row(6, "Ramp Down:",  self._pv_ramp_dn,           "s")
        row(7, "Arc Sense:",  self._pv_arc,               "ust. na Chroma", readonly=True)
        row(8, "Frequency:",  self._pv_freq,              "Hz — ust. na Chroma", readonly=True)
        row(9, "Continuity:", tk.StringVar(value="OFF"),  "", readonly=True)

        tk.Label(
            inner,
            text=("Arc Sense i Frequency nie są programowane przez aplikację, "
                  "ponieważ firmware 5.14 odrzucał używane komendy. "
                  "Wartości należy potwierdzić na panelu Chromy."),
            bg=self.config.COLOR_WHITE,
            fg="#E65100",
            font=("Arial", 8, "italic"),
            justify="left",
            wraplength=520,
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.profile_status = tk.Label(
            frame, text="", bg=self.config.COLOR_WHITE, font=("Arial", 10))
        self.profile_status.pack(pady=(0, 5))

        tk.Button(frame, text="Zapisz profil ACW",
                  bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=22, height=2,
                  command=self._save_profile).pack(pady=5)

    def _save_profile(self):
        try:
            voltage    = float(self._pv_voltage.get())
            limit_high = float(self._pv_limit_high.get())
            limit_low  = float(self._pv_limit_low.get())
            ramp_time  = float(self._pv_ramp.get())
            dwell      = float(self._pv_dwell.get())
            ramp_dn    = float(self._pv_ramp_dn.get())
            arc_sense  = int(self._pv_arc.get())
            frequency  = int(self._pv_freq.get())
        except ValueError:
            self.profile_status.config(
                text="✗ Nieprawidłowe wartości — sprawdź pola!",
                fg=self.config.COLOR_ERROR)
            return

        errors = []
        if not (0.1 <= voltage <= 5.0):
            errors.append("Voltage: 0.1–5.0 kV")
        if not (0.0 < limit_high <= 10.0):
            errors.append("Max Limit: 0.001–10.0 mA")
        if not (0.0 <= limit_low < limit_high):
            errors.append("Min Limit musi być < Max Limit")
        if not (0.0 <= ramp_time <= 999.0):
            errors.append("Ramp Time: 0–999 s")
        if not (0.1 <= dwell <= 999.0):
            errors.append("Dwell: 0.1–999 s")
        if frequency not in (50, 60):
            errors.append("Frequency: 50 lub 60 Hz")
        if errors:
            self.profile_status.config(
                text="✗ " + " | ".join(errors),
                fg=self.config.COLOR_ERROR)
            return

        self.config.TEST_PROFILE['voltage']    = int(voltage * 1000)
        self.config.TEST_PROFILE['limit_high'] = limit_high
        self.config.TEST_PROFILE['limit_low']  = limit_low
        self.config.TEST_PROFILE['ramp_time']  = ramp_time
        self.config.TEST_PROFILE['dwell']      = dwell
        self.config.TEST_PROFILE['ramp_dn']    = ramp_dn
        self.config.TEST_PROFILE['arc_sense']  = arc_sense
        self.config.TEST_PROFILE['frequency']  = frequency

        self.settings.save_config(self.config)

        total = ramp_time + dwell + ramp_dn
        self.profile_status.config(
            text=f"✓ Zapisano | {voltage:.2f} kV | "
                 f"{limit_low:.3f}–{limit_high:.3f} mA | "
                 f"Czas całk.: {total:.1f} s",
            fg=self.config.COLOR_ACCENT)

    # ================================================================== #
    # ZAKŁADKA 5 — LOGI                                                   #
    # ================================================================== #
    def _create_logs_tab(self):
        frame = tk.Frame(self.notebook, bg=self.config.COLOR_WHITE)
        self.notebook.add(frame, text="  Logi  ")

        tk.Label(frame, text="Lokalizacja zapisu logów",
                 bg=self.config.COLOR_WHITE, fg=self.config.COLOR_PRIMARY,
                 font=("Arial", 13, "bold")).pack(pady=(18, 4))

        tk.Label(frame,
                 text="Raporty TXT są zapisywane w podanej ścieżce.\n"
                      "Obsługiwane są ścieżki lokalne i sieciowe UNC "
                      "(\\\\serwer\\folder).",
                 bg=self.config.COLOR_WHITE, fg="#666666",
                 font=("Arial", 9, "italic"), justify="center").pack(pady=(0, 12))

        form = tk.Frame(frame, bg=self.config.COLOR_WHITE,
                        relief=tk.RAISED, borderwidth=2)
        form.pack(padx=35, pady=(0, 10), fill=tk.X)

        inner = tk.Frame(form, bg=self.config.COLOR_WHITE)
        inner.pack(padx=20, pady=15, fill=tk.X)

        tk.Label(inner, text="Ścieżka zapisu logów:",
                 bg=self.config.COLOR_WHITE, fg="#444444",
                 font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 6))

        path_row = tk.Frame(inner, bg=self.config.COLOR_WHITE)
        path_row.pack(fill=tk.X)

        self.log_dir_var = tk.StringVar(
            value=getattr(self.config, "LOG_DIR", "logs"))
        self.log_dir_entry = tk.Entry(
            path_row, textvariable=self.log_dir_var,
            font=("Courier", 10), relief=tk.SOLID, borderwidth=1)
        self.log_dir_entry.pack(
            side=tk.LEFT, expand=True, fill=tk.X, ipady=6, padx=(0, 8))

        tk.Button(path_row, text="Przeglądaj...",
                  bg=self.config.COLOR_PRIMARY, fg=self.config.COLOR_WHITE,
                  font=("Arial", 9, "bold"), relief=tk.FLAT,
                  cursor="hand2", padx=10, pady=5,
                  command=self._browse_log_dir).pack(side=tk.LEFT)

        self.log_active_label = tk.Label(
            inner,
            text=f"Aktualnie aktywna: {getattr(self.config, 'LOG_DIR', 'logs')}",
            bg=self.config.COLOR_WHITE, fg="#aaaaaa",
            font=("Arial", 8, "italic"))
        self.log_active_label.pack(anchor="w", pady=(6, 0))

        self.log_status = tk.Label(
            frame, text="", bg=self.config.COLOR_WHITE, font=("Arial", 10))
        self.log_status.pack(pady=(0, 5))

        btn_row = tk.Frame(frame, bg=self.config.COLOR_WHITE)
        btn_row.pack(pady=6)

        tk.Button(btn_row, text="Sprawdź dostępność",
                  bg="#FF9800", fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=20, height=2,
                  command=self._check_log_dir).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(btn_row, text="Zapisz ścieżkę",
                  bg=self.config.COLOR_ACCENT, fg=self.config.COLOR_WHITE,
                  font=("Arial", 11, "bold"), relief=tk.FLAT,
                  cursor="hand2", width=20, height=2,
                  command=self._save_log_dir).pack(side=tk.LEFT)

    def _browse_log_dir(self):
        current = self.log_dir_var.get().strip()
        init    = current if os.path.isdir(current) else "C:\\"
        chosen  = filedialog.askdirectory(
            title="Wybierz folder zapisu logów",
            initialdir=init,
            parent=self.window)
        if chosen:
            self.log_dir_var.set(chosen.replace("/", "\\"))
            self.log_status.config(text="")

    def _check_log_dir(self):
        path = self.log_dir_var.get().strip()
        if not path:
            self.log_status.config(
                text="✗ Ścieżka jest pusta!",
                fg=self.config.COLOR_ERROR)
            return
        if not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
                self.log_status.config(
                    text=f"✓ Folder utworzony: {path}",
                    fg=self.config.COLOR_ACCENT)
                return
            except Exception as e:
                self.log_status.config(
                    text=f"✗ Nie można utworzyć folderu: {e}",
                    fg=self.config.COLOR_ERROR)
                return
        test_file = os.path.join(path, "_hipot_write_test.tmp")
        try:
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            self.log_status.config(
                text=f"✓ Ścieżka dostępna i zapisywalna: {path}",
                fg=self.config.COLOR_ACCENT)
        except Exception as e:
            self.log_status.config(
                text=f"✗ Brak uprawnień do zapisu: {e}",
                fg=self.config.COLOR_ERROR)

    def _save_log_dir(self):
        path = self.log_dir_var.get().strip()
        if not path:
            self.log_status.config(
                text="✗ Ścieżka nie może być pusta!",
                fg=self.config.COLOR_ERROR)
            return
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            self.log_status.config(
                text=f"✗ Nie można utworzyć folderu: {e}",
                fg=self.config.COLOR_ERROR)
            return
        self.config.LOG_DIR = path
        self.settings.save_config(self.config)
        self.log_active_label.config(
            text=f"Aktualnie aktywna: {path}")
        self.log_status.config(
            text=f"✓ Zapisano ścieżkę logów: {path}",
            fg=self.config.COLOR_ACCENT)