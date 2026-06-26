# hipot_device.py
"""Moduł komunikacji z urządzeniem Hi-Pot Chroma — Amidala"""
import serial
import time
from typing import Optional, Tuple, Dict

OVERFLOW = 9.0e+37  # Chroma zwraca tę wartość gdy brak pomiaru


class ChromaHiPotDevice:

    def __init__(self, port: str = "COM6", baudrate: int = 9600):
        self.port      = port
        self.baudrate  = baudrate
        self.serial    = None
        self.connected = False

    # ------------------------------------------------------------------ #
    # POŁĄCZENIE                                                           #
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2
            )
            time.sleep(0.5)
            self.connected = True

            self.send_command("*IDN?")
            response = self.read_response()
            if response:
                print(f"Połączono z: {response}")
                self.send_command("SYST:KLOC OFF")
                time.sleep(0.3)
                err = self.query("SYST:ERR?")
                print(f"[KEYLOCK] SYST:KLOC OFF → '{err}'")
                return True
            return False

        except Exception as e:
            print(f"Błąd połączenia: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.serial and self.serial.is_open:
            self.stop_test()
            self.serial.close()
        self.connected = False

    # ------------------------------------------------------------------ #
    # KOMUNIKACJA                                                          #
    # ------------------------------------------------------------------ #
    def send_command(self, command: str):
        if not self.connected or not self.serial:
            raise Exception("Urządzenie nie jest połączone!")
        if not command.endswith('\n'):
            command += '\n'
        self.serial.write(command.encode('ascii'))
        time.sleep(0.1)

    def read_response(self, timeout: float = 2.0) -> Optional[str]:
        if not self.connected or not self.serial:
            return None
        start_time = time.time()
        response   = ""
        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting > 0:
                chunk = self.serial.read(
                    self.serial.in_waiting).decode('ascii', errors='ignore')
                response += chunk
                if '\n' in response or '\r' in response:
                    break
            time.sleep(0.05)
        return response.strip() if response else None

    def query(self, command: str) -> Optional[str]:
        self.send_command(command)
        return self.read_response()

    def _parse(self, response: Optional[str]) -> list:
        if not response:
            return []
        sep = ';' if ';' in response else ','
        return [p.strip() for p in response.split(sep)]

    # ------------------------------------------------------------------ #
    # KONFIGURACJA ACW — dedykowana dla Amidali                           #
    # ------------------------------------------------------------------ #
    def configure_acw(self, profile: dict):
        """
        Konfiguruje krok 1 jako ACW wg profilu z Config.TEST_PROFILE.

        Oczekiwane klucze profilu:
            voltage    [V]   np. 4000
            limit_high [mA]  np. 2.50
            limit_low  [mA]  np. 0.050
            ramp_time  [s]   np. 5.0
            dwell      [s]   np. 1.0  (test time)
            ramp_dn    [s]   np. 0.0
            arc_sense        np. 0
            frequency  [Hz]  np. 60
        """
        step = 1

        # Prądy: mA → A
        i_high = profile['limit_high'] / 1000.0
        i_low  = profile['limit_low']  / 1000.0

        cmds = [
            f"SAFEty:STEP{step}:AC:LEVel {profile['voltage']}",
            f"SAFEty:STEP{step}:AC:LIMit:HIGH {i_high}",
            f"SAFEty:STEP{step}:AC:LIMit:LOW {i_low}",
            f"SAFEty:STEP{step}:AC:TIME:TEST {profile['dwell']}",
            f"SAFEty:STEP{step}:AC:TIME:RAMP {profile['ramp_time']}",
            f"SAFEty:STEP{step}:AC:TIME:FALL {profile['ramp_dn']}",
            f"SAFEty:STEP{step}:AC:FREQ {profile['frequency']}",
            f"SAFEty:STEP{step}:AC:ARC {profile['arc_sense']}",
        ]

        for cmd in cmds:
            self.send_command(cmd)
            time.sleep(0.15)
            err = self.query("SYST:ERR?")
            print(f"    {cmd}")
            print(f"    ERR: '{err}'")

    # ------------------------------------------------------------------ #
    # START / STOP                                                         #
    # ------------------------------------------------------------------ #
    def start_test(self) -> bool:
        try:
            self.send_command("SYST:KLOC OFF")
            self.send_command("SAFEty:STARt")
            time.sleep(0.3)
            err = self.query("SYST:ERR?")
            print(f"[START] SYST:ERR? = '{err}'")
            return "-203" not in str(err)
        except Exception as e:
            print(f"Błąd rozpoczęcia testu: {e}")
            return False

    def stop_test(self) -> bool:
        try:
            self.send_command("SAFEty:STOP")
            return True
        except Exception as e:
            print(f"Błąd zatrzymania testu: {e}")
            return False

    # ------------------------------------------------------------------ #
    # STATUS I POMIARY                                                     #
    # ------------------------------------------------------------------ #
    def get_status(self) -> str:
        try:
            response = self.query("SAFEty:STATus?")
            if response:
                s = response.strip().upper()
                if s in ("PASS", "FAIL", "STOP", "STOPPED",
                         "TESTING", "RUNNING", "READY", "WAIT"):
                    return s
                print(f"[STATUS] nieznana odpowiedź: '{response}' → TESTING")
                return "TESTING"
            return "TESTING"
        except Exception as e:
            print(f"Błąd pobierania statusu: {e}")
            return "TESTING"

    def read_measurements(self) -> Optional[Dict]:
        try:
            response = self.query("SAFEty:FETCh? STEP,MODE,OMET,MMET,RMET")
            if response:
                parts = self._parse(response)
                if len(parts) >= 5:
                    raw_v = float(parts[2])
                    raw_i = float(parts[3])
                    raw_r = float(parts[4])
                    return {
                        'step':            parts[0],
                        'mode':            parts[1],
                        'output_voltage':  raw_v if raw_v < OVERFLOW else 0.0,
                        'measure_current': raw_i if raw_i < OVERFLOW else 0.0,
                        'real_current':    raw_r if raw_r < OVERFLOW else 0.0,
                    }
        except Exception as e:
            print(f"Błąd odczytu pomiarów: {e}")
        return None

    def get_test_result(self) -> Tuple[str, Dict]:
        try:
            judgment_code = self.query("SAFEty:RESult:LAST:JUDG?")
            output_v      = self.query("SAFEty:RESult:LAST:OMET?")
            measured_i    = self.query("SAFEty:RESult:LAST:MMET?")
            real_i        = self.query("SAFEty:RESult:LAST:RMET?")

            print(f"[WYNIK] judgment_code = '{judgment_code}'")
            print(f"[WYNIK] output_v      = '{output_v}'")
            print(f"[WYNIK] measured_i    = '{measured_i}'")
            print(f"[WYNIK] real_i        = '{real_i}'")

            jc     = judgment_code.strip() if judgment_code else ""
            result = "PASS" if jc == "116" else "FAIL"
            error_code = "" if result == "PASS" else jc

            raw_v  = float(output_v)   if output_v   else 0.0
            raw_mi = float(measured_i) if measured_i else 0.0
            raw_ri = float(real_i)     if real_i     else 0.0

            data = {
                'judgment_code':    jc,
                'error_code':       error_code,
                'output_voltage':   raw_v  if raw_v  < OVERFLOW else 0.0,
                'measured_current': (raw_mi * 1000) if raw_mi < OVERFLOW else 0.0,
                'real_current':     (raw_ri * 1000) if raw_ri < OVERFLOW else 0.0,
            }
            return (result, data)

        except Exception as e:
            print(f"Błąd pobierania wyniku: {e}")
            return ("UNKNOWN", {})

    # ------------------------------------------------------------------ #
    # CZYSZCZENIE KROKÓW                                                   #
    # ------------------------------------------------------------------ #
    def clear_steps(self):
        try:
            num_steps = self.query("SAFEty:SNUMber?")
            if num_steps:
                parts = self._parse(num_steps)
                n = int(float(parts[0])) if parts else 0
                for i in range(n, 0, -1):
                    self.send_command(f"SAFEty:STEP{i}:DELete")
                    time.sleep(0.1)
        except Exception as e:
            print(f"Błąd czyszczenia kroków: {e}")

    # ------------------------------------------------------------------ #
    # DEBUG                                                                #
    # ------------------------------------------------------------------ #
    def debug_test(self, port: str = "COM6"):
        from config import Config
        print("=" * 55)
        print("DEBUG HI-POT AMIDALA")
        print("=" * 55)

        print(f"\n[1] Łączenie z {port}...")
        self.port = port
        ok = self.connect()
        print(f"    connect() = {ok}")
        if not ok:
            print("    STOP — brak połączenia")
            return

        print("\n[2] *IDN?")
        print(f"    '{self.query('*IDN?')}'")

        print("\n[3] SYST:ERR?")
        print(f"    '{self.query('SYST:ERR?')}'")

        print("\n[4] clear_steps()")
        self.clear_steps()
        print(f"    SNUMber? po czyszczeniu: '{self.query('SAFEty:SNUMber?')}'")

        print("\n[5] configure_acw(TEST_PROFILE)")
        profile = Config.TEST_PROFILE
        self.configure_acw(profile)
        print(f"    SNUMber? po konfiguracji: '{self.query('SAFEty:SNUMber?')}'")

        print("\n[6] start_test()")
        ok = self.start_test()
        print(f"    start_test() = {ok}")
        print(f"    STATus? = '{self.query('SAFEty:STATus?')}'")

        if not ok:
            print("\n    *** START zablokowany ***")
            self.disconnect()
            return

        print("\n[7] Monitorowanie przez 15s...")
        for i in range(30):
            time.sleep(0.5)
            stat = self.query("SAFEty:STATus?")
            meas = self.query("SAFEty:FETCh? STEP,MODE,OMET,MMET,RMET")
            print(f"    t={i*0.5:.1f}s  stat='{stat}'  meas='{meas}'")
            if stat and "STOP" in stat.upper():
                print("    >>> STOPPED")
                break

        print("\n[8] Wynik...")
        result, data = self.get_test_result()
        print(f"    wynik: {result}")
        print(f"    dane:  {data}")

        print("\n[9] Rozłączanie...")
        self.disconnect()
        print("    rozłączono")
        print("\n" + "=" * 55)
        print(f"KOŃCOWY WYNIK: {result}")
        print("=" * 55)


if __name__ == "__main__":
    ChromaHiPotDevice().debug_test("COM6")