"""Avvio dell'interfaccia grafica."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("Denoiser")
    app.setOrganizationName("Denoiser")
    window = MainWindow()
    window.show()
    # Una foto passata da riga di comando (o trascinata sull'icona dell'eseguibile) viene aperta subito.
    files = [Path(a) for a in argv[1:] if Path(a).is_file()]
    if files:
        window.open_path(files[0])
    # Usato dalla build automatica per verificare che l'eseguibile si avvii.
    if os.environ.get("DENOISER_SMOKE_TEST"):
        QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
