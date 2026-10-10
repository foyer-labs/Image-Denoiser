# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller packaging/denoiser.spec --noconfirm
# Produce dist/Denoiser/ con Denoiser.exe (interfaccia) e denoiser-cli.exe (riga di comando).

import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# I percorsi sono relativi alla cartella di questo file (SPECPATH).
SRC = os.path.join(SPECPATH, "..", "src")

hiddenimports = (
    collect_submodules("skimage.restoration")
    + collect_submodules("pywt")
    + collect_submodules("onnxruntime")
    + ["onnx", "onnx.helper", "onnx.numpy_helper", "onnx.checker"]
)
datas = collect_data_files("skimage") + collect_data_files("onnxruntime")
# onnxruntime (e DirectML su Windows) vive in librerie dinamiche da includere esplicitamente.
binaries = collect_dynamic_libs("onnxruntime")
excludes = ["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore"]


def analysis(script):
    return Analysis(
        [script],
        pathex=[SRC],
        hiddenimports=hiddenimports,
        datas=datas,
        binaries=binaries,
        excludes=excludes,
        noarchive=False,
    )


gui = analysis(os.path.join(SPECPATH, "denoiser_gui.py"))
cli = analysis(os.path.join(SPECPATH, "denoiser_cli.py"))

gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    [],
    exclude_binaries=True,
    name="Denoiser",
    console=False,
    upx=False,
)
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="denoiser-cli",
    console=True,
    upx=False,
)
coll = COLLECT(
    gui_exe,
    gui.binaries,
    gui.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    name="Denoiser",
    upx=False,
)
