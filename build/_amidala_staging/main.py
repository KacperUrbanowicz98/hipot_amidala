# main.py
"""Punkt wejscia aplikacji Hi-Pot Amidala."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _application_dir() -> Path:
    return (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )


def _write_startup_error(error_text: str) -> None:
    try:
        Path("startup_error.log").write_text(error_text, encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    app_dir = _application_dir()
    os.chdir(app_dir)

    # Musi zostac wykonane przed pierwszym printem. W buildzie --windowed
    # sys.stdout/sys.stderr moga nie istniec; wtedy diagnostyka trafia do
    # app_runtime_logs zamiast powodowac dodatkowy wyjatek.
    from runtime_logging import configure_runtime_logging

    runtime_log = configure_runtime_logging(app_dir)

    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    app = None
    fatal_callback_handled = False

    def fatal_tk_callback(exc_type, exc_value, exc_traceback):
        """Nieobsluzony blad Tk zatrzymuje test i zamyka aplikacje fail-safe."""
        nonlocal fatal_callback_handled
        if fatal_callback_handled:
            return
        fatal_callback_handled = True

        error_text = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        print("[FATAL UI] Nieobsluzony wyjatek callbacku Tk:", file=sys.stderr)
        print(error_text, file=sys.stderr)
        _write_startup_error(error_text)

        try:
            screen = getattr(app, "current_test_screen", None)
            if screen is not None:
                screen.shutdown()
        except Exception:
            print("[FATAL UI] Blad podczas awaryjnego STOP:", file=sys.stderr)
            traceback.print_exc()

        try:
            messagebox.showerror(
                "Krytyczny blad aplikacji",
                "Wystapil nieobsluzony blad. Aktywny test zostal zatrzymany, "
                "a dalsze testy sa zablokowane.\n\n"
                f"{exc_value}\n\n"
                "Szczegoly zapisano w logu uruchomieniowym.",
                parent=root,
            )
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

    root.report_callback_exception = fatal_tk_callback

    try:
        from config import APP_VERSION
        from gui import AmidalaApp

        print(f"[RUNTIME] Hi-Pot Amidala {APP_VERSION}")
        if runtime_log:
            print(f"[RUNTIME] Diagnostyka sesji: {runtime_log}")
        app = AmidalaApp(root)
    except Exception as exc:
        error_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        print("[STARTUP] Blad uruchomienia:", file=sys.stderr)
        print(error_text, file=sys.stderr)
        _write_startup_error(error_text)
        try:
            messagebox.showerror(
                "Blad uruchomienia Hi-Pot Amidala",
                f"Aplikacja nie zostala uruchomiona, aby uniknac testu z bledna "
                f"konfiguracja.\n\n{exc}\n\nSzczegoly: startup_error.log",
                parent=root,
            )
        except Exception:
            pass
        root.destroy()
        return 1

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
