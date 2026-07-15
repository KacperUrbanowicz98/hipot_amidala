# config.py
"""Konfiguracja aplikacji Hi-Pot Amidala.

Wszystkie ustawienia edytowalne z panelu administracyjnego są zapisywane
w pliku amidala_config.json przez SettingsManager i wczytywane ponownie
przy starcie aplikacji.
"""

import os

_CONFIG_FILE = "amidala_config.json"


class Config:
    # ------------------------------------------------------------------ #
    # STAŁE UI - nie są zapisywane w JSON                                 #
    # ------------------------------------------------------------------ #
    WINDOW_TITLE = "Hi-Pot Amidala"

    COLOR_BG = "#F5F5F5"
    COLOR_WHITE = "#FFFFFF"
    COLOR_PRIMARY = "#1A237E"
    COLOR_ACCENT = "#4CAF50"
    COLOR_ERROR = "#F44336"
    COLOR_WARNING = "#FF9800"

    # ------------------------------------------------------------------ #
    # DOMYŚLNY PROFIL TESTOWY                                             #
    # ------------------------------------------------------------------ #
    # Ta wartość jest tylko fallbackiem. Po uruchomieniu dane są
    # nadpisywane wartościami z amidala_config.json.
    TEST_PROFILE = {
        "type": "ACW",
        "voltage": 4000,
        "limit_high": 2.500,
        "limit_low": 0.050,
        "ramp_time": 5.0,
        "dwell": 1.0,
        "ramp_dn": 0.0,
        "arc_sense": 0,
        "frequency": 60,
        "continuity": "OFF",
        "cont_max": 1.00,
        "cont_min": 0.00,
        "connect": "OFF",
    }

    # ------------------------------------------------------------------ #
    # WARTOŚCI DOMYŚLNE - NADPISYWANE PRZEZ JSON                          #
    # ------------------------------------------------------------------ #
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

    # Pozostawione dla kompatybilności ze starszym kodem.
    AUTHORIZED_USERS = ["12101333"]

    def __init__(self):
        """Tworzy niezależną konfigurację i wczytuje ustawienia z JSON."""
        # TEST_PROFILE jest słownikiem. Kopia zapobiega modyfikowaniu
        # wspólnej wartości klasowej przez panel administracyjny.
        self.TEST_PROFILE = dict(type(self).TEST_PROFILE)
        self.AUTHORIZED_USERS = list(type(self).AUTHORIZED_USERS)

        self._load()

    def _load(self):
        """Wczytuje konfigurację w tym samym formacie, w którym zapisuje panel."""
        from settings_manager import SettingsManager

        manager = SettingsManager()

        if os.path.isfile(_CONFIG_FILE):
            manager.load_config(self)
        else:
            # Pierwsze uruchomienie - utworzenie edytowalnego JSON-a
            # z aktualnymi wartościami domyślnymi.
            manager.save_config(self)