import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger("InstagramCloudStorage")


class StorageProvider(ABC):
    """Abstract interface for persistent data storage across deployments."""

    @abstractmethod
    def read_json(self, relative_path: str, default: Optional[Any] = None) -> Any:
        pass

    @abstractmethod
    def write_json(self, relative_path: str, data: Any) -> bool:
        pass

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        pass


class LocalStorageProvider(StorageProvider):
    """File-backed local disk storage provider storing JSON data in the data/ directory."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve_path(self, relative_path: str) -> str:
        return os.path.join(self.base_dir, relative_path.lstrip("/\\"))

    def exists(self, relative_path: str) -> bool:
        return os.path.exists(self._resolve_path(relative_path))

    def read_json(self, relative_path: str, default: Optional[Any] = None) -> Any:
        full_path = self._resolve_path(relative_path)
        if not os.path.exists(full_path):
            return default if default is not None else {}
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"LocalStorageProvider read error for '{relative_path}': {e}")
            return default if default is not None else {}

    def write_json(self, relative_path: str, data: Any) -> bool:
        full_path = self._resolve_path(relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        temp_path = f"{full_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, full_path)
            return True
        except Exception as e:
            logger.error(f"LocalStorageProvider write error for '{relative_path}': {e}")
            return False


class ProductionStorageProvider(LocalStorageProvider):
    """Production persistent storage provider.

    Uses environment overrides (e.g. PERSISTENT_STORAGE_DIR / Render Disks) if set,
    otherwise falls back safely to LocalStorageProvider.
    """

    def __init__(self):
        storage_dir = os.getenv("PERSISTENT_STORAGE_DIR", "").strip()
        if not storage_dir or not os.path.exists(storage_dir):
            storage_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        super().__init__(base_dir=storage_dir)


def get_storage_provider() -> StorageProvider:
    """Factory returning appropriate StorageProvider based on environment."""
    prod_env = os.getenv("INSTAGRAM_PRODUCTION_ENABLED", "false").strip().lower()
    if prod_env in ("true", "1", "yes", "on"):
        return ProductionStorageProvider()
    return LocalStorageProvider()
