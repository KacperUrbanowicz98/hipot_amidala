# settings_manager.py
"""Zarządzanie trwałą konfiguracją aplikacji — zapis/odczyt JSON"""
import json
import os

CONFIG_FILE    = "amidala_config.json"
OPERATORS_FILE = "operators.json"
HWID_MAP_FILE  = "hwid_map.json"


class SettingsManager:

    # ------------------------------------------------------------------ #
    # OPERATORS (legacy — zachowane dla kompatybilności)                  #
    # ------------------------------------------------------------------ #
    def load_operators(self, default: list) -> list:
        if not os.path.exists(OPERATORS_FILE):
            return default
        try:
            with open(OPERATORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else default
        except Exception:
            return default

    def save_operators(self, operators: list):
        try:
            with open(OPERATORS_FILE, "w", encoding="utf-8") as f:
                json.dump(operators, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SettingsManager] Błąd zapisu operators.json: {e}")

    # ------------------------------------------------------------------ #
    # HWID MAP                                                             #
    # ------------------------------------------------------------------ #
    def load_hwid_map(self, default: dict) -> dict:
        if not os.path.exists(HWID_MAP_FILE):
            return dict(default)
        try:
            with open(HWID_MAP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return (
                    {k.upper(): v for k, v in data.items()}
                    if isinstance(data, dict)
                    else dict(default)
                )
        except Exception as e:
            print(f"[SettingsManager] Błąd odczytu {HWID_MAP_FILE}: {e}")
            return dict(default)

    def save_hwid_map(self, hwid_map: dict):
        try:
            with open(HWID_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(hwid_map, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SettingsManager] Błąd zapisu {HWID_MAP_FILE}: {e}")

    # ------------------------------------------------------------------ #
    # CONFIG — zapis / odczyt wszystkich ustawień                         #
    # ------------------------------------------------------------------ #
    def save_config(self, config):
        """Zapisuje do JSON wszystkie edytowalne pola konfiguracji."""
        p = config.TEST_PROFILE
        data = {
            # RS232
            "DEFAULT_COM_PORT":     config.DEFAULT_COM_PORT,
            "DEFAULT_BAUDRATE":     config.DEFAULT_BAUDRATE,
            "DEFAULT_PARITY":       config.DEFAULT_PARITY,
            "DEFAULT_FLOW_CONTROL": config.DEFAULT_FLOW_CONTROL,
            # Interlock
            "INTERLOCK_PORT":       config.INTERLOCK_PORT,
            "INTERLOCK_BAUDRATE":   config.INTERLOCK_BAUDRATE,
            "INTERLOCK_ENABLED":    config.INTERLOCK_ENABLED,
            # Inne
            "LOG_DIR":              config.LOG_DIR,
            "AUTO_SAVE_RESULTS":    getattr(config, "AUTO_SAVE_RESULTS", True),
            "TEST_TIMEOUT":         getattr(config, "TEST_TIMEOUT", 300),
            # Profil ACW
            "TEST_PROFILE": {
                "type":       p.get("type",       "ACW"),
                "voltage":    p.get("voltage",    4000),
                "limit_high": p.get("limit_high", 2.5),
                "limit_low":  p.get("limit_low",  0.05),
                "ramp_time":  p.get("ramp_time",  5.0),
                "dwell":      p.get("dwell",      1.0),
                "ramp_dn":    p.get("ramp_dn",    0.0),
                "arc_sense":  p.get("arc_sense",  0),
                "frequency":  p.get("frequency",  60),
                "continuity": p.get("continuity", "OFF"),
            },
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SettingsManager] Błąd zapisu {CONFIG_FILE}: {e}")

    def load_config(self, config):
        """Wczytuje ustawienia z JSON i nadpisuje pola obiektu config."""
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[SettingsManager] Błąd odczytu {CONFIG_FILE}: {e}")
            return

        # RS232
        if "DEFAULT_COM_PORT"     in data:
            config.DEFAULT_COM_PORT     = data["DEFAULT_COM_PORT"]
        if "DEFAULT_BAUDRATE"     in data:
            config.DEFAULT_BAUDRATE     = int(data["DEFAULT_BAUDRATE"])
        if "DEFAULT_PARITY"       in data:
            config.DEFAULT_PARITY       = data["DEFAULT_PARITY"]
        if "DEFAULT_FLOW_CONTROL" in data:
            config.DEFAULT_FLOW_CONTROL = data["DEFAULT_FLOW_CONTROL"]

        # Interlock
        if "INTERLOCK_PORT"     in data:
            config.INTERLOCK_PORT     = data["INTERLOCK_PORT"]
        if "INTERLOCK_BAUDRATE" in data:
            config.INTERLOCK_BAUDRATE = int(data["INTERLOCK_BAUDRATE"])
        if "INTERLOCK_ENABLED"  in data:
            config.INTERLOCK_ENABLED  = bool(data["INTERLOCK_ENABLED"])

        # Inne
        if "LOG_DIR"           in data:
            config.LOG_DIR           = data["LOG_DIR"]
        if "AUTO_SAVE_RESULTS" in data:
            config.AUTO_SAVE_RESULTS = bool(data["AUTO_SAVE_RESULTS"])
        if "TEST_TIMEOUT"      in data:
            config.TEST_TIMEOUT      = int(data["TEST_TIMEOUT"])

        # Profil ACW
        if "TEST_PROFILE" in data:
            saved_p = data["TEST_PROFILE"]
            p       = config.TEST_PROFILE
            p["type"]       = saved_p.get("type",       p.get("type",       "ACW"))
            p["voltage"]    = int(saved_p.get("voltage",    p.get("voltage",    4000)))
            p["limit_high"] = float(saved_p.get("limit_high", p.get("limit_high", 2.5)))
            p["limit_low"]  = float(saved_p.get("limit_low",  p.get("limit_low",  0.05)))
            p["ramp_time"]  = float(saved_p.get("ramp_time",  p.get("ramp_time",  5.0)))
            p["dwell"]      = float(saved_p.get("dwell",      p.get("dwell",      1.0)))
            p["ramp_dn"]    = float(saved_p.get("ramp_dn",    p.get("ramp_dn",    0.0)))
            p["arc_sense"]  = int(saved_p.get("arc_sense",   p.get("arc_sense",  0)))
            p["frequency"]  = int(saved_p.get("frequency",   p.get("frequency",  60)))
            p["continuity"] = saved_p.get("continuity",      p.get("continuity", "OFF"))