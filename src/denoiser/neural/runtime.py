"""Esecuzione dei modelli con ONNX Runtime, sulla GPU quando disponibile."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

# In ordine di preferenza: NVIDIA CUDA, DirectML (qualsiasi GPU su Windows), Apple, CPU.
_GPU_PROVIDERS = ("CUDAExecutionProvider", "DmlExecutionProvider", "CoreMLExecutionProvider")

_sessions: dict[tuple[str, str], "InferenceSessionWrapper"] = {}
_lock = threading.Lock()

DEVICES = {"auto": "Automatico (GPU se disponibile)", "cpu": "Solo CPU"}


def available_providers() -> list[str]:
    import onnxruntime as ort

    return list(ort.get_available_providers())


def describe_devices() -> str:
    gpu = [p for p in available_providers() if p in _GPU_PROVIDERS]
    names = {"CUDAExecutionProvider": "NVIDIA CUDA", "DmlExecutionProvider": "DirectML",
             "CoreMLExecutionProvider": "Core ML"}
    return "GPU: " + ", ".join(names[p] for p in gpu) if gpu else "Nessuna accelerazione GPU disponibile: si usa la CPU"


class InferenceSessionWrapper:
    def __init__(self, path: Path, device: str):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        available = available_providers()
        providers: list = []
        if device != "cpu":
            providers = [p for p in _GPU_PROVIDERS if p in available]
        if "DmlExecutionProvider" in providers:
            # Requisiti di DirectML.
            options.enable_mem_pattern = False
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        providers.append("CPUExecutionProvider")
        self.session = ort.InferenceSession(str(path), sess_options=options, providers=providers)
        self.provider = self.session.get_providers()[0]
        self.input_name = self.session.get_inputs()[0].name
        self._run_lock = threading.Lock()

    def __call__(self, batch: np.ndarray) -> np.ndarray:
        with self._run_lock:  # una sessione GPU alla volta
            return self.session.run(None, {self.input_name: batch.astype(np.float32)})[0]


def get_session(path: Path, device: str = "auto") -> InferenceSessionWrapper:
    key = (str(path), device)
    with _lock:
        if key not in _sessions:
            _sessions[key] = InferenceSessionWrapper(path, device)
        return _sessions[key]
