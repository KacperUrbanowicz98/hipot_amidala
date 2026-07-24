# logger.py
"""Zapis raportow testow zgodnych z Chroma 19052."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

_DEFAULT_LOG_DIR = "logs"
_FALLBACK_DIR = "logs_pending"

ERROR_CODES = {
    "1": "Hardware Fail",
    "2": "GFI Trip",
    "4": "ARC Fail",
    "8": "Check Low Fail",
    "16": "DC Mode High Fail",
    "17": "AC Mode High Fail",
    "18": "AC Mode Low Fail",
    "32": "Ground Continuity Fail",
    "64": "IR Low Fail",
    "116": "Pass",
    "128": "IR High Fail",
    "256": "ADV Over",
    "512": "ADI Over",
}


def _get_error_description(error_code: str) -> str:
    if not error_code:
        return ""
    return ERROR_CODES.get(str(error_code).strip(), f"Error code {error_code}")


def _application_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_fallback_log_dir() -> str:
    return os.path.join(_application_dir(), _FALLBACK_DIR)


def _report_lines(
    program: str,
    serial: str,
    vtm: float,
    im: float,
    result: str,
    error_code: str,
    low_limit: float,
    high_limit: float,
    now: datetime,
) -> list[str]:
    result_cap = "Pass" if str(result).upper() == "PASS" else "Fail"
    error_description = _get_error_description(error_code)
    return [
        "Chroma 19052 Test report",
        "",
        f"Program:\t{program}",
        f"S/N:\t\t{serial}",
        f"TIME:\t\t{now.strftime('%Y/%m/%d %H:%M:%S')}",
        f"Total result:\t{result_cap}",
        "",
        "STEP:\t\t1",
        "MODE:\t\tWVAC",
        "EXT Name:\t",
        f"Vtm:\t\t{vtm:.3f}\tKV",
        f"Im:\t\t{im:.3f}\tmA",
        f"Low:\t\t{low_limit:.3f}\tmA",
        f"High:\t\t{high_limit:.3f}\tmA",
        f"Result:\t\t{result_cap}",
        f"Error Code:\t{error_code}",
        "",
        f"Error Description: {error_description}",
    ]


def _write_report(directory: str, filename: str, lines: list[str]) -> str:
    """Publikuje raport atomowo: watcher widzi dopiero kompletny plik TXT."""
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{filename}.", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write("\r\n".join(lines))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, filepath)
        return filepath
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def save_report(
    operator: str,
    program: str,
    serial: str,
    vtm: float,
    im: float,
    result: str,
    error_code: str = "",
    low_limit: float = 0.050,
    high_limit: float = 2.500,
    log_dir: str = _DEFAULT_LOG_DIR,
) -> str:
    del operator
    now = datetime.now()
    filename = f"{serial}_{now.strftime('%Y%m%d%H%M%S')}.txt"
    lines = _report_lines(
        program, serial, vtm, im, result, error_code, low_limit, high_limit, now
    )

    try:
        filepath = _write_report(log_dir, filename, lines)
        print(f"[LOG] Zapisano: {filepath}")
        return filepath
    except OSError as primary_error:
        fallback_dir = get_fallback_log_dir()
        filepath = _write_report(fallback_dir, filename, lines)
        print(
            f"[LOG] Sciezka podstawowa niedostepna: {log_dir} "
            f"({primary_error})"
        )
        print(f"[LOG] Zapis awaryjny: {filepath}")
        return filepath
