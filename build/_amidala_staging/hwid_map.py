# hwid_map.py
"""Mapowanie HWID (pierwsze 6 znaków S/N) → nazwa modelu"""
from settings_manager import SettingsManager

# Domyślna mapa HWID → model (fallback jeśli brak hwid_map.json)
DEFAULT_HWID_MAP = {
    # ESD-160S/VE
    "211530": "ESD-160S/VE",
    "211531": "ESD-160S/VE",
    "211532": "ESD-160S/VE",
    "211533": "ESD-160S/VE",
    "211534": "ESD-160S/VE",
    "211535": "ESD-160S/VE",
    "211536": "ESD-160S/VE",
    "211537": "ESD-160S/VE",
    "211538": "ESD-160S/VE",
    "211539": "ESD-160S/VE",
    # ESD-160S
    "211510": "ESD-160S",
    "211511": "ESD-160S",
    "211512": "ESD-160S",
    "211513": "ESD-160S",
    "211514": "ESD-160S",
    "211515": "ESD-160S",
    "211516": "ESD-160S",
    "211517": "ESD-160S",
    "211518": "ESD-160S",
    "211519": "ESD-160S",
    # ESD-160C/VE
    "111540": "ESD-160C/VE",
    "111541": "ESD-160C/VE",
    "111542": "ESD-160C/VE",
    "111543": "ESD-160C/VE",
    "111544": "ESD-160C/VE",
    "111545": "ESD-160C/VE",
    "111546": "ESD-160C/VE",
    "111547": "ESD-160C/VE",
    "111548": "ESD-160C/VE",
    "111549": "ESD-160C/VE",
    # ESD-160C
    "111520": "ESD-160C",
    "111521": "ESD-160C",
    "111522": "ESD-160C",
    "111523": "ESD-160C",
    "111524": "ESD-160C",
    "111525": "ESD-160C",
    "111526": "ESD-160C",
    "111527": "ESD-160C",
    "111528": "ESD-160C",
    "111529": "ESD-160C",
    # ESi160
    "6763A1": "ESi160",
    "6763A2": "ESi160",
    "6763A3": "ESi160",
    "6763A4": "ESi160",
    "6763A5": "ESi160",
}


class HwidMap:
    """Singleton-like — ładuje mapę raz, trzyma w pamięci."""

    _instance = None

    def __init__(self):
        sm = SettingsManager()
        self._map: dict = sm.load_hwid_map(DEFAULT_HWID_MAP)

    # ------------------------------------------------------------------ #

    def get_model(self, serial: str) -> str | None:
        """
        Zwraca nazwę modelu dla danego S/N lub None jeśli HWID nieznany.
        Pobiera pierwsze 6 znaków S/N jako HWID.
        """
        if not serial or len(serial) < 6:
            return None
        hwid = serial[:6].upper()
        return self._map.get(hwid)

    def validate_serial(self, serial: str) -> tuple[bool, str]:
        """
        Walidacja S/N:
        - długość 14 lub 17 znaków
        - pierwsze 6 znaków musi być w mapie HWID
        Zwraca (True, model_name) lub (False, komunikat_błędu).
        """
        s = serial.strip().upper()

        if len(s) not in (14, 17):
            return False, f"Nieprawidłowa długość S/N: {len(s)} znaków (wymagane 14 lub 17)"

        model = self.get_model(s)
        if model is None:
            hwid = s[:6]
            return False, f"Nieznany HWID: '{hwid}' — brak w mapie"

        return True, model

    # ------------------------------------------------------------------ #
    # Metody dla panelu admina                                             #
    # ------------------------------------------------------------------ #

    def get_all(self) -> dict:
        """Zwraca kopię całej mapy {hwid: model}."""
        return dict(self._map)

    def add_hwid(self, hwid: str, model: str) -> tuple[bool, str]:
        """
        Dodaje nowy HWID do mapy i zapisuje do pliku.
        Zwraca (True, '') lub (False, komunikat_błędu).
        """
        hwid = hwid.strip().upper()
        model = model.strip()

        if not hwid:
            return False, "HWID nie może być pusty"
        if len(hwid) != 6:
            return False, f"HWID musi mieć dokładnie 6 znaków (podano {len(hwid)})"
        if not model:
            return False, "Nazwa modelu nie może być pusta"

        self._map[hwid] = model
        SettingsManager().save_hwid_map(self._map)
        return True, ""

    def remove_hwid(self, hwid: str) -> bool:
        """Usuwa HWID z mapy. Zwraca True jeśli usunięto."""
        hwid = hwid.strip().upper()
        if hwid in self._map:
            del self._map[hwid]
            SettingsManager().save_hwid_map(self._map)
            return True
        return False

    def get_models_list(self) -> list[str]:
        """Zwraca unikalną posortowaną listę nazw modeli."""
        return sorted(set(self._map.values()))