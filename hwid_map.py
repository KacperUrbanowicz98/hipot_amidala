# hwid_map.py
"""Mapowanie HWID (pierwsze 6 znakow S/N) na nazwe modelu."""

from safety_rules import SafetyValidationError, validate_serial
from settings_manager import SettingsManager


DEFAULT_HWID_MAP = {
    "211530": "ESD-160S/VE", "211531": "ESD-160S/VE",
    "211532": "ESD-160S/VE", "211533": "ESD-160S/VE",
    "211534": "ESD-160S/VE", "211535": "ESD-160S/VE",
    "211536": "ESD-160S/VE", "211537": "ESD-160S/VE",
    "211538": "ESD-160S/VE", "211539": "ESD-160S/VE",
    "211510": "ESD-160S", "211511": "ESD-160S",
    "211512": "ESD-160S", "211513": "ESD-160S",
    "211514": "ESD-160S", "211515": "ESD-160S",
    "211516": "ESD-160S", "211517": "ESD-160S",
    "211518": "ESD-160S", "211519": "ESD-160S",
    "111540": "ESD-160C/VE", "111541": "ESD-160C/VE",
    "111542": "ESD-160C/VE", "111543": "ESD-160C/VE",
    "111544": "ESD-160C/VE", "111545": "ESD-160C/VE",
    "111546": "ESD-160C/VE", "111547": "ESD-160C/VE",
    "111548": "ESD-160C/VE", "111549": "ESD-160C/VE",
    "111520": "ESD-160C", "111521": "ESD-160C",
    "111522": "ESD-160C", "111523": "ESD-160C",
    "111524": "ESD-160C", "111525": "ESD-160C",
    "111526": "ESD-160C", "111527": "ESD-160C",
    "111528": "ESD-160C", "111529": "ESD-160C",
    "6763A1": "ESi160", "6763A2": "ESi160",
    "6763A3": "ESi160", "6763A4": "ESi160",
    "6763A5": "ESi160",
}


class HwidMap:
    def __init__(self):
        self._map: dict[str, str] = SettingsManager().load_hwid_map(DEFAULT_HWID_MAP)

    def get_model(self, serial: str) -> str | None:
        if not serial or len(serial) < 6:
            return None
        return self._map.get(serial[:6].upper())

    def validate_serial(self, serial: str) -> tuple[bool, str]:
        try:
            normalized = validate_serial(serial)
        except SafetyValidationError as exc:
            return False, str(exc)

        model = self.get_model(normalized)
        if model is None:
            return False, f"Nieznany HWID: '{normalized[:6]}' - brak w mapie"
        return True, model

    def get_all(self) -> dict:
        return dict(self._map)

    def add_hwid(self, hwid: str, model: str) -> tuple[bool, str]:
        normalized_hwid = str(hwid or "").strip().upper()
        normalized_model = str(model or "").strip()
        if len(normalized_hwid) != 6 or not normalized_hwid.isascii() or not normalized_hwid.isalnum():
            return False, "HWID musi miec dokladnie 6 liter/cyfr"
        if not normalized_model:
            return False, "Nazwa modelu nie moze byc pusta"

        updated = dict(self._map)
        updated[normalized_hwid] = normalized_model
        try:
            SettingsManager().save_hwid_map(updated)
        except Exception as exc:
            return False, f"Nie udalo sie zapisac mapy HWID: {exc}"
        self._map = updated
        return True, ""

    def remove_hwid(self, hwid: str) -> bool:
        normalized_hwid = str(hwid or "").strip().upper()
        if normalized_hwid not in self._map:
            return False
        updated = dict(self._map)
        del updated[normalized_hwid]
        SettingsManager().save_hwid_map(updated)
        self._map = updated
        return True

    def get_models_list(self) -> list:
        return sorted(set(self._map.values()))
