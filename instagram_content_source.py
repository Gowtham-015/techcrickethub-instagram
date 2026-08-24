from abc import ABC, abstractmethod
from typing import Any, Dict, List


class InstagramContentSource(ABC):
    """Abstract interface for Instagram content sources."""

    @abstractmethod
    def get_content_items(self) -> List[Dict[str, Any]]:
        """Retrieves raw content items from the content source."""
        pass
