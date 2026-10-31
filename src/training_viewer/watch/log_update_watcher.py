"""日志更新监听器。

以低频轮询作为正确性保证，并在 watchdog 可用时用文件系统事件提前唤醒扫描。
只依赖文件事件会在网络盘、编辑器写入等场景漏事件，因此轮询始终保留。
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

LOGGER = logging.getLogger("training_viewer.watcher")

try:  # watchdog 是必需依赖，但在最小环境中仍允许退化为纯轮询。
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - 仅在依赖被裁剪时发生
    FileSystemEventHandler = None  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]


class _WakeupHandler(FileSystemEventHandler if FileSystemEventHandler else object):
    def __init__(self, wake_up):
        self._wake_up = wake_up

    def on_any_event(self, event):  # noqa: D401 - watchdog 回调
        self._wake_up()


class LogUpdateWatcher:
    """轮询 + 文件事件的日志更新监听器。"""

    def __init__(self, service, interval_seconds: float = 2.0):
        self.service = service
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._wakeup_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer = None
        self._observer_lock = threading.RLock()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="training-viewer-log-watcher", daemon=True
        )
        self._thread.start()
        self.refresh_watches()

    def stop(self) -> None:
        self._stop_event.set()
        self._wakeup_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._stop_observer()

    def wake_up(self) -> None:
        self._wakeup_event.set()

    def refresh_watches(self) -> None:
        if Observer is None:
            return
        with self._observer_lock:
            self._stop_observer()
            observer = Observer()
            handler = _WakeupHandler(self.wake_up)
            scheduled = 0
            for root in self.service.list_roots():
                path = Path(root["path"])
                if not path.is_dir():
                    continue
                try:
                    observer.schedule(handler, str(path), recursive=True)
                    scheduled += 1
                except OSError as error:
                    LOGGER.warning("无法监听目录 %s：%s（继续使用轮询）", path, error)
            if scheduled:
                observer.daemon = True
                observer.start()
                self._observer = observer

    def _stop_observer(self) -> None:
        with self._observer_lock:
            if self._observer is not None:
                try:
                    self._observer.stop()
                    self._observer.join(timeout=2)
                except Exception:  # noqa: BLE001 - 停止失败不应阻止退出
                    LOGGER.debug("停止文件监听器失败", exc_info=True)
                self._observer = None

    def _run(self) -> None:
        if Observer is None:
            LOGGER.warning("watchdog 不可用，仅使用 %.1f 秒轮询", self.interval_seconds)
        try:
            self.service.synchronize()
        except Exception:  # noqa: BLE001
            LOGGER.exception("首次目录同步失败")
        while not self._stop_event.is_set():
            self._wakeup_event.wait(timeout=self.interval_seconds)
            self._wakeup_event.clear()
            if self._stop_event.is_set():
                break
            try:
                self.service.synchronize()
            except Exception:  # noqa: BLE001 - 后台线程必须保持存活
                LOGGER.exception("轮询同步失败，将在下一轮重试")
