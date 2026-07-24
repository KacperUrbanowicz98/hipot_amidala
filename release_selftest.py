"""Testy regresyjne uruchamiane przez builder przed utworzeniem EXE.

Testy nie wymagaja podlaczonej Chromy ani Arduino. Sprawdzaja reguly bezpieczenstwa,
stan cyklu, ochrone przed starym LAST, konfiguracje i format raportu.
"""

from __future__ import annotations

import json
import os
import tempfile
import sys
import types
from pathlib import Path
from unittest.mock import patch

try:
    import serial as _serial_check  # noqa: F401
except ModuleNotFoundError:
    serial_stub = types.ModuleType("serial")
    serial_stub.PARITY_NONE = "N"
    serial_stub.PARITY_ODD = "O"
    serial_stub.PARITY_EVEN = "E"
    serial_stub.EIGHTBITS = 8
    serial_stub.STOPBITS_ONE = 1
    serial_stub.Serial = object
    sys.modules["serial"] = serial_stub

from logger import save_report
from safety_rules import (
    SafetyValidationError,
    validate_acw_profile,
    validate_pass_evidence,
    validate_serial,
    validate_test_timeout,
    validate_timeout_for_profile,
)
from settings_manager import SettingsManager


VALID_PROFILE = {
    "type": "ACW",
    "voltage": 4000,
    "limit_high": 2.5,
    "limit_low": 0.05,
    "presence_min_current": 0.5,
    "ramp_time": 5.0,
    "dwell": 1.0,
    "ramp_dn": 0.0,
    "arc_sense": 0,
    "frequency": 60,
    "continuity": "OFF",
}


def expect_error(func, description: str) -> None:
    try:
        func()
    except (SafetyValidationError, AssertionError):
        return
    raise AssertionError(f"Brak oczekiwanego bledu: {description}")


class DummyConfig:
    COLOR_ERROR = "red"
    COLOR_ACCENT = "green"
    COLOR_BG = "white"
    COLOR_WHITE = "white"
    COLOR_PRIMARY = "blue"
    DEFAULT_COM_PORT = "COM2"
    DEFAULT_BAUDRATE = 9600
    DEFAULT_PARITY = "NONE"
    DEFAULT_FLOW_CONTROL = "NONE"
    INTERLOCK_PORT = "COM10"
    INTERLOCK_BAUDRATE = 9600
    INTERLOCK_ENABLED = True
    LOG_DIR = "logs"
    AUTO_SAVE_RESULTS = True
    TEST_TIMEOUT = 300
    TEST_PROFILE = dict(VALID_PROFILE)


class DummyWidget:
    def __init__(self):
        self.values = {}

    def config(self, **kwargs):
        self.values.update(kwargs)


class DummySerial:
    is_open = True

    def reset_input_buffer(self):
        pass

    def write(self, _data):
        return 1

    def flush(self):
        pass

    def close(self):
        self.is_open = False


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        self.value += 0.05
        return self.value

    def sleep(self, seconds):
        self.value += float(seconds)


class FakeStartDevice:
    """Minimalny ChromaHiPotDevice do testowania bramki nowego cyklu."""

    def __init__(self, baseline_voltage, statuses, live_voltages):
        from hipot_device import ChromaHiPotDevice

        self._impl = ChromaHiPotDevice("COM1", 9600)
        self._impl.connected = True
        self._impl.serial = DummySerial()
        self.baseline_voltage = baseline_voltage
        self.statuses = list(statuses)
        self.live_voltages = list(live_voltages)
        self.read_count = 0
        self.stopped = False

        self._impl._clear_input = lambda: None
        self._impl._write_unlocked = lambda _command: None
        self._impl.query = self.query
        self._impl.get_status = self.get_status
        self._impl.read_measurements = self.read_measurements
        self._impl.stop_test = self.stop_test

    def query(self, command, **_kwargs):
        if command == "SYST:ERR?":
            return '+0,"No error"'
        if command == "SYST:KLOC?":
            return "1"
        return None

    def get_status(self):
        return self.statuses.pop(0) if self.statuses else "PASS"

    def read_measurements(self):
        self.read_count += 1
        if self.read_count == 1:
            voltage = self.baseline_voltage
        else:
            voltage = self.live_voltages.pop(0) if self.live_voltages else self.baseline_voltage
        return {
            "output_voltage": float(voltage),
            "measure_current": 0.0017,
            "real_current": 0.0,
        }

    def stop_test(self):
        self.stopped = True
        self._impl._cycle_active_confirmed = False
        self._impl._cycle_started_monotonic = None
        return True

    def start_test(self):
        return self._impl.start_test()


class FakeResultDevice:
    def __init__(self):
        from hipot_device import ChromaHiPotDevice

        self.device = ChromaHiPotDevice("COM1", 9600)
        self.device.connected = True
        self.device.serial = DummySerial()
        self.device._cycle_active_confirmed = True
        self.device._cycle_started_monotonic = 10.0
        self.device._cycle_id = 7
        self.device._clear_input = lambda: None
        self.device.query = self.query

    @staticmethod
    def query(command, **_kwargs):
        answers = {
            "SAFEty:RESult:LAST:JUDG?": "116",
            "SAFEty:RESult:LAST:OMET?": "+3.999000E+03",
            "SAFEty:RESult:LAST:MMET?": "+1.734000E-03",
            "SAFEty:RESult:LAST:RMET?": "+9.910000E+37",
        }
        return answers.get(command)



class FakeCycleDevice:
    def __init__(
        self,
        current_ma: float,
        result: str = "PASS",
        terminal_after: int = 45,
    ):
        self.connected = True
        self.current_ma = current_ma
        self.result = result
        self.terminal_after = terminal_after
        self.status_calls = 0
        self.stop_calls = 0

    def start_test(self):
        return True

    def get_status(self):
        self.status_calls += 1
        return "STOPPED" if self.status_calls >= self.terminal_after else "RUNNING"

    def read_measurements(self):
        return {
            "output_voltage": 4000.0,
            "measure_current": self.current_ma / 1000.0,
            "real_current": 0.0,
        }

    def get_test_result(self):
        code = "116" if self.result == "PASS" else "18"
        return self.result, {
            "fresh_cycle": True,
            "cycle_id": 1,
            "judgment_code": code,
            "error_code": "" if self.result == "PASS" else code,
            "output_voltage": 4000.0,
            "measured_current": self.current_ma,
            "real_current": 0.0,
        }

    def stop_test(self):
        self.stop_calls += 1
        return True


def test_safety_rules() -> None:
    profile = validate_acw_profile(VALID_PROFILE)
    assert profile["presence_min_current"] == 0.5
    assert validate_serial("21153628743757") == "21153628743757"
    assert validate_test_timeout("300") == 300

    expect_error(
        lambda: validate_acw_profile({**profile, "presence_min_current": 2.5}),
        "prog obecnosci rowny Max Limit",
    )
    expect_error(
        lambda: validate_acw_profile({**profile, "presence_min_current": 0.499}),
        "prog obecnosci ponizej stalej granicy 0.500 mA",
    )
    expect_error(lambda: validate_serial("21153628 43757"), "spacja w S/N")
    expect_error(lambda: validate_test_timeout(5.9), "ulamkowy TEST_TIMEOUT")
    assert validate_timeout_for_profile(300, profile) == 300
    expect_error(
        lambda: validate_timeout_for_profile(10, profile),
        "timeout krotszy niz profil z marginesem",
    )
    from safety_rules import validate_interlock_settings
    expect_error(
        lambda: validate_interlock_settings("COM10", 9600, False),
        "wylaczenie interlocka w wersji produkcyjnej",
    )

    validate_pass_evidence(
        result="PASS",
        terminal_status="STOPPED",
        target_voltage=4000,
        effective_low_ma=0.5,
        high_limit_ma=2.5,
        final_voltage=3999,
        final_current_ma=1.734,
        cycle_max_voltage=4002,
        in_range_samples=3,
        overcurrent_seen=False,
    )

    bad_cases = [
        dict(final_current_ma=0.106, in_range_samples=0),
        dict(terminal_status="FAIL"),
        dict(overcurrent_seen=True),
        dict(final_voltage=3000, cycle_max_voltage=3000),
        dict(in_range_samples=1),
    ]
    base = dict(
        result="PASS",
        terminal_status="STOPPED",
        target_voltage=4000,
        effective_low_ma=0.5,
        high_limit_ma=2.5,
        final_voltage=4000,
        final_current_ma=1.7,
        cycle_max_voltage=4000,
        in_range_samples=3,
        overcurrent_seen=False,
    )
    for index, changes in enumerate(bad_cases, start=1):
        expect_error(
            lambda changes=changes: validate_pass_evidence(**{**base, **changes}),
            f"nieprawidlowy PASS #{index}",
        )


def test_configuration_and_reports() -> None:
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as temp:
        os.chdir(temp)
        try:
            cfg = DummyConfig()
            SettingsManager().save_config(cfg)
            assert Path("amidala_config.json").is_file()

            data = json.loads(Path("amidala_config.json").read_text(encoding="utf-8"))
            data["TEST_PROFILE"]["presence_min_current"] = 0.05
            Path("amidala_config.json").write_text(
                json.dumps(data), encoding="utf-8"
            )
            expect_error(
                lambda: SettingsManager().load_config(DummyConfig()),
                "reczne obnizenie progu obecnosci w JSON",
            )

            expect_error(
                lambda: SettingsManager().save_hwid_map({}),
                "pusta mapa HWID",
            )
            expect_error(
                lambda: SettingsManager().load_hwid_map({"ABC123": "MODEL"}),
                "brak hwid_map.json",
            )

            report_dir = Path(temp) / "reports"
            path = Path(
                save_report(
                    operator="OP",
                    program="ESD-160S/VE",
                    serial="21153628743757",
                    vtm=3.999,
                    im=1.734,
                    result="PASS",
                    low_limit=0.500,
                    high_limit=2.500,
                    log_dir=str(report_dir),
                )
            )
            raw = path.read_bytes()
            assert b"\r\n" in raw
            assert b"\r\r\n" not in raw
            assert not list(report_dir.glob("*.tmp"))
        finally:
            os.chdir(previous)



def test_device_identity_and_configuration() -> None:
    from hipot_device import ChromaHiPotDevice

    def make_device(idn: str):
        device = ChromaHiPotDevice("COM1", 9600)
        serial_port = DummySerial()
        answers = {
            "*IDN?": idn,
            "SYST:ERR?": '+0,"No error"',
            "SYST:KLOC?": "1",
        }
        device.query = lambda command, **_kwargs: answers.get(command)
        device.send_command = lambda _command: None
        return device, serial_port

    with patch("hipot_device.serial.Serial", return_value=DummySerial()), patch(
        "hipot_device.time.sleep", lambda _seconds: None
    ):
        valid, _ = make_device("Chroma,19052,190520013341,5.14")
        assert valid.connect() is True

        wrong, _ = make_device("Other,1234,ABC,1.0")
        assert wrong.connect() is False

    device = ChromaHiPotDevice("COM1", 9600)
    commands = []
    device.send_command = commands.append

    def query(command, **_kwargs):
        answers = {
            "SYST:ERR?": '+0,"No error"',
            "SAFEty:SNUMber?": "1",
            "SAFEty:STEP1:AC?": "4000",
            "SAFEty:STEP1:AC:LIMit?": "0.0025",
            "SAFEty:STEP1:AC:LIMit:LOW?": "0.0005",
            "SAFEty:STEP1:AC:TIME?": "1.0",
            "SAFEty:STEP1:AC:TIME:RAMP?": "5.0",
            "SAFEty:STEP1:AC:TIME:FALL?": "0.0",
        }
        return answers.get(command)

    device.query = query
    with patch("hipot_device.time.sleep", lambda _seconds: None):
        assert device.configure_acw(dict(VALID_PROFILE)) is True
    assert "SAFEty:STEP1:AC:LIMit:LOW 0.0005" in commands
    assert "SAFEty:STEP1:AC:LIMit:HIGH 0.0025" in commands

    bad = ChromaHiPotDevice("COM1", 9600)
    bad.send_command = lambda _command: None
    def bad_query(command, **_kwargs):
        if command == "SYST:ERR?":
            return '+0,"No error"'
        if command == "SAFEty:SNUMber?":
            return "1"
        values = {
            "SAFEty:STEP1:AC?": "3900",  # celowo zly odczyt
            "SAFEty:STEP1:AC:LIMit?": "0.0025",
            "SAFEty:STEP1:AC:LIMit:LOW?": "0.0005",
            "SAFEty:STEP1:AC:TIME?": "1.0",
            "SAFEty:STEP1:AC:TIME:RAMP?": "5.0",
            "SAFEty:STEP1:AC:TIME:FALL?": "0.0",
        }
        return values.get(command)
    bad.query = bad_query
    with patch("hipot_device.time.sleep", lambda _seconds: None):
        try:
            bad.configure_acw(dict(VALID_PROFILE))
        except RuntimeError as exc:
            assert "Odczyt zwrotny Voltage" in str(exc)
        else:
            raise AssertionError("Niezgodny readback konfiguracji nie zablokowal testu")


def test_interlock_heartbeat() -> None:
    from interlock import InterlockMonitor

    class SilentSerial:
        is_open = True

        def readline(self):
            return b""

        def close(self):
            self.is_open = False

    clock = FakeClock()
    monitor = InterlockMonitor("COM10", 9600, heartbeat_timeout=0.5)
    monitor.serial = SilentSerial()
    monitor.connected = True
    monitor._last_message_time = clock.monotonic()
    events = []
    monitor.set_on_change(events.append)
    with patch("interlock.time.monotonic", clock.monotonic), patch(
        "interlock.time.sleep", clock.sleep
    ):
        monitor._monitor_loop()
    assert events == [None]
    assert monitor.connected is False

    class SequenceSerial:
        def __init__(self):
            self.is_open = True
            self.messages = [b"CLOSED\n", b"CLOSED\n", b"1\n", b"OPEN\n"]

        def readline(self):
            if self.messages:
                return self.messages.pop(0)
            return b""

        def close(self):
            self.is_open = False

    clock = FakeClock()
    monitor = InterlockMonitor("COM10", 9600, heartbeat_timeout=0.5)
    monitor.serial = SequenceSerial()
    monitor.connected = True
    monitor._last_message_time = clock.monotonic()
    events = []
    monitor.set_on_change(events.append)
    with patch("interlock.time.monotonic", clock.monotonic), patch(
        "interlock.time.sleep", clock.sleep
    ):
        monitor._monitor_loop()
    assert events[:2] == [True, False]
    assert events[-1] is None


def test_fresh_cycle_guard() -> None:
    clock = FakeClock()
    with patch("hipot_device.time.monotonic", clock.monotonic), patch(
        "hipot_device.time.sleep", clock.sleep
    ):
        active = FakeStartDevice(0.0, ["RUNNING"], [])
        assert active.start_test() is True

        voltage_rise = FakeStartDevice(0.0, ["WAIT"], [120.0])
        assert voltage_rise.start_test() is True

        stale = FakeStartDevice(4000.0, ["PASS"] * 20, [4000.0] * 20)
        assert stale.start_test() is False
        assert stale.stopped is True

        no_baseline = FakeStartDevice(0.0, ["PASS"] * 20, [4000.0] * 20)
        no_baseline._impl.read_measurements = lambda: None
        assert no_baseline.start_test() is False

    result_device = FakeResultDevice().device
    with patch("hipot_device.time.sleep", lambda _seconds: None), patch(
        "hipot_device.time.monotonic", lambda: 16.0
    ):
        result, data = result_device.get_test_result()
        assert result == "PASS"
        assert data["fresh_cycle"] is True
        assert data["cycle_id"] == 7
        assert abs(data["measured_current"] - 1.734) < 0.001
        second_result, _ = result_device.get_test_result()
        assert second_result == "UNKNOWN"



def test_full_cycle_result_gate() -> None:
    from test_screen import TestScreen

    def run_case(
        current_ma: float,
        device_result: str,
        terminal_after: int = 45,
    ):
        screen = TestScreen(None, DummyConfig(), "21153628743757", "ESD-160S/VE")
        screen.device = FakeCycleDevice(current_ma, device_result, terminal_after)
        screen.test_running = True
        screen._test_aborted = False
        screen._closed = False
        screen._run_id = 1

        callbacks = []
        completed = []
        errors = []
        screen._post_ui = callbacks.append
        screen._update_display = lambda: None
        screen._test_completed = lambda result, data: completed.append((result, data))
        screen._test_error = errors.append

        clock = FakeClock()
        screen.start_time = clock.monotonic()
        with patch("test_screen.time.monotonic", clock.monotonic), patch(
            "test_screen.time.sleep", clock.sleep
        ):
            screen._run_test_background(1)

        for callback in callbacks:
            callback()
        return completed, errors, screen.device.stop_calls

    completed, errors, _ = run_case(1.734, "PASS")
    assert [item[0] for item in completed] == ["PASS"]
    assert not errors

    # Nawet gdy tester omylkowo zwroci 116, pusty fixture nie moze przejsc.
    completed, errors, stop_calls = run_case(0.106, "PASS")
    assert not completed
    assert errors and "Odrzucono PASS" in errors[0]
    assert stop_calls >= 1

    completed, errors, _ = run_case(0.106, "FAIL")
    assert [item[0] for item in completed] == ["FAIL"]
    assert not errors

    # Prawdziwy FAIL moze nastapic natychmiast (np. przebicie/overcurrent) i musi
    # zostac zapisany, zamiast byc uznany za stary wynik.
    completed, errors, _ = run_case(3.0, "FAIL", terminal_after=2)
    assert [item[0] for item in completed] == ["FAIL"]
    assert not errors

    # Podejrzanie szybki PASS nadal musi zostac odrzucony.
    completed, errors, stop_calls = run_case(1.734, "PASS", terminal_after=2)
    assert not completed
    assert errors and "PASS pojawił się zbyt szybko" in errors[0]
    assert stop_calls >= 1


def test_interlock_state_machine() -> None:
    from test_screen import TestScreen

    screen = TestScreen(None, DummyConfig(), "21153628743757", "ESD-160S/VE")
    screen.device = type("Device", (), {"connected": True, "stop_test": lambda self: True})()
    screen.interlock = type("Interlock", (), {"connected": True})()
    screen._device_configured = True
    screen.interlock_label = DummyWidget()
    screen.interlock_frame = DummyWidget()
    screen.start_button = DummyWidget()
    screen.stop_button = DummyWidget()
    screen.back_button = DummyWidget()
    screen.next_sn_button = DummyWidget()
    screen.status_label = DummyWidget()
    screen.sn_dialog = None

    starts = []
    screen._start_test = lambda: starts.append("START")

    screen._apply_interlock_state(True)
    assert not starts, "Sam poczatkowy CLOSED nie moze uruchomic testu"
    screen._apply_interlock_state(False)
    screen._apply_interlock_state(True)
    assert starts == ["START"], "Wymagane OPEN -> CLOSED powinno uruchomic test"

    # Otwarcie po fizycznym zakonczeniu cyklu nie moze skasowac wyniku ani
    # wymagac drugiego, sztucznego cyklu OPEN -> CLOSED.
    screen.test_running = True
    screen._cycle_terminal_seen = True
    screen._test_aborted = False
    stop_before = getattr(screen.device, "stop_calls", 0)
    screen._apply_interlock_state(False)
    assert screen.test_running is True
    assert screen._test_aborted is False
    assert screen._lid_open_seen is True
    assert screen._prev_interlock_closed is False

    screen._result_pending = True
    screen._test_aborted = False
    screen._stop_test()
    assert screen._test_aborted is False, "STOP nie moze anulowac zweryfikowanego wyniku"



def test_runtime_logging_windowed() -> None:
    """Symuluje build --windowed, w ktorym stdout/stderr sa None."""
    from runtime_logging import configure_runtime_logging, restore_runtime_logging

    real_stdout = sys.stdout
    real_stderr = sys.stderr
    marker_out = "RUNTIME-STDOUT-SELFTEST"
    marker_err = "RUNTIME-STDERR-SELFTEST"

    with tempfile.TemporaryDirectory() as tmp:
        try:
            sys.stdout = None
            sys.stderr = None
            log_path = configure_runtime_logging(tmp)
            assert log_path is not None
            print(marker_out)
            sys.stderr.write(marker_err + "\n")
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            restore_runtime_logging()
            sys.stdout = real_stdout
            sys.stderr = real_stderr

        content = Path(log_path).read_text(encoding="utf-8")
        assert marker_out in content
        assert marker_err in content


def main() -> None:
    test_safety_rules()
    test_configuration_and_reports()
    test_device_identity_and_configuration()
    test_interlock_heartbeat()
    test_fresh_cycle_guard()
    test_full_cycle_result_gate()
    test_interlock_state_machine()
    test_runtime_logging_windowed()
    print("[SELFTEST] Wszystkie testy regresyjne zakonczone powodzeniem")


if __name__ == "__main__":
    main()
