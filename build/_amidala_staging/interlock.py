# interlock.py
"""Monitor interlocka Arduino — klapa otwarta/zamknięta.

Monitor działa fail-safe: brak prawidłowego komunikatu OPEN/CLOSED przez określony
czas jest traktowany jako utrata interlocka i zgłaszany do aplikacji jako ``None``.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import serial

from safety_rules import validate_interlock_settings


class InterlockMonitor:
    # Firmware stanowiska wysyla wyłącznie te dwa komunikaty.
    # Inne wartosci sa odrzucane zamiast zgadywania stanu klapy.
    CLOSED_SIGNALS = {"CLOSED"}
    OPEN_SIGNALS = {"OPEN"}

    def __init__(
        self,
        port: str = "COM5",
        baudrate: int = 9600,
        heartbeat_timeout: float = 2.0,
    ):
        self.port, self.baudrate, _ = validate_interlock_settings(
            port, baudrate, True
        )
        self.heartbeat_timeout = max(0.5, float(heartbeat_timeout))
        self.serial: Optional[serial.Serial] = None
        self.connected = False

        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._on_change: Optional[Callable[[Optional[bool]], None]] = None
        self._last_state: Optional[bool] = None
        self._last_message_time: Optional[float] = None
        self._loss_reported = False

    def connect(self) -> bool:
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.25,
            )
            time.sleep(1.5)  # reset Arduino po otwarciu portu
            self.serial.reset_input_buffer()
            self.connected = True
            self._last_state = None
            self._last_message_time = time.monotonic()
            self._loss_reported = False
            print(f"[INTERLOCK] Połączono: {self.port} @ {self.baudrate}")
            return True
        except Exception as exc:
            print(f"[INTERLOCK] Błąd połączenia: {exc}")
            try:
                if self.serial and self.serial.is_open:
                    self.serial.close()
            except Exception:
                pass
            self.connected = False
            return False

    def disconnect(self):
        self._stop_flag.set()
        self._on_change = None
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
        finally:
            self.connected = False
            thread = self._thread
            if (
                thread
                and thread.is_alive()
                and thread is not threading.current_thread()
            ):
                thread.join(timeout=0.5)
            print("[INTERLOCK] Rozłączono")

    def set_on_change(self, callback: Callable[[Optional[bool]], None]):
        self._on_change = callback

    def start_monitoring(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _notify(self, state: Optional[bool]):
        if not self._on_change:
            return
        try:
            self._on_change(state)
        except Exception as callback_error:
            print(f"[INTERLOCK] Błąd callback: {callback_error}")

    def _report_connection_loss(self, reason: str):
        if self._loss_reported:
            return
        self._loss_reported = True
        self.connected = False
        self._last_state = None
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
        except Exception:
            pass
        print(f"[INTERLOCK] Utrata komunikacji: {reason}")
        self._notify(None)

    def _monitor_loop(self):
        consecutive_errors = 0
        max_errors = 5

        while not self._stop_flag.is_set():
            try:
                if not self.serial or not self.serial.is_open:
                    raise RuntimeError("Port zamknięty")

                raw = self.serial.readline()
                now = time.monotonic()

                if not raw:
                    if (
                        self._last_message_time is not None
                        and now - self._last_message_time > self.heartbeat_timeout
                    ):
                        self._report_connection_loss(
                            f"brak danych przez {self.heartbeat_timeout:.1f} s"
                        )
                        break
                    continue

                message = raw.decode("ascii", errors="ignore").strip().upper()
                if not message:
                    continue

                if message in self.CLOSED_SIGNALS:
                    new_state = True
                elif message in self.OPEN_SIGNALS:
                    new_state = False
                else:
                    print(f"[INTERLOCK] Nieznany sygnał: '{message}'")
                    continue

                self._last_message_time = now
                self.connected = True
                self._loss_reported = False
                consecutive_errors = 0

                # Arduino może wysyłać ten sam stan wiele razy na sekundę.
                # Callback wykonujemy wyłącznie przy rzeczywistej zmianie.
                if new_state == self._last_state:
                    continue

                self._last_state = new_state
                state_text = "CLOSED" if new_state else "OPEN"
                print(f"[INTERLOCK] Zmiana stanu: '{state_text}'")
                self._notify(new_state)

            except Exception as exc:
                if self._stop_flag.is_set():
                    break

                consecutive_errors += 1
                print(f"[INTERLOCK] Błąd pętli ({consecutive_errors}): {exc}")

                if consecutive_errors >= max_errors:
                    self._report_connection_loss(
                        f"{consecutive_errors} kolejnych błędów portu"
                    )
                    break

                time.sleep(0.5)

    def is_closed(self) -> Optional[bool]:
        return self._last_state
