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

from safety_rules import (
    MIN_PRESENCE_CURRENT_MA,
    validate_acw_profile,
    validate_rs232_settings,
)


OVERFLOW = 9.0e37
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
_INT_RE = re.compile(r"^[+-]?\d+$")


class ChromaHiPotDevice:
    def __init__(
        self,
        port: str = "COM6",
        baudrate: int = 9600,
        parity: str = "NONE",
        flow_control: str = "NONE",
    ):
        self.port, self.baudrate, self.parity, self.flow_control = validate_rs232_settings(
            port, baudrate, parity, flow_control
        )
        self.serial: Optional[serial.Serial] = None
        self.connected = False
        self._io_lock = threading.RLock()
        self._cycle_id = 0
        self._cycle_active_confirmed = False
        self._cycle_started_monotonic: Optional[float] = None
        self._local_keys_locked = False

    # ------------------------------------------------------------------ #
    # POŁĄCZENIE
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        try:
            parity_map = {
                "NONE": serial.PARITY_NONE,
                "ODD": serial.PARITY_ODD,
                "EVEN": serial.PARITY_EVEN,
            }
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=parity_map[self.parity],
                stopbits=serial.STOPBITS_ONE,
                timeout=0.20,
                write_timeout=2.0,
                rtscts=self.flow_control == "RTS/CTS",
                xonxoff=self.flow_control == "XON/XOFF",
            )
            time.sleep(0.5)
            self.connected = True
            self._clear_input()

            response = self.query("*IDN?", timeout=2.0, retries=2)
            if not response:
                self.disconnect(send_stop=False)
                return False

            idn_parts = [part.strip() for part in response.split(",")]
            if (
                len(idn_parts) < 2
                or idn_parts[0].upper() != "CHROMA"
                or idn_parts[1] != "19052"
            ):
                print(f"[IDN] Nieoczekiwane urządzenie: {response}")
                self.disconnect(send_stop=False)
                return False

            print(f"Połączono z: {response}")
            # Podczas sterowania z aplikacji blokujemy lokalne klawisze panelu,
            # aby ustawienia nie mogly zostac zmienione pomiedzy konfiguracja a START.
            self.send_command("SYST:KLOC ON")
            time.sleep(0.15)
            err = self.query("SYST:ERR?", timeout=2.0, retries=2)
            state = self.query(
                "SYST:KLOC?",
                timeout=2.0,
                retries=2,
                validator=self._is_integer,
            )
            print(f"[KEYLOCK] SYST:KLOC ON -> ERR='{err}', STATE='{state}'")
            if (
                not err
                or not err.lstrip().startswith("+0")
                or state is None
                or int(state) != 1
            ):
                self.disconnect(send_stop=False)
                return False
            self._local_keys_locked = True
            return True

        except Exception as exc:
            print(f"Błąd połączenia: {exc}")
            try:
                if self.serial and self.serial.is_open:
                    self.serial.close()
            except Exception:
                pass
            self.connected = False
            return False

    def disconnect(self, send_stop: bool = True):
        with self._io_lock:
            try:
                if self.serial and self.serial.is_open:
                    if send_stop:
                        try:
                            self._write_unlocked("SAFEty:STOP")
                            time.sleep(0.08)
                        except Exception:
                            pass
                    # Po zakonczeniu pracy oddajemy obsluge panelowi lokalnemu.
                    try:
                        self._write_unlocked("SYST:KLOC OFF")
                        time.sleep(0.08)
                    except Exception:
                        pass
                    self.serial.close()
            finally:
                self._local_keys_locked = False
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
    @staticmethod
    def _assert_close(
        label: str,
        actual: Optional[float],
        expected: float,
        tolerance: float,
    ) -> None:
        if actual is None:
            raise RuntimeError(f"Brak odczytu zwrotnego parametru: {label}")
        if abs(float(actual) - float(expected)) > float(tolerance):
            raise RuntimeError(
                f"Odczyt zwrotny {label} nie zgadza sie z konfiguracja: "
                f"oczekiwano {expected}, odczytano {actual}"
            )

    def _verify_acw_readback(
        self,
        *,
        step: int,
        voltage: float,
        i_high: float,
        i_low: float,
        dwell: float,
        ramp_time: float,
        ramp_dn: float,
    ) -> None:
        """Odczytuje z Chromy parametry, ktore aplikacja wlasnie ustawila."""
        readback = {
            "Voltage": self._query_float(f"SAFEty:STEP{step}:AC?"),
            "Max Limit": self._query_float(f"SAFEty:STEP{step}:AC:LIMit?"),
            "Min Limit": self._query_float(f"SAFEty:STEP{step}:AC:LIMit:LOW?"),
            "Dwell": self._query_float(f"SAFEty:STEP{step}:AC:TIME?"),
            "Ramp Time": self._query_float(f"SAFEty:STEP{step}:AC:TIME:RAMP?"),
            "Ramp Down": self._query_float(f"SAFEty:STEP{step}:AC:TIME:FALL?"),
        }
        self._assert_close("Voltage", readback["Voltage"], voltage, max(1.0, voltage * 0.001))
        self._assert_close("Max Limit", readback["Max Limit"], i_high, max(1e-6, i_high * 0.01))
        self._assert_close("Min Limit", readback["Min Limit"], i_low, max(1e-6, i_low * 0.01))
        self._assert_close("Dwell", readback["Dwell"], dwell, 0.05)
        self._assert_close("Ramp Time", readback["Ramp Time"], ramp_time, 0.05)
        self._assert_close("Ramp Down", readback["Ramp Down"], ramp_dn, 0.05)
        print(
            "[VERIFY] Profil ACW odczytany zwrotnie: "
            f"{readback['Voltage']:.1f} V, "
            f"LOW {readback['Min Limit'] * 1000.0:.3f} mA, "
            f"HIGH {readback['Max Limit'] * 1000.0:.3f} mA, "
            f"RAMP/TEST/FALL {readback['Ramp Time']:.2f}/"
            f"{readback['Dwell']:.2f}/{readback['Ramp Down']:.2f} s"
        )

    def configure_acw(self, profile: dict) -> bool:
        """Programuje profil ACW i fail-safe weryfikuje odpowiedzi urządzenia."""
        profile = validate_acw_profile(profile)
        step = 1
        i_high = float(profile["limit_high"]) / 1000.0
        # Limit obecności jest niezależnym zabezpieczeniem przed pustym fixture.
        # Chroma dostaje wyższy z: wymaganego Low Limit i progu obecności.
        presence_min_ma = float(profile.get("presence_min_current", MIN_PRESENCE_CURRENT_MA))
        i_low_ma = max(float(profile["limit_low"]), presence_min_ma)
        i_low = i_low_ma / 1000.0
        print(f"[CONFIG] Efektywny LOW / próg obecności: {i_low_ma:.3f} mA")

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

        self._verify_acw_readback(
            step=step,
            voltage=float(profile["voltage"]),
            i_high=i_high,
            i_low=i_low,
            dwell=float(profile["dwell"]),
            ramp_time=float(profile["ramp_time"]),
            ramp_dn=float(profile["ramp_dn"]),
        )
        return True

    def start_test(self) -> bool:
        """Uruchamia NOWY cykl i potwierdza, że Chroma faktycznie zaczęła test.

        Sam brak błędu po komendzie START nie wystarcza. Poprzedni wynik LAST może
        nadal zawierać PASS, dlatego wymagamy stanu TESTING/RUNNING albo świeżego
        pomiaru napięcia powyżej 50 V.
        """
        self._cycle_active_confirmed = False
        self._cycle_started_monotonic = None

        try:
            # Uporządkuj stan po poprzednim cyklu. STOP nie kasuje LAST.
            with self._io_lock:
                self._clear_input()
                self._write_unlocked("SAFEty:STOP")
                time.sleep(0.20)
            stop_error = self.query("SYST:ERR?", timeout=2.0, retries=2)
            if not stop_error or not stop_error.lstrip().startswith("+0"):
                print(f"[START] STOP przed cyklem odrzucony: '{stop_error}'")
                return False

            # Pomiar bazowy po STOP chroni przed uznaniem starego FETCh/OMET
            # za dowod nowego narastania napiecia.
            baseline = self.read_measurements()
            baseline_valid = baseline is not None
            baseline_voltage = (
                float(baseline.get("output_voltage", 0.0)) if baseline else 0.0
            )

            with self._io_lock:
                self._clear_input()
                self._write_unlocked("SYST:KLOC ON")
                time.sleep(0.08)
                command_started = time.monotonic()
                self._write_unlocked("SAFEty:STARt")
                time.sleep(0.20)

            error = self.query("SYST:ERR?", timeout=2.0, retries=2)
            keylock = self.query(
                "SYST:KLOC?",
                timeout=2.0,
                retries=2,
                validator=self._is_integer,
            )
            print(f"[START] SYST:ERR? = '{error}', KLOC='{keylock}'")
            if (
                not error
                or not error.lstrip().startswith("+0")
                or keylock is None
                or int(keylock) != 1
            ):
                self.stop_test()
                return False
            self._local_keys_locked = True

            # Najważniejsze zabezpieczenie przed odczytem starego PASS.
            deadline = time.monotonic() + 3.0
            active_confirmed = False
            while time.monotonic() < deadline:
                status = self.get_status()
                if status in ("TESTING", "RUNNING"):
                    active_confirmed = True
                    break

                measurement = self.read_measurements()
                if measurement:
                    voltage = float(measurement.get("output_voltage", 0.0))
                    fresh_voltage_rise = baseline_valid and (
                        (baseline_voltage < 50.0 and voltage >= 50.0)
                        or voltage >= baseline_voltage + 50.0
                    )
                    if fresh_voltage_rise:
                        active_confirmed = True
                        break

                time.sleep(0.10)

            if not active_confirmed:
                print(
                    "[START] Brak potwierdzenia nowego aktywnego cyklu — "
                    "odrzucam możliwy stary wynik LAST"
                )
                self.stop_test()
                return False

            self._cycle_id += 1
            self._cycle_active_confirmed = True
            self._cycle_started_monotonic = command_started
            print(f"[START] Potwierdzono nowy cykl #{self._cycle_id}")
            return True

        except Exception as exc:
            print(f"Błąd rozpoczęcia testu: {exc}")
            try:
                self.stop_test()
            except Exception:
                pass
            return False

    def stop_test(self) -> bool:
        try:
            self.send_command("SAFEty:STOP")
            return True
        except Exception as exc:
            print(f"Błąd zatrzymania testu: {exc}")
            return False
        finally:
            self._cycle_active_confirmed = False
            self._cycle_started_monotonic = None

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
        """Pobiera wynik tylko dla cyklu potwierdzonego po bieżącym START."""
        try:
            if not self._cycle_active_confirmed or self._cycle_started_monotonic is None:
                raise RuntimeError(
                    "Brak potwierdzonego nowego cyklu — wynik LAST może być stary"
                )

            cycle_id = self._cycle_id
            cycle_elapsed = time.monotonic() - self._cycle_started_monotonic

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

            print(f"[WYNIK] cycle_id     = '{cycle_id}'")
            print(f"[WYNIK] cycle_elapsed= '{cycle_elapsed:.3f}'")
            print(f"[WYNIK] judgment_code= '{judgment}'")
            print(f"[WYNIK] output_v     = '{output_v}'")
            print(f"[WYNIK] measured_i   = '{measured_i}'")
            print(f"[WYNIK] real_i       = '{real_i}'")

            if judgment is None:
                raise RuntimeError("Brak poprawnego kodu wyniku JUDG")
            if output_v is None or measured_i is None:
                raise RuntimeError(
                    "Brak kompletnych pomiarów OMET/MMET dla bieżącego cyklu"
                )

            judgment_value = int(judgment)
            if judgment_value <= 0 or judgment_value in {112, 115}:
                raise RuntimeError(
                    f"Kod JUDG {judgment_value} nie jest końcowym wynikiem produktu"
                )
            judgment_code = str(judgment_value)
            result = "PASS" if judgment_code == "116" else "FAIL"
            error_code = "" if result == "PASS" else judgment_code

            raw_v = output_v
            raw_mi = measured_i
            raw_ri = real_i if real_i is not None else 0.0

            data = {
                "fresh_cycle": True,
                "cycle_id": cycle_id,
                "cycle_elapsed": cycle_elapsed,
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
        finally:
            # Wynik może zostać odczytany tylko raz dla tego START.
            self._cycle_active_confirmed = False
            self._cycle_started_monotonic = None

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

