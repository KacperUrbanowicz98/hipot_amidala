"""Centralne reguly bezpieczenstwa i walidacji dla Hi-Pot Amidala."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping


class SafetyValidationError(ValueError):
    """Blad konfiguracji lub dowodow cyklu, ktory musi zablokowac test."""


_SERIAL_RE = re.compile(r"^[A-Z0-9]+$")
_ALLOWED_BAUDRATES = {1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200}
_ALLOWED_PARITY = {"NONE", "ODD", "EVEN"}
_ALLOWED_FLOW_CONTROL = {"NONE", "RTS/CTS", "XON/XOFF"}
MIN_PRESENCE_CURRENT_MA = 0.500


def _finite_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SafetyValidationError(f"{field}: oczekiwano liczby") from exc
    if not math.isfinite(number):
        raise SafetyValidationError(f"{field}: wartosc musi byc skonczona")
    return number


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise SafetyValidationError(f"{field}: oczekiwano liczby calkowitej")

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return int(value)
        raise SafetyValidationError(f"{field}: oczekiwano liczby calkowitej")

    text = str(value or "").strip()
    if not re.fullmatch(r"[+-]?\d+", text):
        raise SafetyValidationError(f"{field}: oczekiwano liczby calkowitej")
    return int(text)


def validate_test_timeout(value: Any) -> int:
    timeout = _strict_int(value, "TEST_TIMEOUT")
    if not 5 <= timeout <= 3600:
        raise SafetyValidationError("TEST_TIMEOUT musi byc w zakresie 5-3600 s")
    return timeout


def validate_serial(serial: str, allowed_lengths: tuple[int, ...] = (14, 17)) -> str:
    value = str(serial or "").strip().upper()
    if len(value) not in allowed_lengths:
        expected = " lub ".join(str(length) for length in allowed_lengths)
        raise SafetyValidationError(
            f"Nieprawidlowa dlugosc S/N: {len(value)} znakow (wymagane {expected})"
        )
    if not _SERIAL_RE.fullmatch(value):
        raise SafetyValidationError("S/N moze zawierac tylko litery A-Z i cyfry 0-9")
    return value


def validate_rs232_settings(
    port: Any,
    baudrate: Any,
    parity: Any = "NONE",
    flow_control: Any = "NONE",
) -> tuple[str, int, str, str]:
    normalized_port = str(port or "").strip().upper()
    if not normalized_port:
        raise SafetyValidationError("Port COM Hi-Pot nie moze byc pusty")

    normalized_baudrate = _strict_int(baudrate, "Baudrate Hi-Pot")
    if normalized_baudrate not in _ALLOWED_BAUDRATES:
        raise SafetyValidationError(
            f"Nieobslugiwany baudrate Hi-Pot: {normalized_baudrate}"
        )

    normalized_parity = str(parity or "").strip().upper()
    if normalized_parity not in _ALLOWED_PARITY:
        raise SafetyValidationError(
            f"Nieobslugiwane parity: {normalized_parity or '<puste>'}"
        )

    normalized_flow = str(flow_control or "").strip().upper()
    if normalized_flow not in _ALLOWED_FLOW_CONTROL:
        raise SafetyValidationError(
            f"Nieobslugiwany Flow Control: {normalized_flow or '<puste>'}"
        )

    return normalized_port, normalized_baudrate, normalized_parity, normalized_flow


def validate_interlock_settings(
    port: Any,
    baudrate: Any,
    enabled: Any,
) -> tuple[str, int, bool]:
    if not isinstance(enabled, bool):
        raise SafetyValidationError("INTERLOCK_ENABLED musi byc wartoscia true/false")
    if enabled is not True:
        raise SafetyValidationError(
            "INTERLOCK_ENABLED musi pozostac true w wersji produkcyjnej"
        )

    normalized_port = str(port or "").strip().upper()
    if not normalized_port:
        raise SafetyValidationError("Port COM interlocka nie moze byc pusty")

    normalized_baudrate = _strict_int(baudrate, "Baudrate interlocka")
    if normalized_baudrate not in _ALLOWED_BAUDRATES:
        raise SafetyValidationError(
            f"Nieobslugiwany baudrate interlocka: {normalized_baudrate}"
        )
    return normalized_port, normalized_baudrate, True


def validate_acw_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, Mapping):
        raise SafetyValidationError("TEST_PROFILE musi byc obiektem JSON")

    test_type = str(profile.get("type", "ACW")).strip().upper()
    if test_type != "ACW":
        raise SafetyValidationError("Obslugiwany jest wylacznie profil ACW")

    voltage = _finite_float(profile.get("voltage", 4000), "Voltage")
    limit_high = _finite_float(profile.get("limit_high", 2.5), "Max Limit")
    limit_low = _finite_float(profile.get("limit_low", 0.05), "Min Limit")
    presence_min = _finite_float(
        profile.get("presence_min_current", 0.50), "Min obecnosci"
    )
    ramp_time = _finite_float(profile.get("ramp_time", 5.0), "Ramp Time")
    dwell = _finite_float(profile.get("dwell", 1.0), "Dwell")
    ramp_dn = _finite_float(profile.get("ramp_dn", 0.0), "Ramp Down")
    arc_sense = _strict_int(profile.get("arc_sense", 0), "Arc Sense")
    frequency = _strict_int(profile.get("frequency", 60), "Frequency")
    continuity = str(profile.get("continuity", "OFF")).strip().upper()

    errors: list[str] = []
    if not 100.0 <= voltage <= 5000.0:
        errors.append("Voltage musi byc w zakresie 100-5000 V")
    if not 0.001 <= limit_high <= 10.0:
        errors.append("Max Limit musi byc w zakresie 0.001-10.0 mA")
    if not 0.0 <= limit_low < limit_high:
        errors.append("Min Limit musi byc >= 0 i mniejszy od Max Limit")
    if not MIN_PRESENCE_CURRENT_MA <= presence_min < limit_high:
        errors.append(
            f"Min obecnosci musi byc >= {MIN_PRESENCE_CURRENT_MA:.3f} mA "
            "i mniejszy od Max Limit"
        )
    if presence_min < limit_low:
        errors.append("Min obecnosci nie moze byc nizszy od Min Limit")
    if not 0.0 <= ramp_time <= 999.0:
        errors.append("Ramp Time musi byc w zakresie 0-999 s")
    if not 0.1 <= dwell <= 999.0:
        errors.append("Dwell musi byc w zakresie 0.1-999 s")
    if not 0.0 <= ramp_dn <= 999.0:
        errors.append("Ramp Down musi byc w zakresie 0-999 s")
    if frequency not in (50, 60):
        errors.append("Frequency musi wynosic 50 lub 60 Hz")
    if continuity != "OFF":
        errors.append("Continuity musi pozostac OFF dla tego profilu")

    if errors:
        raise SafetyValidationError(" | ".join(errors))

    return {
        "type": test_type,
        "voltage": int(round(voltage)),
        "limit_high": limit_high,
        "limit_low": limit_low,
        "presence_min_current": presence_min,
        "ramp_time": ramp_time,
        "dwell": dwell,
        "ramp_dn": ramp_dn,
        "arc_sense": arc_sense,
        "frequency": frequency,
        "continuity": continuity,
    }


def validate_timeout_for_profile(timeout_value: Any, profile: Mapping[str, Any]) -> int:
    """Sprawdza, czy limit czasu nie przerwie prawidlowego profilu testowego."""
    timeout = validate_test_timeout(timeout_value)
    normalized = validate_acw_profile(profile)
    total = (
        float(normalized["ramp_time"])
        + float(normalized["dwell"])
        + float(normalized["ramp_dn"])
    )
    required = int(math.ceil(max(total + 10.0, 15.0)))
    if timeout < required:
        raise SafetyValidationError(
            f"TEST_TIMEOUT musi wynosic co najmniej {required} s dla profilu "
            f"o czasie {total:.1f} s"
        )
    return timeout


def validate_pass_evidence(
    *,
    result: str,
    terminal_status: str | None,
    target_voltage: float,
    effective_low_ma: float,
    high_limit_ma: float,
    final_voltage: float,
    final_current_ma: float,
    cycle_max_voltage: float,
    in_range_samples: int,
    overcurrent_seen: bool,
) -> None:
    """Odrzuca PASS bez dowodow z biezacego cyklu."""
    if str(result).upper() != "PASS":
        return

    if terminal_status == "FAIL":
        raise SafetyValidationError(
            "Odrzucono PASS - status biezacego cyklu wskazal FAIL"
        )

    effective_voltage = max(float(final_voltage), float(cycle_max_voltage))
    if effective_voltage < float(target_voltage) * 0.90:
        raise SafetyValidationError(
            "Odrzucono PASS - nie potwierdzono wymaganego napiecia testowego"
        )

    if int(in_range_samples) < 2:
        raise SafetyValidationError(
            "Odrzucono PASS - brak co najmniej dwoch pomiarow obciazenia "
            "w prawidlowym zakresie podczas biezacego cyklu"
        )

    if overcurrent_seen:
        raise SafetyValidationError(
            "Odrzucono PASS - podczas biezacego cyklu wykryto przekroczenie Max Limit"
        )

    if not float(effective_low_ma) <= float(final_current_ma) <= float(high_limit_ma):
        raise SafetyValidationError(
            f"Odrzucono PASS - prad koncowy {float(final_current_ma):.3f} mA "
            f"jest poza zakresem {float(effective_low_ma):.3f}-"
            f"{float(high_limit_ma):.3f} mA"
        )
