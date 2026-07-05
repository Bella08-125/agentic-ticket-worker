from __future__ import annotations

from typing import Any


class MemoryStore:
    """Tiny long-term memory abstraction used for interview-visible architecture."""

    def recall_customer_profile(self, customer_type: str) -> dict[str, Any]:
        profiles = {
            "vip": {"service_level": "priority", "requires_careful_tone": True},
            "store": {"service_level": "partner_store", "requires_careful_tone": True},
            "normal": {"service_level": "standard", "requires_careful_tone": False},
        }
        return profiles.get(customer_type, profiles["normal"])
