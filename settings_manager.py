# settings_manager.py
"""Zarzadzanie trwala konfiguracja aplikacji - zapis/odczyt JSON."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from safety_rules import (
    SafetyValidationError,
    validate_acw_profile,
    validate_interlock_settings,
    validate_rs232_settings,
    validate_test_timeout,
    validate_timeout_for_profile,
)

CONFIG_FILE = "amidala_config.json"
OPERATORS_FILE = "operators.json"
HWID_MAP_FILE = "hwid_map.json"


class SettingsManager:
    @staticmethod
    def _atomic_write_json(path: str, data: Any) -> None:
        """Zapisuje JSON atomowo, aby watcher ani awaria nie widzialy polowy pliku."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    @staticmethod
    def _load_json_object(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            raise SafetyValidationError(f"Blad odczytu {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise SafetyValidationError(f"{path} musi zawierac obiekt JSON")
        return data

    # ------------------------------------------------------------------ #
    # OPERATORS (legacy)
    # ------------------------------------------------------------------ #
    def load_operators(self, default: list) -> list:
        if not os.path.exists(OPERATORS_FILE):
            return list(default)
        try:
            with open(OPERATORS_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else list(default)
        except Exception as exc:
            print(f"[SettingsManager] Blad odczytu {OPERATORS_FILE}: {exc}")
            return list(default)

    def save_operators(self, operators: list) -> None:
        self._atomic_write_json(OPERATORS_FILE, operators)

    # ------------------------------------------------------------------ #
    # HWID MAP
    # ------------------------------------------------------------------ #
    def load_hwid_map(self, default: dict) -> dict:
        if not os.path.exists(HWID_MAP_FILE):
            raise SafetyValidationError(
                f"Brak wymaganego pliku mapy HWID: {HWID_MAP_FILE}"
            )

        data = self._load_json_object(HWID_MAP_FILE)
        normalized: dict[str, str] = {}
        for raw_hwid, raw_model in data.items():
            hwid = str(raw_hwid).strip().upper()
            model = str(raw_model).strip()
            if len(hwid) != 6 or not hwid.isascii() or not hwid.isalnum():
                raise SafetyValidationError(
                    f"Nieprawidlowy HWID w {HWID_MAP_FILE}: {raw_hwid!r}"
                )
            if not model:
                raise SafetyValidationError(
                    f"Pusta nazwa modelu dla HWID {hwid} w {HWID_MAP_FILE}"
                )
            normalized[hwid] = model
        if not normalized:
            raise SafetyValidationError(f"{HWID_MAP_FILE} nie moze byc pusty")
        return normalized

    def save_hwid_map(self, hwid_map: dict) -> None:
        normalized: dict[str, str] = {}
        for raw_hwid, raw_model in hwid_map.items():
            hwid = str(raw_hwid).strip().upper()
            model = str(raw_model).strip()
            if len(hwid) != 6 or not hwid.isascii() or not hwid.isalnum() or not model:
                raise SafetyValidationError(
                    f"Nieprawidlowe mapowanie HWID: {raw_hwid!r} -> {raw_model!r}"
                )
            normalized[hwid] = model
        if not normalized:
            raise SafetyValidationError(f"{HWID_MAP_FILE} nie moze byc pusty")
        self._atomic_write_json(HWID_MAP_FILE, normalized)

    # ------------------------------------------------------------------ #
    # CONFIG
    # ------------------------------------------------------------------ #
    def save_config(self, config) -> None:
        profile = validate_acw_profile(config.TEST_PROFILE)
        port, baudrate, parity, flow_control = validate_rs232_settings(
            config.DEFAULT_COM_PORT,
            config.DEFAULT_BAUDRATE,
            config.DEFAULT_PARITY,
            config.DEFAULT_FLOW_CONTROL,
        )
        interlock_port, interlock_baudrate, interlock_enabled = (
            validate_interlock_settings(
                config.INTERLOCK_PORT,
                config.INTERLOCK_BAUDRATE,
                config.INTERLOCK_ENABLED,
            )
        )
        log_dir = str(config.LOG_DIR or "").strip()
        if not log_dir:
            raise SafetyValidationError("LOG_DIR nie moze byc pusty")
        auto_save = config.AUTO_SAVE_RESULTS
        if not isinstance(auto_save, bool):
            raise SafetyValidationError("AUTO_SAVE_RESULTS musi byc true/false")
        if not auto_save:
            raise SafetyValidationError(
                "AUTO_SAVE_RESULTS musi pozostac true w wersji produkcyjnej"
            )
        timeout = validate_timeout_for_profile(config.TEST_TIMEOUT, profile)

        data = {
            "DEFAULT_COM_PORT": port,
            "DEFAULT_BAUDRATE": baudrate,
            "DEFAULT_PARITY": parity,
            "DEFAULT_FLOW_CONTROL": flow_control,
            "INTERLOCK_PORT": interlock_port,
            "INTERLOCK_BAUDRATE": interlock_baudrate,
            "INTERLOCK_ENABLED": interlock_enabled,
            "LOG_DIR": log_dir,
            "AUTO_SAVE_RESULTS": auto_save,
            "TEST_TIMEOUT": timeout,
            "TEST_PROFILE": profile,
        }
        self._atomic_write_json(CONFIG_FILE, data)

    def load_config(self, config) -> None:
        """Waliduje caly plik przed zmiana obiektu config (transakcyjnie)."""
        if not os.path.exists(CONFIG_FILE):
            return

        data = self._load_json_object(CONFIG_FILE)
        port, baudrate, parity, flow_control = validate_rs232_settings(
            data.get("DEFAULT_COM_PORT", config.DEFAULT_COM_PORT),
            data.get("DEFAULT_BAUDRATE", config.DEFAULT_BAUDRATE),
            data.get("DEFAULT_PARITY", config.DEFAULT_PARITY),
            data.get("DEFAULT_FLOW_CONTROL", config.DEFAULT_FLOW_CONTROL),
        )

        enabled_value = data.get("INTERLOCK_ENABLED", config.INTERLOCK_ENABLED)
        interlock_port, interlock_baudrate, interlock_enabled = (
            validate_interlock_settings(
                data.get("INTERLOCK_PORT", config.INTERLOCK_PORT),
                data.get("INTERLOCK_BAUDRATE", config.INTERLOCK_BAUDRATE),
                enabled_value,
            )
        )

        log_dir = str(data.get("LOG_DIR", config.LOG_DIR) or "").strip()
        if not log_dir:
            raise SafetyValidationError("LOG_DIR nie moze byc pusty")

        auto_save = data.get("AUTO_SAVE_RESULTS", config.AUTO_SAVE_RESULTS)
        if not isinstance(auto_save, bool):
            raise SafetyValidationError("AUTO_SAVE_RESULTS musi byc true/false")
        if not auto_save:
            raise SafetyValidationError(
                "AUTO_SAVE_RESULTS musi pozostac true w wersji produkcyjnej"
            )

        timeout_value = data.get("TEST_TIMEOUT", config.TEST_TIMEOUT)
        # Walidacja powiazania timeoutu z profilem nastapi po zlozeniu profilu.

        merged_profile = dict(config.TEST_PROFILE)
        saved_profile = data.get("TEST_PROFILE", {})
        if not isinstance(saved_profile, dict):
            raise SafetyValidationError("TEST_PROFILE musi byc obiektem JSON")
        merged_profile.update(saved_profile)
        profile = validate_acw_profile(merged_profile)
        timeout = validate_timeout_for_profile(timeout_value, profile)

        # Zastosowanie dopiero po pomyslnej walidacji wszystkich pol.
        config.DEFAULT_COM_PORT = port
        config.DEFAULT_BAUDRATE = baudrate
        config.DEFAULT_PARITY = parity
        config.DEFAULT_FLOW_CONTROL = flow_control
        config.INTERLOCK_PORT = interlock_port
        config.INTERLOCK_BAUDRATE = interlock_baudrate
        config.INTERLOCK_ENABLED = interlock_enabled
        config.LOG_DIR = log_dir
        config.AUTO_SAVE_RESULTS = auto_save
        config.TEST_TIMEOUT = timeout
        config.TEST_PROFILE = profile
