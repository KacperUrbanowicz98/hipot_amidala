# config.py
"""Konfiguracja aplikacji Hi-Pot Amidala"""
from settings_manager import SettingsManager


class Config:
    # Kolory
    COLOR_PRIMARY = "#375ea9"
    COLOR_ACCENT  = "#4CAF50"
    COLOR_BG      = "#f5f5f5"
    COLOR_WHITE   = "#FFFFFF"
    COLOR_ERROR   = "#f44336"

    # Okno
    WINDOW_WIDTH  = 1000
    WINDOW_HEIGHT = 750
    WINDOW_TITLE  = "Reconext Hi-Pot Amidala"

    # RS232 — Chroma Hi-Pot
    DEFAULT_COM_PORT    = "COM6"
    DEFAULT_BAUDRATE    = 9600
    DEFAULT_PARITY      = "NONE"
    DEFAULT_FLOW_CONTROL = "NONE"

    # Interlock — Arduino
    INTERLOCK_PORT     = "COM1"
    INTERLOCK_BAUDRATE = 9600
    INTERLOCK_ENABLED  = True

    # Inne
    AUTO_SAVE_RESULTS = True
    TEST_TIMEOUT      = 300
    LOG_DIR           = "logs"

    # Profil testowy ACW — stały, jeden dla wszystkich produktów
    TEST_PROFILE = {
        "type":       "ACW",
        "voltage":    4000,       # V (4.00 kV)
        "limit_high": 2.50,       # mA
        "limit_low":  0.050,      # mA
        "ramp_time":  5.0,        # s
        "dwell":      1.0,        # s  (test time)
        "ramp_dn":    0.0,        # s
        "arc_sense":  0,
        "frequency":  60,         # Hz
    }

    # Autoryzowani operatorzy (fallback — nadpisywane z operators.json)
    AUTHORIZED_USERS = [
        "TEST",
    ]

    def __init__(self):
        sm = SettingsManager()
        self.AUTHORIZED_USERS = sm.load_operators(self.AUTHORIZED_USERS)
        sm.load_config(self)