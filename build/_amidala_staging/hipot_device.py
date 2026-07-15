# hipot_device.py
"""Komunikacja z urządzeniem Hi-Pot Chroma 19052 — Amidala.

Wersja odporna na mieszanie odpowiedzi RS232:
- każda transakcja jest chroniona blokadą,
- przed zapytaniem usuwane są stare dane z bufora,
- odpowiedzi są czytane po jednej linii,
- status, pomiary i wynik mają walidację oraz ponowienie zapytania.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Callable, Dict, Optional, Tuple

import serial


OVERFLOW = 9.0e37
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
_INT_RE = re.compile(r"^[+-]?\d+$")


class ChromaHiPotDevice:
    def __init__(self, port: str = "COM6", baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self.connected = False
        self._io_lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # POŁĄCZENIE
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.20,
                write_timeout=2.0,
            )
            time.sleep(0.5)
            self.connected = True
            self._clear_input()

            response = self.query("*IDN?", timeout=2.0, retries=2)
            if not response:
                self.disconnect(send_stop=False)
                return False

            print(f"Połączono z: {response}")
            self.send_command("SYST:KLOC OFF")
            time.sleep(0.15)
            err = self.query("SYST:ERR?", timeout=2.0, retries=2)
            print(f"[KEYLOCK] SYST:KLOC OFF -> '{err}'")
            return True

        except Exception as exc:
            print(f"Błąd połączenia: {exc}")
            self.connected = False
            return False

    def disconnect(self, send_stop: bool = True):
        with self._io_lock:
            try:
                if self.serial and self.serial.is_open:
                    if send_stop:
                        try:
                            self._write_unlocked("SAFEty:STOP")
                        except Exception:
                            pass
                    self.serial.close()
            finally:
                self.connected = False

    # ------------------------------------------------------------------ #
    # KOMUNIKACJA
    # ------------------------------------------------------------------ #
    def _require_connection(self):
        if not self.connected or not self.serial or not self.serial.is_open:
            raise RuntimeError("Urządzenie nie jest połączone")

    def _clear_input(self):
        if self.serial and self.serial.is_open:
            self.serial.reset_input_buffer()

    def _write_unlocked(self, command: str):
        self._require_connection()
        command = command.rstrip("\r\n") + "\n"
        self.serial.write(command.encode("ascii"))
        self.serial.flush()

    def send_command(self, command: str):
        """Wysyła komendę, która nie zwraca odpowiedzi."""
        with self._io_lock:
            self._write_unlocked(command)
            time.sleep(0.08)

    def _read_one_line_unlocked(self, timeout: float = 2.0) -> Optional[str]:
        """Czyta dokładnie jedną niepustą linię odpowiedzi."""
        self._require_connection()
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            raw = self.serial.readline()
            if not raw:
                continue

            text = raw.decode("ascii", errors="ignore").strip()
            if text:
                return text

        return None

    def read_response(self, timeout: float = 2.0) -> Optional[str]:
        with self._io_lock:
            return self._read_one_line_unlocked(timeout)

    def query(
        self,
        command: str,
        timeout: float = 2.0,
        retries: int = 1,
        validator: Optional[Callable[[str], bool]] = None,
    ) -> Optional[str]:
        """Wykonuje atomową transakcję: wyczyść bufor -> wyślij -> odczytaj linię.

        Czyszczenie bufora przed każdym zapytaniem usuwa spóźnioną odpowiedź z
        poprzedniej komendy. Dzięki blokadzie STOP lub inne wywołanie z GUI nie
        może wejść pomiędzy wysłanie zapytania i odczyt odpowiedzi.
        """
        attempts = max(1, retries)

        with self._io_lock:
            for attempt in range(attempts):
                self._clear_input()
                self._write_unlocked(command)
                response = self._read_one_line_unlocked(timeout)

                if response is not None and (
                    validator is None or validator(response)
                ):
                    return response

                if response is not None:
                    print(
                        f"[RS232] Odrzucono odpowiedź dla '{command}': "
                        f"'{response}'"
                    )

                if attempt + 1 < attempts:
                    time.sleep(0.12)

        return None

    @staticmethod
    def _parse(response: Optional[str]) -> list[str]:
        if not response:
            return []
        separator = ";" if ";" in response else ","
        return [part.strip() for part in response.split(separator)]

    @staticmethod
    def _is_float(value: str) -> bool:
        return bool(_FLOAT_RE.fullmatch(value.strip()))

    @staticmethod
    def _is_integer(value: str) -> bool:
        return bool(_INT_RE.fullmatch(value.strip()))

    # ------------------------------------------------------------------ #
    # KONFIGURACJA ACW
    # ------------------------------------------------------------------ #
    def configure_acw(self, profile: dict) -> bool:
        """Programuje profil ACW i fail-safe weryfikuje odpowiedzi urządzenia."""
        step = 1
        i_high = float(profile["limit_high"]) / 1000.0
        i_low = float(profile["limit_low"]) / 1000.0

        commands = [
            f"SAFEty:STEP{step}:AC:LEVel {profile['voltage']}",
            f"SAFEty:STEP{step}:AC:LIMit:HIGH {i_high}",
            f"SAFEty:STEP{step}:AC:LIMit:LOW {i_low}",
            f"SAFEty:STEP{step}:AC:TIME:TEST {profile['dwell']}",
            f"SAFEty:STEP{step}:AC:TIME:RAMP {profile['ramp_time']}",
            f"SAFEty:STEP{step}:AC:TIME:FALL {profile['ramp_dn']}",
        ]

        # Firmware 5.14 zwraca -113 dla używanych wcześniej nagłówków
        # SAFEty:STEP1:AC:FREQ oraz SAFEty:STEP1:AC:ARC. Nie wysyłamy ich,
        # dopóki nie zostanie potwierdzona właściwa składnia z manuala 19052.
        for command in commands:
            self.send_command(command)
            time.sleep(0.10)
            error = self.query("SYST:ERR?", timeout=2.0, retries=2)
            print(f"    {command}")
            print(f"    ERR: '{error}'")

            if not error:
                raise RuntimeError(
                    f"Brak potwierdzenia po komendzie konfiguracji: {command}"
                )
            if not error.lstrip().startswith("+0"):
                raise RuntimeError(
                    f"Chroma odrzuciła komendę '{command}': {error}"
                )

        steps = self.query(
            "SAFEty:SNUMber?",
            timeout=2.0,
            retries=2,
            validator=lambda response: bool(self._parse(response))
            and self._is_float(self._parse(response)[0]),
        )
        if not steps:
            raise RuntimeError("Brak potwierdzenia liczby kroków po konfiguracji")

        count = int(float(self._parse(steps)[0]))
        if count < 1:
            raise RuntimeError("Po konfiguracji Chroma nie ma aktywnego kroku testowego")
        return True

    def start_test(self) -> bool:
        try:
            with self._io_lock:
                self._clear_input()
                self._write_unlocked("SYST:KLOC OFF")
                time.sleep(0.08)
                self._write_unlocked("SAFEty:STARt")
                time.sleep(0.25)

            error = self.query("SYST:ERR?", timeout=2.0, retries=2)
            print(f"[START] SYST:ERR? = '{error}'")
            return bool(error) and error.lstrip().startswith("+0")
        except Exception as exc:
            print(f"Błąd rozpoczęcia testu: {exc}")
            return False

    def stop_test(self) -> bool:
        try:
            self.send_command("SAFEty:STOP")
            return True
        except Exception as exc:
            print(f"Błąd zatrzymania testu: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # STATUS I POMIARY
    # ------------------------------------------------------------------ #
    @staticmethod
    def _valid_status(response: str) -> bool:
        return response.strip().upper() in {
            "PASS",
            "FAIL",
            "STOP",
            "STOPPED",
            "TESTING",
            "RUNNING",
            "READY",
            "WAIT",
        }

    def get_status(self) -> str:
        """Zwraca stan testu albo COMM_ERROR po braku poprawnej odpowiedzi."""
        try:
            response = self.query(
                "SAFEty:STATus?",
                timeout=1.5,
                retries=2,
                validator=self._valid_status,
            )
            return response.strip().upper() if response else "COMM_ERROR"
        except Exception as exc:
            print(f"Błąd pobierania statusu: {exc}")
            return "COMM_ERROR"

    def _valid_measurement(self, response: str) -> bool:
        parts = self._parse(response)
        return (
            len(parts) >= 5
            and self._is_float(parts[2])
            and self._is_float(parts[3])
            and self._is_float(parts[4])
        )

    def read_measurements(self) -> Optional[Dict]:
        try:
            response = self.query(
                "SAFEty:FETCh? STEP,MODE,OMET,MMET,RMET",
                timeout=1.5,
                retries=2,
                validator=self._valid_measurement,
            )
            if not response:
                return None

            parts = self._parse(response)
            raw_v = float(parts[2])
            raw_i = float(parts[3])
            raw_r = float(parts[4])
            return {
                "step": parts[0],
                "mode": parts[1],
                "output_voltage": raw_v if raw_v < OVERFLOW else 0.0,
                "measure_current": raw_i if raw_i < OVERFLOW else 0.0,
                "real_current": raw_r if raw_r < OVERFLOW else 0.0,
            }
        except Exception as exc:
            print(f"Błąd odczytu pomiarów: {exc}")
            return None

    def _query_float(self, command: str) -> Optional[float]:
        response = self.query(
            command,
            timeout=2.0,
            retries=3,
            validator=self._is_float,
        )
        return float(response) if response is not None else None

    def get_test_result(self) -> Tuple[str, Dict]:
        try:
            # Dajemy urządzeniu chwilę na zapisanie rejestru LAST i usuwamy
            # ostatnią spóźnioną odpowiedź z pętli pomiarowej.
            time.sleep(0.30)
            with self._io_lock:
                self._clear_input()

            judgment = self.query(
                "SAFEty:RESult:LAST:JUDG?",
                timeout=2.0,
                retries=3,
                validator=self._is_integer,
            )
            output_v = self._query_float("SAFEty:RESult:LAST:OMET?")
            measured_i = self._query_float("SAFEty:RESult:LAST:MMET?")
            real_i = self._query_float("SAFEty:RESult:LAST:RMET?")

            print(f"[WYNIK] judgment_code = '{judgment}'")
            print(f"[WYNIK] output_v      = '{output_v}'")
            print(f"[WYNIK] measured_i    = '{measured_i}'")
            print(f"[WYNIK] real_i        = '{real_i}'")

            if judgment is None:
                raise RuntimeError("Brak poprawnego kodu wyniku JUDG")

            judgment_code = str(int(judgment))
            result = "PASS" if judgment_code == "116" else "FAIL"
            error_code = "" if result == "PASS" else judgment_code

            raw_v = output_v or 0.0
            raw_mi = measured_i or 0.0
            raw_ri = real_i or 0.0

            data = {
                "judgment_code": judgment_code,
                "error_code": error_code,
                "output_voltage": raw_v if raw_v < OVERFLOW else 0.0,
                "measured_current": (
                    raw_mi * 1000.0 if raw_mi < OVERFLOW else 0.0
                ),
                "real_current": (
                    raw_ri * 1000.0 if raw_ri < OVERFLOW else 0.0
                ),
            }
            return result, data

        except Exception as exc:
            print(f"Błąd pobierania wyniku: {exc}")
            return "UNKNOWN", {}

    # ------------------------------------------------------------------ #
    # CZYSZCZENIE KROKÓW
    # ------------------------------------------------------------------ #
    def clear_steps(self) -> bool:
        """Usuwa wszystkie kroki i zgłasza błąd zamiast go ukrywać."""
        response = self.query("SAFEty:SNUMber?", timeout=2.0, retries=2)
        parts = self._parse(response)
        if not parts or not self._is_float(parts[0]):
            raise RuntimeError("Nie udało się odczytać liczby kroków Chromy")

        count = int(float(parts[0]))
        for step in range(count, 0, -1):
            self.send_command(f"SAFEty:STEP{step}:DELete")
            time.sleep(0.10)
            error = self.query("SYST:ERR?", timeout=2.0, retries=2)
            if not error or not error.lstrip().startswith("+0"):
                raise RuntimeError(
                    f"Nie udało się usunąć kroku {step}: {error or 'brak odpowiedzi'}"
                )
        return True
