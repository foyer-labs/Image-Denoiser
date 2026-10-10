"""Esecuzione delle elaborazioni in background, per non bloccare l'interfaccia."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)


class Task(QRunnable):
    """Esegue ``fn(*args, **kwargs)`` in un thread; se ``with_progress`` passa anche ``progress=``."""

    def __init__(self, fn: Callable[..., Any], *args: Any, with_progress: bool = False, **kwargs: Any):
        super().__init__()
        self.signals = TaskSignals()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        if with_progress:
            self._kwargs["progress"] = self.signals.progress.emit

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # mostrato all'utente
            detail = str(exc) or exc.__class__.__name__
            traceback.print_exc()
            self.signals.failed.emit(detail)
        else:
            self.signals.finished.emit(result)


def start(task: Task) -> Task:
    QThreadPool.globalInstance().start(task)
    return task
