# logger.py
"""Zapis raportów testów w formacie zgodnym z Chroma 19052 Test Report"""
import os
from datetime import datetime

_DEFAULT_LOG_DIR = "logs"

ERROR_CODES = {
    "1":   "Hardware Fail",
    "2":   "GFI Trip",
    "4":   "ARC Fail",
    "8":   "Check Low Fail",
    "16":  "DC Mode High Fail",
    "17":  "AC Mode High Fail",
    "18":  "AC Mode Low Fail",
    "32":  "Ground Continuity Fail",
    "64":  "IR Low Fail",
    "116": "Pass",
    "128": "IR High Fail",
    "256": "ADV Over",
    "512": "ADI Over",
}


def _get_error_description(error_code: str) -> str:
    if not error_code:
        return ""
    return ERROR_CODES.get(str(error_code).strip(), f"Error code {error_code}")


def save_report(operator: str, program: str, serial: str,
                vtm: float, im: float,
                result: str, error_code: str = "",
                log_dir: str = _DEFAULT_LOG_DIR) -> str:
    """
    Zapisuje raport TXT w formacie Chroma 19052.
    Nazwa pliku: SN_YYYYMMDDHHmmss.txt
    Zwraca ścieżkę do pliku.

    Parametry:
        operator   - HRID operatora (zapisywany w nazwie folderu)
        program    - nazwa modelu np. ESD-160S/VE
        serial     - numer seryjny DUT
        vtm        - napięcie wyjściowe [kV]
        im         - prąd mierzony [mA]
        result     - "PASS" lub "FAIL"
        error_code - kod błędu Chromy (pusty przy PASS)
        log_dir    - folder zapisu (config.LOG_DIR = ścieżka IFS)
    """
    os.makedirs(log_dir, exist_ok=True)

    now          = datetime.now()
    datetime_str = now.strftime("%Y/%m/%d %H:%M:%S")
    error_desc   = _get_error_description(error_code)
    result_cap   = "Pass" if str(result).upper() == "PASS" else "Fail"

    lines = [
        "Chroma 19052 Test report",
        "",
        f"Program:\t{program}",
        f"S/N:\t\t{serial}",
        f"TIME:\t\t{datetime_str}",
        f"Total result:\t{result_cap}",
        "",
        "STEP:\t\t1",
        "MODE:\t\tWVAC",
        "EXT Name:\t",
        f"Vtm:\t\t{vtm:.3f}\tKV",
        f"Im:\t\t{im:.3f}\tmA",
        f"Low:\t\t0.050\tmA",
        f"High:\t\t2.500\tmA",
        f"Result:\t\t{result_cap}",
        f"Error Code:\t{error_code}",
        "",
        f"Error Description: {error_desc}",
    ]

    filename = f"{serial}_{now.strftime('%Y%m%d%H%M%S')}.txt"
    filepath = os.path.join(log_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))

    print(f"[LOG] Zapisano: {filepath}")
    return filepath