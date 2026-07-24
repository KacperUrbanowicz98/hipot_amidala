# config.py
"""Konfiguracja aplikacji Hi-Pot Amidala."""

import os

from safety_rules import MIN_PRESENCE_CURRENT_MA

APP_VERSION = "1.0.5"
_CONFIG_FILE = "amidala_config.json"


class Config:
    APP_VERSION = APP_VERSION
    WINDOW_TITLE = "Hi-Pot Amidala"

    COLOR_BG = "#F5F5F5"
    COLOR_WHITE = "#FFFFFF"
    COLOR_PRIMARY = "#1A237E"
    COLOR_ACCENT = "#4CAF50"
    COLOR_ERROR = "#F44336"
    COLOR_WARNING = "#FF9800"

    TEST_PROFILE = {
        "type": "ACW",
        "voltage": 4000,
        "limit_high": 2.500,
        "limit_low": 0.050,
        "presence_min_current": MIN_PRESENCE_CURRENT_MA,
        "ramp_time": 5.0,
        "dwell": 1.0,
        "ramp_dn": 0.0,
        "arc_sense": 0,
        "frequency": 60,
        "continuity": "OFF",
    }

    DEFAULT_COM_PORT = "COM6"
    DEFAULT_BAUDRATE = 9600
    DEFAULT_PARITY = "NONE"
    DEFAULT_FLOW_CONTROL = "NONE"

    INTERLOCK_PORT = "COM5"
    INTERLOCK_BAUDRATE = 9600
    INTERLOCK_ENABLED = True

    LOG_DIR = r"\\IFS\hipot_logs\Amidala"
    AUTO_SAVE_RESULTS = True
    TEST_TIMEOUT = 300
    AUTHORIZED_USERS = ["12101333"]

    def __init__(self):
        self.TEST_PROFILE = dict(type(self).TEST_PROFILE)
        self.AUTHORIZED_USERS = list(type(self).AUTHORIZED_USERS)
        self._load()

    def _load(self):
        from settings_manager import SettingsManager

        manager = SettingsManager()
        if not os.path.isfile(_CONFIG_FILE):
            from safety_rules import SafetyValidationError
            raise SafetyValidationError(
                f"Brak wymaganego pliku konfiguracji: {_CONFIG_FILE}"
            )
        manager.load_config(self)
