r"""
Builder aplikacji Reconext Hi-Pot Amidala dla Windows.

Funkcje:
- budowa PyInstaller w trybie ONEDIR (cały folder aplikacji),
- brak UPX, co zwykle zmniejsza liczbę fałszywych alarmów AV,
- metadane wersji Windows,
- kopiowanie edytowalnych JSON-ów obok EXE,
- ustawienie katalogu roboczego na folder EXE,
- opcjonalne/obowiązkowe podpisanie Authenticode przez SignTool,
- weryfikacja podpisu i zapis manifestu SHA-256.

Zalecane podpisywanie certyfikatem z magazynu Windows:
    set AMIDALA_SIGN_CERT_SHA1=ODCISK_CERTYFIKATU_BEZ_SPACJI
    python create_exe.py

Alternatywnie certyfikat PFX:
    set AMIDALA_SIGN_PFX=C:\certyfikaty\reconext-code-signing.pfx
    set AMIDALA_SIGN_PFX_PASSWORD=haslo
    python create_exe.py

Domyślnie podpis jest WYMAGANY. Do lokalnego builda testowego bez podpisu:
    set AMIDALA_REQUIRE_SIGNING=0
    python create_exe.py
"""

from __future__ import annotations

import getpass
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


APP_NAME = "Hi-Pot Amidala"
APP_DESCRIPTION = "Reconext Hi-Pot Amidala Tester"
COMPANY_NAME = "Reconext"
VERSION = "1.0.0.0"
COPYRIGHT = "Reconext 2026"
ENTRY_POINT = "main.py"

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
STAGING_DIR = BUILD_DIR / "_amidala_staging"
OUTPUT_DIR = DIST_DIR / APP_NAME
EXE_PATH = OUTPUT_DIR / f"{APP_NAME}.exe"

# Pliki źródłowe muszą w stagingu mieć te dokładne nazwy,
# ponieważ takie moduły są importowane w aplikacji.
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
]

# Te pliki mają pozostać edytowalne po zbudowaniu aplikacji.
EDITABLE_DATA_FILES = [
    "amidala_config.json",
    "hwid_map.json",
]

OPTIONAL_DATA_FILES = [
    "operators.json",
]

HIDDEN_IMPORTS = [
    # GUI
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",
    # RS232 / pyserial
    "serial",
    "serial.tools.list_ports",
    "serial.tools.list_ports_windows",
    # Moduły projektu, także importowane wewnątrz metod
    "config",
    "gui",
    "admin_panel",
    "test_screen",
    "hipot_device",
    "interlock",
    "logger",
    "settings_manager",
    "hwid_map",
]

TIMESTAMP_URL = os.environ.get(
    "AMIDALA_TIMESTAMP_URL",
    "http://timestamp.digicert.com",
).strip()

REQUIRE_SIGNING = os.environ.get("AMIDALA_REQUIRE_SIGNING", "1").strip() not in {
    "0", "false", "False", "no", "NO"
}


class BuildError(RuntimeError):
    """Kontrolowany błąd procesu budowania."""


def print_header(title: str) -> None:
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)


def run_command(
    command: list[str],
    *,
    cwd: Optional[Path] = None,
    hide_sensitive: bool = False,
) -> None:
    if hide_sensitive:
        print("[*] Uruchamiam polecenie podpisujące (dane certyfikatu ukryte).")
    else:
        print("[*] " + subprocess.list2cmdline(command))

    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BuildError(
            f"Polecenie zakończyło się błędem {result.returncode}: "
            f"{command[0]}"
        )


def ensure_package(import_name: str, pip_name: str) -> None:
    if importlib.util.find_spec(import_name) is not None:
        return

    print(f"[~] Brak pakietu {pip_name}. Instaluję...")
    run_command([sys.executable, "-m", "pip", "install", pip_name])


def numeric_suffix(path: Path, canonical_name: str) -> int:
    """Zwraca numer z nazwy typu gui(3).py; plik kanoniczny ma priorytet."""
    if path.name.lower() == canonical_name.lower():
        return 10**9

    canonical = Path(canonical_name)
    pattern = re.compile(
        rf"^{re.escape(canonical.stem)}\((\d+)\){re.escape(canonical.suffix)}$",
        re.IGNORECASE,
    )
    match = pattern.match(path.name)
    return int(match.group(1)) if match else -1


def resolve_project_file(canonical_name: str, required: bool = True) -> Optional[Path]:
    """
    Najpierw szuka nazwy kanonicznej, a następnie plików pobranych przez
    przeglądarkę/ChatGPT z dopiskiem (1), (2), itd.
    """
    exact = ROOT_DIR / canonical_name
    if exact.is_file():
        return exact

    canonical = Path(canonical_name)
    pattern = re.compile(
        rf"^{re.escape(canonical.stem)}(?:\((\d+)\))?{re.escape(canonical.suffix)}$",
        re.IGNORECASE,
    )
    candidates = [
        path for path in ROOT_DIR.iterdir()
        if path.is_file() and pattern.match(path.name)
    ]

    if candidates:
        selected = max(
            candidates,
            key=lambda p: (numeric_suffix(p, canonical_name), p.stat().st_mtime),
        )
        print(f"[~] {canonical_name}: używam pliku {selected.name}")
        return selected

    if required:
        raise BuildError(f"Brak wymaganego pliku: {canonical_name}")
    return None


def prepare_staging() -> dict[str, Path]:
    print_header("Przygotowanie plików Hi-Pot Amidala")

    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    resolved: dict[str, Path] = {}

    for canonical_name in PROJECT_FILES:
        source = resolve_project_file(canonical_name, required=True)
        assert source is not None
        destination = STAGING_DIR / canonical_name
        shutil.copy2(source, destination)
        resolved[canonical_name] = source
        print(f"[+] {source.name} -> staging/{canonical_name}")

    for canonical_name in EDITABLE_DATA_FILES:
        source = resolve_project_file(canonical_name, required=True)
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


def create_version_file(path: Path) -> None:
    version_tuple = tuple(int(part) for part in VERSION.split("."))
    if len(version_tuple) != 4:
        raise BuildError("VERSION musi mieć format czterech liczb, np. 1.0.0.0")

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
    print(f"[+] Utworzono {path.name}")


def create_runtime_hook(path: Path) -> None:
    # Dzięki temu amidala_config.json i hwid_map.json są zawsze czytane
    # z folderu obok EXE, niezależnie od skrótu i pola 'Rozpocznij w'.
    content = """import os
import sys

if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(app_dir)
"""
    path.write_text(content, encoding="utf-8")
    print(f"[+] Utworzono {path.name}")


def build_application() -> None:
    print_header("Budowanie folderu aplikacji")

    ensure_package("PyInstaller", "pyinstaller")
    ensure_package("serial", "pyserial")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    pyinstaller_work = BUILD_DIR / "pyinstaller"
    spec_dir = BUILD_DIR / "spec"
    pyinstaller_work.mkdir(parents=True, exist_ok=True)
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
        str(pyinstaller_work),
        "--specpath",
        str(spec_dir),
        "--version-file",
        str(STAGING_DIR / "version_info.txt"),
        "--runtime-hook",
        str(STAGING_DIR / "runtime_hook_amidala.py"),
    ]

    icon = resolve_project_file("amidala.ico", required=False)
    if icon:
        command.extend(["--icon", str(icon)])
        print(f"[+] Ikona: {icon.name}")
    else:
        print("[~] Brak amidala.ico - używam domyślnej ikony")

    for module_name in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", module_name])

    command.append(ENTRY_POINT)

    run_command(command, cwd=STAGING_DIR)

    if not EXE_PATH.is_file():
        raise BuildError(f"PyInstaller nie utworzył oczekiwanego pliku: {EXE_PATH}")

    print(f"[+] Utworzono: {EXE_PATH}")


def copy_editable_files(resolved_files: dict[str, Path]) -> None:
    print_header("Kopiowanie konfiguracji obok EXE")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for canonical_name in EDITABLE_DATA_FILES + OPTIONAL_DATA_FILES:
        source = resolved_files.get(canonical_name)
        if not source:
            continue
        destination = OUTPUT_DIR / canonical_name
        shutil.copy2(source, destination)
        print(f"[+] {source.name} -> {destination.name}")


def version_key(path: Path) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(path.parent))
    return tuple(int(number) for number in numbers[-4:]) if numbers else (0,)


def find_signtool() -> Optional[Path]:
    from_path = shutil.which("signtool.exe") or shutil.which("signtool")
    if from_path:
        return Path(from_path)

    search_roots = []
    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env_name)
        if base:
            search_roots.append(Path(base))

    candidates: list[Path] = []
    for base in search_roots:
        candidates.extend((base / "Windows Kits" / "10" / "bin").glob("*/x64/signtool.exe"))
        candidates.extend((base / "Windows Kits" / "10" / "bin").glob("x64/signtool.exe"))
        candidates.extend((base / "Windows Kits" / "8.1" / "bin" / "x64").glob("signtool.exe"))

    candidates = [candidate for candidate in candidates if candidate.is_file()]
    return max(candidates, key=version_key) if candidates else None


def signing_arguments() -> Optional[list[str]]:
    """Zwraca argumenty wyboru certyfikatu bez polecenia SignTool."""
    thumbprint = os.environ.get("AMIDALA_SIGN_CERT_SHA1", "").replace(" ", "").strip()
    subject = os.environ.get("AMIDALA_SIGN_CERT_SUBJECT", "").strip()
    pfx_value = os.environ.get("AMIDALA_SIGN_PFX", "").strip()
    machine_store = os.environ.get("AMIDALA_SIGN_MACHINE_STORE", "0").strip() in {
        "1", "true", "True", "yes", "YES"
    }

    if thumbprint:
        args = ["/sha1", thumbprint, "/s", "My"]
        if machine_store:
            args.append("/sm")
        print("[+] Podpis: certyfikat z magazynu Windows wybrany odciskiem SHA-1")
        return args

    if subject:
        args = ["/n", subject, "/s", "My"]
        if machine_store:
            args.append("/sm")
        print(f"[+] Podpis: certyfikat z magazynu Windows, Subject zawiera: {subject}")
        return args

    pfx_path: Optional[Path] = None
    if pfx_value:
        pfx_path = Path(pfx_value).expanduser()
        if not pfx_path.is_absolute():
            pfx_path = ROOT_DIR / pfx_path
    else:
        default_pfx = ROOT_DIR / "code_signing.pfx"
        if default_pfx.is_file():
            pfx_path = default_pfx

    if pfx_path:
        if not pfx_path.is_file():
            raise BuildError(f"Nie znaleziono certyfikatu PFX: {pfx_path}")

        password = os.environ.get("AMIDALA_SIGN_PFX_PASSWORD")
        if password is None and sys.stdin.isatty():
            password = getpass.getpass("Hasło do certyfikatu PFX: ")

        args = ["/f", str(pfx_path)]
        if password:
            args.extend(["/p", password])
        print(f"[+] Podpis: certyfikat PFX {pfx_path.name}")
        return args

    return None


def sign_and_verify_executable() -> bool:
    print_header("Podpis cyfrowy Authenticode")

    signtool = find_signtool()
    cert_args = signing_arguments()

    if not signtool:
        message = (
            "Nie znaleziono signtool.exe. Zainstaluj Windows SDK "
            "(Signing Tools for Desktop Apps)."
        )
        if REQUIRE_SIGNING:
            raise BuildError(message)
        print(f"[!] {message} Build pozostaje NIEPODPISANY.")
        return False

    print(f"[+] SignTool: {signtool}")

    if not cert_args:
        message = (
            "Nie skonfigurowano certyfikatu. Ustaw AMIDALA_SIGN_CERT_SHA1, "
            "AMIDALA_SIGN_CERT_SUBJECT albo AMIDALA_SIGN_PFX."
        )
        if REQUIRE_SIGNING:
            raise BuildError(message)
        print(f"[!] {message} Build pozostaje NIEPODPISANY.")
        return False

    command = [
        str(signtool),
        "sign",
        "/v",
        "/fd",
        "SHA256",
        "/d",
        APP_DESCRIPTION,
    ]
    command.extend(cert_args)

    if TIMESTAMP_URL:
        command.extend(["/tr", TIMESTAMP_URL, "/td", "SHA256"])

    command.append(str(EXE_PATH))
    run_command(command, hide_sensitive=True)

    verify_command = [
        str(signtool),
        "verify",
        "/pa",
        "/v",
        str(EXE_PATH),
    ]
    run_command(verify_command)
    print("[+] Podpis został zweryfikowany poprawnie.")
    return True


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


def write_manifest(signed: bool) -> Path:
    manifest_path = OUTPUT_DIR / "build_manifest.txt"
    lines = [
        f"Application: {APP_NAME}",
        f"Version: {VERSION}",
        f"Company: {COMPANY_NAME}",
        f"Build time: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Authenticode signed: {'YES' if signed else 'NO'}",
        f"Timestamp server: {TIMESTAMP_URL if signed and TIMESTAMP_URL else 'N/A'}",
        "",
        "SHA-256:",
    ]

    for path in iter_output_files():
        relative = path.relative_to(OUTPUT_DIR)
        lines.append(f"{sha256_file(path)}  {relative}")

    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Manifest: {manifest_path}")
    return manifest_path


def show_summary(signed: bool) -> None:
    exe_size_mb = EXE_PATH.stat().st_size / (1024 * 1024)
    folder_size = sum(path.stat().st_size for path in OUTPUT_DIR.rglob("*") if path.is_file())
    folder_size_mb = folder_size / (1024 * 1024)

    print_header("BUILD ZAKOŃCZONY")
    print(f"Folder aplikacji : {OUTPUT_DIR}")
    print(f"Plik uruchamiany : {EXE_PATH}")
    print(f"Rozmiar EXE      : {exe_size_mb:.1f} MB")
    print(f"Rozmiar folderu  : {folder_size_mb:.1f} MB")
    print(f"Podpis cyfrowy   : {'TAK' if signed else 'NIE'}")
    print("\n[!] Na stanowiska kopiuj CAŁY folder 'Hi-Pot Amidala'.")
    print("[!] Nie modyfikuj EXE po podpisaniu - zmiana unieważni podpis.")


def main() -> int:
    try:
        if os.name != "nt":
            raise BuildError("Ten builder jest przeznaczony do uruchamiania na Windows.")

        resolved_files = prepare_staging()
        build_application()
        copy_editable_files(resolved_files)
        signed = sign_and_verify_executable()
        write_manifest(signed)
        show_summary(signed)
        return 0

    except KeyboardInterrupt:
        print("\n[!] Anulowano przez użytkownika.")
        return 130
    except BuildError as error:
        print_header("BŁĄD BUDOWANIA")
        print(f"[!] {error}")
        print(f"[~] Logi PyInstaller: {BUILD_DIR / 'pyinstaller'}")
        return 1
    except Exception as error:
        print_header("NIEOCZEKIWANY BŁĄD")
        print(f"[!] {type(error).__name__}: {error}")
        return 1
    finally:
        if sys.stdin.isatty():
            try:
                input("\nNaciśnij Enter, aby zamknąć...")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(main())