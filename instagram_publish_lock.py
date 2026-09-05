import logging
import os
import sys
import time
import uuid
from typing import Optional


logger = logging.getLogger("InstagramPublishLock")


class InstagramPublishLockError(Exception):
    """Raised when publish lock cannot be acquired."""

    pass


class InstagramPublishLock:
    """Process-safe and instance-aware file lock for Instagram publishing."""

    _active_locks: dict[str, "InstagramPublishLock"] = {}

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
        self.owner_id = str(uuid.uuid4())

    def _parse_lock_file(self, content: str) -> tuple[int, str]:
        """Parses pid and owner_id from lockfile content."""
        pid = 0
        owner_id = ""
        if not content:
            return pid, owner_id
        for part in content.split(","):
            part = part.strip()
            if part.startswith("pid="):
                try:
                    pid = int(part.split("=")[1])
                except ValueError:
                    pid = 0
            elif part.startswith("owner="):
                owner_id = part.split("=")[1].strip()
        return pid, owner_id

    def _parse_pid(self, content: str) -> int:
        pid, _ = self._parse_lock_file(content)
        return pid

    def _is_pid_active(self, pid: int) -> bool:
        """Verifies if process ID is active on OS."""
        if pid <= 0:
            return False
        try:
            if sys.platform == "win32":
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except Exception:
            return False

    def acquire(self) -> bool:
        start_time = time.time()
        abs_path = os.path.normcase(os.path.abspath(self.lock_file))

        while True:
            # Check for existing lock file
            if os.path.exists(self.lock_file):
                try:
                    mtime = os.path.getmtime(self.lock_file)
                    age = time.time() - mtime

                    content = ""
                    try:
                        with open(self.lock_file, "r", encoding="utf-8") as f:
                            content = f.read()
                    except Exception:
                        content = ""

                    pid_in_file, owner_in_file = self._parse_lock_file(content)

                    # 1. Re-entrant lock check: Same instance already owns the lock file
                    if owner_in_file and owner_in_file == self.owner_id:
                        self.acquired = True
                        InstagramPublishLock._active_locks[abs_path] = self
                        return True

                    # 2. Active lock instance in same process currently holding lock
                    active_inst = InstagramPublishLock._active_locks.get(abs_path)
                    if active_inst and active_inst is not self and active_inst.acquired:
                        if time.time() - start_time >= self.timeout_seconds:
                            return False
                        time.sleep(0.2)
                        continue

                    # 3. Same process ID but no active lock instance holding it: Leftover from previous completed instance
                    if pid_in_file == os.getpid() and owner_in_file != self.owner_id and not active_inst:
                        logger.warning(
                            f"Recovering publish lock '{self.lock_file}' left over by previous lock instance in same process (PID {pid_in_file})."
                        )
                        self.release_force()
                    else:
                        pid_active = self._is_pid_active(pid_in_file) if pid_in_file > 0 else False

                        # 4. Dead process, corrupt file, or stale age check
                        if pid_in_file == 0 or not pid_active or age > self.stale_threshold_seconds:
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
                lock_info = f"pid={os.getpid()},owner={self.owner_id},time={time.time()}"
                os.write(fd, lock_info.encode("utf-8"))
                os.close(fd)
                self.acquired = True
                InstagramPublishLock._active_locks[abs_path] = self
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
        abs_path = os.path.normcase(os.path.abspath(self.lock_file))
        InstagramPublishLock._active_locks.pop(abs_path, None)
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
