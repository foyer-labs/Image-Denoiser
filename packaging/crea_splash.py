"""Genera l'immagine di avvio dell'eseguibile (splash nativo di PyInstaller).

Uso: python packaging/crea_splash.py PERCORSO.png
L'immagine è la stessa schermata disegnata dall'app (denoiser.gui.splash), senza barra piena:
il passaggio allo splash con la barra di avanzamento risulta così senza scatti.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from denoiser import __version__  # noqa: E402
from denoiser.gui.splash import render_splash  # noqa: E402
from denoiser.gui.style import apply_theme  # noqa: E402

app = QApplication([])
apply_theme(app)
if not render_splash(None, "", __version__, 1.0, rounded=False).save(sys.argv[1]):
    sys.exit(f"Impossibile salvare {sys.argv[1]}")
print(f"Immagine di avvio salvata in {sys.argv[1]}")
