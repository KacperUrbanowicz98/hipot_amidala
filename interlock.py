# interlock.py
"""Monitor interloka Arduino — klapa otwarta/zamknięta"""
import serial
import threading
import time
from typing import Callable, Optional


class InterlockMonitor:

    CLOSED_SIGNALS = {"CLOSED", "1", "TRUE", "CLOSE", "LOCK"}
    OPEN_SIGNALS   = {"OPEN",   "0", "FALSE", "UNLOCK"}

    def __init__(self, port: str = "COM5", baudrate: int = 9600):
        self.port      = port
        self.baudrate  = baudrate
        self.serial    = None
        self.connected = False

        self._thread:    Optional[threading.Thread] = None
        self._stop_flag  = threading.Event()
        self._on_change: Optional[Callable] = None
        self._last_state: Optional[bool]    = None

    # ------------------------------------------------------------------ #
    # POŁĄCZENIE                                                           #
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2)
            time.sleep(1.5)           # Arduino reset po otwarciu portu
            self.serial.flushInput()
            self.connected = True
            print(f"[INTERLOCK] Połączono: {self.port} @ {self.baudrate}")
            return True
        except Exception as e:
            print(f"[INTERLOCK] Błąd połączenia: {e}")
            self.connected = False
            return False

    def disconnect(self):
        self._stop_flag.set()
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.connected = False
        print("[INTERLOCK] Rozłączono")

    # ------------------------------------------------------------------ #
    # MONITORING                                                           #
    # ------------------------------------------------------------------ #
    def set_on_change(self, callback: Callable):
        """callback(closed: bool | None)"""
        self._on_change = callback

    def start_monitoring(self):
        self._stop_flag.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self):
        consecutive_errors = 0
        MAX_ERRORS         = 5

        while not self._stop_flag.is_set():
            try:
                if not self.serial or not self.serial.is_open:
                    raise Exception("Port zamknięty")

                if self.serial.in_waiting > 0:
                    raw = self.serial.readline()
                    msg = raw.decode("ascii", errors="ignore").strip().upper()

                    if not msg:
                        time.sleep(0.05)
                        continue

                    print(f"[INTERLOCK] Odebrano: '{msg}'")
                    consecutive_errors = 0

                    if msg in self.CLOSED_SIGNALS:
                        new_state = True
                    elif msg in self.OPEN_SIGNALS:
                        new_state = False
                    else:
                        print(f"[INTERLOCK] Nieznany sygnał: '{msg}'")
                        time.sleep(0.05)
                        continue

                    if new_state != self._last_state:
                        self._last_state = new_state
                        if self._on_change:
                            try:
                                self._on_change(new_state)
                            except Exception as cb_err:
                                print(f"[INTERLOCK] Błąd callback: {cb_err}")

                time.sleep(0.05)

            except Exception as e:
                consecutive_errors += 1
                print(f"[INTERLOCK] Błąd pętli ({consecutive_errors}): {e}")

                if consecutive_errors >= MAX_ERRORS:
                    print("[INTERLOCK] Za dużo błędów — zatrzymuję monitoring")
                    self.connected = False
                    if self._on_change:
                        try:
                            self._on_change(None)
                        except Exception:
                            pass
                    break

                time.sleep(0.5)

    # ------------------------------------------------------------------ #
    # STAN BIEŻĄCY                                                         #
    # ------------------------------------------------------------------ #
    def is_closed(self) -> Optional[bool]:
        return self._last_state