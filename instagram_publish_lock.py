import logging
import os
import sys
import time
from typing import Optional

logger = logging.getLogger("InstagramPublishLock")


class InstagramPublishLockError(Exception):
    """Raised when publish lock cannot be acquired."""

    pass


class InstagramPublishLock:
    """Process-safe and thread-safe lock using disk lockfile data/instagram_publish.lock.

    Enforces atomic publishing to eliminate race conditions between cloud workers.
    """

    def __init__(
        self,
        lock_file: Optional[str] = None,
        timeout_seconds: float = 15.0,
        stale_threshold_seconds: float = 30.0,
    ):
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(base_dir, exist_ok=True)
        self.lock_file = lock_file or os.path.join(base_dir, "instagram_publish.lock")
        self.timeout_seconds = timeout_seconds
        self.stale_threshold_seconds = stale_threshold_seconds
        self.acquired = False

    @staticmethod
    def _parse_pid(content: str) -> int:
        if not content:
            return 0
        try:
            import json
            data = json.loads(content)
            if isinstance(data, dict) and "pid" in data:
                return int(data["pid"])
        except Exception:
            pass
        try:
            if "pid=" in content:
                pid_str = content.split("pid=")[1].split(",")[0].split("}")[0].strip(' "')
                return int(pid_str)
        except Exception:
            pass
        return 0

    @staticmethod
    def _is_pid_active(pid: int) -> bool:
        """Checks if a process ID is currently running on the system."""
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True
        try:
            if os.name == "nt":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                h_proc = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if h_proc:
                    kernel32.CloseHandle(h_proc)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, OverflowError, AttributeError):
            return False

    def acquire(self) -> bool:
        """Attempts to acquire lock within timeout period, auto-recovering stale locks."""
        start_time = time.time()

        while True:
            # Check for existing lock file
            if os.path.exists(self.lock_file):
                try:
                    mtime = os.path.getmtime(self.lock_file)
                    age = time.time() - mtime

                    pid_in_file = 0
                    try:
                        with open(self.lock_file, "r", encoding="utf-8") as f:
                            content = f.read()
                            pid_in_file = self._parse_pid(content)
                    except Exception:
                        pid_in_file = 0

                    pid_active = self._is_pid_active(pid_in_file) if pid_in_file > 0 else False

                    if (pid_in_file > 0 and pid_in_file != os.getpid() and not pid_active) or age > self.stale_threshold_seconds:
                        logger.warning(
                            f"Recovering publish lock '{self.lock_file}' (PID {pid_in_file}, active: {pid_active}, Age: {round(age, 1)}s)."
                        )
                        self.release_force()
                    else:
                        if time.time() - start_time >= self.timeout_seconds:
                            return False
                        time.sleep(0.2)
                        continue
                except OSError:
                    pass

            # Attempt atomic creation
            try:
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                lock_info = f"pid={os.getpid()},time={time.time()}"
                os.write(fd, lock_info.encode("utf-8"))
                os.close(fd)
                self.acquired = True
                logger.info(f"Publish lock acquired successfully ({self.lock_file}).")
                return True
            except OSError:
                if time.time() - start_time >= self.timeout_seconds:
                    return False
                time.sleep(0.2)


    def release(self) -> None:
        """Releases the lock if held by this instance."""
        if self.acquired:
            self.release_force()
            self.acquired = False

    def release_force(self) -> None:
        """Forcefully removes the lock file if present."""
        try:
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
                logger.info(f"Publish lock released ({self.lock_file}).")
        except OSError as e:
            logger.warning(f"Error releasing publish lock: {e}")

    def __enter__(self):
        if not self.acquire():
            raise InstagramPublishLockError("Could not acquire Instagram publish lock (timed out).")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
