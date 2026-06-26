# config.py
"""Konfiguracja aplikacji Hi-Pot Amidala"""
import json
import os

_CONFIG_FILE = "amidala_config.json"


class Config:

    # ------------------------------------------------------------------ #
    # STAŁE UI                                                             #
    # ------------------------------------------------------------------ #
    WINDOW_TITLE = "Hi-Pot Amidala"

    COLOR_BG      = "#F5F5F5"
    COLOR_WHITE   = "#FFFFFF"
    COLOR_PRIMARY = "#1A237E"   # granatowy
    COLOR_ACCENT  = "#4CAF50"   # zielony PASS
    COLOR_ERROR   = "#F44336"   # czerwony FAIL
    COLOR_WARNING = "#FF9800"   # pomarańczowy

    # ------------------------------------------------------------------ #
    # PROFIL TESTOWY ACW — hardcoded, read-only                           #
    # ------------------------------------------------------------------ #
    TEST_PROFILE = {
        "type":        "ACW",
        "voltage":     4000,       # V  (4.00 kV)
        "limit_high":  2.500,      # mA
        "limit_low":   0.050,      # mA
        "ramp_time":   5.0,        # s
        "dwell":       1.0,        # s  (test time)
        "ramp_dn":     0.0,        # s
        "arc_sense":   0,
        "frequency":   60,         # Hz
        "continuity":  "OFF",
        "cont_max":    1.00,       # ohm
        "cont_min":    0.00,       # ohm
        "connect":     "OFF",
    }

    # ------------------------------------------------------------------ #
    # DOMYŚLNE — nadpisywane przez amidala_config.json                    #
    # ------------------------------------------------------------------ #
    DEFAULT_COM_PORT     = "COM6"
    DEFAULT_BAUDRATE     = 9600
    DEFAULT_PARITY       = "NONE"
    DEFAULT_FLOW_CONTROL = "NONE"

    INTERLOCK_PORT     = "COM5"
    INTERLOCK_BAUDRATE = 9600
    INTERLOCK_ENABLED  = True

    LOG_DIR = r"\\IFS\hipot_logs\Amidala"

    AUTHORIZED_USERS = ["12101333"]

    # ------------------------------------------------------------------ #
    # INIT                                                                 #
    # ------------------------------------------------------------------ #
    def __init__(self):
        self._load()

    def _load(self):
        if not os.path.exists(_CONFIG_FILE):
            self._save_defaults()
            return
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.DEFAULT_COM_PORT     = data.get("com_port",       self.DEFAULT_COM_PORT)
            self.DEFAULT_BAUDRATE     = data.get("baudrate",       self.DEFAULT_BAUDRATE)
            self.DEFAULT_PARITY       = data.get("parity",         self.DEFAULT_PARITY)
            self.DEFAULT_FLOW_CONTROL = data.get("flow_control",   self.DEFAULT_FLOW_CONTROL)

            self.INTERLOCK_PORT       = data.get("interlock_port", self.INTERLOCK_PORT)
            self.INTERLOCK_BAUDRATE   = data.get("interlock_baud", self.INTERLOCK_BAUDRATE)
            self.INTERLOCK_ENABLED    = data.get("interlock_on",   self.INTERLOCK_ENABLED)

            self.LOG_DIR              = data.get("log_dir",        self.LOG_DIR)
            self.AUTHORIZED_USERS     = data.get("operators",      [])

        except Exception as e:
            print(f"[CONFIG] Błąd wczytywania: {e} — używam domyślnych")
            self._save_defaults()

    def _save_defaults(self):
        from settings_manager import SettingsManager
        SettingsManager().save_config(self)