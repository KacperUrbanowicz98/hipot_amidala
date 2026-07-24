"""Builder EXE dla aplikacji Reconext Hi-Pot Amidala.

Buduje aplikacje PyInstallerem w trybie ONEDIR bez podpisu cyfrowego.
Pliki amidala_config.json i hwid_map.json pozostaja obok EXE i moga
byc edytowane z panelu administratora.
"""

from __future__ import annotations

import hashlib
import importlib.util
import importlib.metadata
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from config import APP_VERSION as SOURCE_APP_VERSION


APP_NAME = "Hi-Pot Amidala"
APP_DESCRIPTION = "Hi-Pot Amidala Tester"
COMPANY_NAME = "Reconext"
VERSION = f"{SOURCE_APP_VERSION}.0"
COPYRIGHT = "Reconext 2026"

REQUIRED_PYTHON = (3, 13)
REQUIRED_PACKAGES = {
    "PyInstaller": ("pyinstaller", "6.21.0"),
    "serial": ("pyserial", "3.5"),
}

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
STAGING_DIR = BUILD_DIR / "_amidala_staging"
OUTPUT_DIR = DIST_DIR / APP_NAME
EXE_PATH = OUTPUT_DIR / f"{APP_NAME}.exe"

PROJECT_FILES = [
    "main.py",
    "gui.py",
    "config.py",
    "admin_panel.py",
    "test_screen.py",
    "hipot_device.py",
    "interlock.py",
    "logger.py",
    "settings_manager.py",
    "hwid_map.py",
    "safety_rules.py",
    "runtime_logging.py",
]

EDITABLE_DATA_FILES = [
    "amidala_config.json",
    "hwid_map.json",
]

OPTIONAL_DATA_FILES = [
    "operators.json",
]

HIDDEN_IMPORTS = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",
    "serial",
    "serial.tools.list_ports",
    "serial.tools.list_ports_windows",
    "config",
    "gui",
    "admin_panel",
    "test_screen",
    "hipot_device",
    "interlock",
    "logger",
    "settings_manager",
    "hwid_map",
    "safety_rules",
    "runtime_logging",
]


REQUIRED_SAFETY_MARKERS = {
    "test_screen.py": (
        "validate_pass_evidence",
        "_cycle_in_range_samples",
        "_result_pending",
        "fresh_cycle",
        "_cycle_terminal_seen",
    ),
    "hipot_device.py": (
        "_cycle_active_confirmed",
        "SAFEty:RESult:LAST:JUDG?",
        "presence_min_current",
        "SYST:KLOC ON",
        "_verify_acw_readback",
    ),
    "safety_rules.py": (
        "MIN_PRESENCE_CURRENT_MA = 0.500",
        "validate_pass_evidence",
        "validate_timeout_for_profile",
    ),
    "runtime_logging.py": (
        "configure_runtime_logging",
        "app_runtime_logs",
    ),
}


class BuildError(RuntimeError):
    pass


def print_header(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def run_command(command: list[str], cwd: Optional[Path] = None) -> None:
    print("[*] " + subprocess.list2cmdline(command))
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BuildError(
            f"Polecenie zakonczylo sie bledem {result.returncode}: {command[0]}"
        )


def ensure_package(
    import_name: str,
    pip_name: str,
    expected_version: str,
) -> None:
    if importlib.util.find_spec(import_name) is None:
        raise BuildError(
            f"Brak pakietu {pip_name}=={expected_version}. Zainstaluj go w .venv: "
            f"{sys.executable} -m pip install {pip_name}=={expected_version}"
        )
    try:
        actual_version = importlib.metadata.version(pip_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise BuildError(f"Nie mozna odczytac wersji pakietu {pip_name}") from exc
    if actual_version != expected_version:
        raise BuildError(
            f"Wymagany {pip_name}=={expected_version}, znaleziono {actual_version}. "
            "Uzyj zatwierdzonego srodowiska .venv."
        )
    print(f"[+] {pip_name} {actual_version}: OK")


def verify_build_environment() -> None:
    if sys.version_info[:2] != REQUIRED_PYTHON:
        raise BuildError(
            f"Wymagany Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}.x, "
            f"uruchomiono {sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        )
    print(
        f"[+] Python {sys.version_info.major}.{sys.version_info.minor}."
        f"{sys.version_info.micro}: OK"
    )
    for import_name, (pip_name, version) in REQUIRED_PACKAGES.items():
        ensure_package(import_name, pip_name, version)


FORBIDDEN_DUPLICATE_MARKERS = (
    "_check_serial_duplicate",
    "_check_duplicate_async",
    "_duplicate_check_done",
    "_duplicate_allowed",
    "Duplikat SN",
    "Sprawdzanie numeru seryjnego",
    "był już testowany",
    "byl juz testowany",
)


def resolve_project_file(
    canonical_name: str,
    required: bool = True,
) -> Optional[Path]:
    """Używa wyłącznie pliku o dokładnej, kanonicznej nazwie.

    Celowo nie wybiera plików typu ``test_screen(3).py``. Dzięki temu builder
    nie może niejawnie zbudować EXE ze starej lub przypadkowej kopii kodu.
    """
    exact = ROOT_DIR / canonical_name
    if exact.is_file():
        return exact

    if required:
        raise BuildError(
            f"Brak wymaganego pliku: {canonical_name}. "
            "Nadaj aktualnemu plikowi dokładnie tę nazwę."
        )
    return None


def validate_source_file(canonical_name: str, source: Path) -> None:
    """Sprawdza wymagane zabezpieczenia i brak wycofanej logiki."""
    text = source.read_text(encoding="utf-8", errors="strict")

    if canonical_name == "test_screen.py":
        found = [marker for marker in FORBIDDEN_DUPLICATE_MARKERS if marker in text]
        if found:
            raise BuildError(
                "test_screen.py nadal zawiera logike kontroli duplikatow: "
                + ", ".join(found)
            )

    missing = [
        marker
        for marker in REQUIRED_SAFETY_MARKERS.get(canonical_name, ())
        if marker not in text
    ]
    if missing:
        raise BuildError(
            f"{canonical_name}: brakuje wymaganych elementow zabezpieczen: "
            + ", ".join(missing)
        )


def run_release_preflight() -> None:
    """Kompiluje kod, uruchamia regresje i waliduje konfiguracje wydania."""
    print_header("Kontrola przed wydaniem")

    source_files = [ROOT_DIR / name for name in PROJECT_FILES]
    source_files.extend([ROOT_DIR / "release_selftest.py", ROOT_DIR / "create_exe.py"])
    missing = [str(path) for path in source_files if not path.is_file()]
    if missing:
        raise BuildError("Brak plikow kontroli wydania: " + ", ".join(missing))

    run_command(
        [sys.executable, "-m", "py_compile", *map(str, source_files)],
        cwd=ROOT_DIR,
    )
    print("[+] Kompilacja wszystkich skryptow: OK")

    run_command(
        [sys.executable, str(ROOT_DIR / "release_selftest.py")],
        cwd=ROOT_DIR,
    )

    validation_code = (
        "from config import Config\n"
        "from hwid_map import HwidMap\n"
        "cfg = Config()\n"
        "assert cfg.INTERLOCK_ENABLED, "
        "'INTERLOCK_ENABLED musi byc true w buildzie produkcyjnym'\n"
        "assert cfg.AUTO_SAVE_RESULTS, "
        "'AUTO_SAVE_RESULTS musi byc true w buildzie produkcyjnym'\n"
        "assert float(cfg.TEST_PROFILE['presence_min_current']) >= 0.500, "
        "'presence_min_current nie moze byc nizszy niz 0.500 mA'\n"
        "assert len(HwidMap().get_all()) > 0, 'Mapa HWID jest pusta'\n"
        "print('[PREFLIGHT] Konfiguracja i mapa HWID: OK')\n"
    )
    run_command([sys.executable, "-c", validation_code], cwd=ROOT_DIR)
    print(f"[+] Wersja zrodla: {SOURCE_APP_VERSION}; wersja EXE: {VERSION}")

def create_version_file(path: Path) -> None:
    version_tuple = tuple(int(part) for part in VERSION.split("."))
    if len(version_tuple) != 4:
        raise BuildError("VERSION musi miec format np. 1.0.0.0")

    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', '{COMPANY_NAME}'),
        StringStruct('FileDescription', '{APP_DESCRIPTION}'),
        StringStruct('FileVersion', '{VERSION}'),
        StringStruct('InternalName', '{APP_NAME}'),
        StringStruct('LegalCopyright', '{COPYRIGHT}'),
        StringStruct('OriginalFilename', '{APP_NAME}.exe'),
        StringStruct('ProductName', '{COMPANY_NAME} {APP_NAME}'),
        StringStruct('ProductVersion', '{VERSION}'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    path.write_text(content, encoding="utf-8")


def create_runtime_hook(path: Path) -> None:
    """Ustawia folder EXE i jawne sciezki bibliotek Tcl/Tk."""
    content = """import os
import sys

if getattr(sys, "frozen", False):
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    internal_dir = getattr(sys, "_MEIPASS", os.path.join(app_dir, "_internal"))

    tcl_dir = os.path.join(internal_dir, "_tcl_data")
    tk_dir = os.path.join(internal_dir, "_tk_data")

    if os.path.isdir(tcl_dir):
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.isdir(tk_dir):
        os.environ["TK_LIBRARY"] = tk_dir

    os.chdir(app_dir)
"""
    path.write_text(content, encoding="utf-8")


def locate_tcl_tk() -> tuple[Path, Path]:
    """Znajduje pelne katalogi Tcl i Tk uzywane przez biezacego Pythona."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            tcl_dir = Path(root.tk.eval("info library")).resolve()
            tk_dir = Path(root.tk.eval("set tk_library")).resolve()
        finally:
            root.destroy()
    except Exception as exc:
        raise BuildError(f"Nie moge ustalic katalogow Tcl/Tk: {exc}") from exc

    required = [
        tcl_dir / "init.tcl",
        tk_dir / "tk.tcl",
        tk_dir / "ttk" / "scrollbar.tcl",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise BuildError(
            "Instalacja Tcl/Tk jest niekompletna. Brakuje: " + ", ".join(missing)
        )

    print(f"[+] Tcl: {tcl_dir}")
    print(f"[+] Tk : {tk_dir}")
    return tcl_dir, tk_dir


def copy_tcl_tk_runtime(tcl_dir: Path, tk_dir: Path) -> None:
    """Dopelnia katalog _internal o wszystkie skrypty Tcl/Tk i Ttk."""
    print_header("Weryfikacja bibliotek Tcl/Tk")

    internal_dir = OUTPUT_DIR / "_internal"
    tcl_target = internal_dir / "_tcl_data"
    tk_target = internal_dir / "_tk_data"

    internal_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(tcl_dir, tcl_target, dirs_exist_ok=True)
    shutil.copytree(tk_dir, tk_target, dirs_exist_ok=True)

    required = [
        tcl_target / "init.tcl",
        tk_target / "tk.tcl",
        tk_target / "ttk" / "scrollbar.tcl",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise BuildError(
            "Po buildzie nadal brakuje plikow Tcl/Tk: " + ", ".join(missing)
        )

    print(f"[+] Tcl skopiowany do: {tcl_target}")
    print(f"[+] Tk/Ttk skopiowany do: {tk_target}")
    print("[+] Zweryfikowano: _tk_data\\ttk\\scrollbar.tcl")


def prepare_staging() -> dict[str, Path]:
    print_header("Przygotowanie plikow")

    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    resolved: dict[str, Path] = {}

    for canonical_name in PROJECT_FILES:
        source = resolve_project_file(canonical_name)
        assert source is not None
        validate_source_file(canonical_name, source)
        shutil.copy2(source, STAGING_DIR / canonical_name)
        resolved[canonical_name] = source
        digest = hashlib.sha256(source.read_bytes()).hexdigest().upper()[:16]
        print(f"[+] {source.name} -> {canonical_name}  SHA256:{digest}")

    for canonical_name in EDITABLE_DATA_FILES:
        source = resolve_project_file(canonical_name)
        assert source is not None
        resolved[canonical_name] = source
        print(f"[+] Dane edytowalne: {source.name}")

    for canonical_name in OPTIONAL_DATA_FILES:
        source = resolve_project_file(canonical_name, required=False)
        if source:
            resolved[canonical_name] = source
            print(f"[+] Dane opcjonalne: {source.name}")
        else:
            print(f"[~] Brak {canonical_name} - pomijam")

    create_version_file(STAGING_DIR / "version_info.txt")
    create_runtime_hook(STAGING_DIR / "runtime_hook_amidala.py")
    return resolved


def build_application(tcl_dir: Path, tk_dir: Path) -> None:
    print_header("Budowanie Hi-Pot Amidala")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    work_dir = BUILD_DIR / "pyinstaller"
    spec_dir = BUILD_DIR / "spec"
    work_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--noupx",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--version-file",
        str(STAGING_DIR / "version_info.txt"),
        "--runtime-hook",
        str(STAGING_DIR / "runtime_hook_amidala.py"),
        "--add-data",
        f"{tcl_dir};_tcl_data",
        "--add-data",
        f"{tk_dir};_tk_data",
    ]

    icon = resolve_project_file("amidala.ico", required=False)
    if icon:
        command.extend(["--icon", str(icon)])
        print(f"[+] Ikona: {icon.name}")
    else:
        print("[~] Brak amidala.ico - uzywam domyslnej ikony")

    for module_name in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", module_name])

    command.append("main.py")
    run_command(command, cwd=STAGING_DIR)

    if not EXE_PATH.is_file():
        raise BuildError(f"Nie znaleziono utworzonego EXE: {EXE_PATH}")


def copy_editable_files(resolved: dict[str, Path]) -> None:
    print_header("Kopiowanie konfiguracji")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for canonical_name in EDITABLE_DATA_FILES + OPTIONAL_DATA_FILES:
        source = resolved.get(canonical_name)
        if not source:
            continue
        destination = OUTPUT_DIR / canonical_name
        shutil.copy2(source, destination)
        print(f"[+] {canonical_name} obok EXE")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def iter_output_files() -> Iterable[Path]:
    for path in sorted(OUTPUT_DIR.rglob("*")):
        if path.is_file() and path.name != "build_manifest.txt":
            yield path


def write_manifest() -> None:
    manifest = OUTPUT_DIR / "build_manifest.txt"
    lines = [
        f"Application: {APP_NAME}",
        f"Version: {VERSION}",
        f"Company: {COMPANY_NAME}",
        f"Build time: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "Authenticode signed: NO",
        "",
        "SHA-256:",
    ]

    for path in iter_output_files():
        lines.append(f"{sha256_file(path)}  {path.relative_to(OUTPUT_DIR)}")

    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def show_summary() -> None:
    exe_size = EXE_PATH.stat().st_size / (1024 * 1024)
    folder_size = sum(
        path.stat().st_size for path in OUTPUT_DIR.rglob("*") if path.is_file()
    ) / (1024 * 1024)

    print_header("BUILD ZAKONCZONY")
    print(f"Folder aplikacji : {OUTPUT_DIR}")
    print(f"Uruchamiaj       : {EXE_PATH}")
    print(f"Rozmiar EXE      : {exe_size:.1f} MB")
    print(f"Rozmiar folderu  : {folder_size:.1f} MB")
    print("Podpis cyfrowy   : NIE")
    print("\n[!] Kopiuj caly folder 'Hi-Pot Amidala', nie samo EXE.")
    print("[!] amidala_config.json i hwid_map.json musza pozostac obok EXE.")


def main() -> int:
    try:
        if os.name != "nt":
            raise BuildError("Builder nalezy uruchomic na Windows.")

        verify_build_environment()
        run_command(
            [sys.executable, "-c", "import serial; print('[PREFLIGHT] pyserial: OK')"],
            cwd=ROOT_DIR,
        )
        run_release_preflight()
        resolved = prepare_staging()
        tcl_dir, tk_dir = locate_tcl_tk()
        build_application(tcl_dir, tk_dir)
        copy_tcl_tk_runtime(tcl_dir, tk_dir)
        copy_editable_files(resolved)
        write_manifest()
        show_summary()
        return 0

    except KeyboardInterrupt:
        print("\n[!] Anulowano przez uzytkownika.")
        return 130
    except BuildError as error:
        print_header("BLAD BUDOWANIA")
        print(f"[!] {error}")
        print(f"[~] Ostrzezenia PyInstaller: {BUILD_DIR / 'pyinstaller'}")
        return 1
    except Exception as error:
        print_header("NIEOCZEKIWANY BLAD")
        print(f"[!] {type(error).__name__}: {error}")
        return 1
    finally:
        if sys.stdin.isatty():
            try:
                input("\nNacisnij Enter, aby zamknac...")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(main())