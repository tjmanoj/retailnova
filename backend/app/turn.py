"""Per-turn state shared between the chat loop and the concierge tools.

Keyed by session id (one active turn per session). The tool context gives tools the
session id, so the model never supplies it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TurnState:
    session_id: str
    store_id: str
    channel: str = "chat"
    image: Optional[bytes] = None
    image_mime: Optional[str] = None
    # SKUs returned by search / availability / alternatives tools during this turn
    seen_skus: list[str] = field(default_factory=list)
    # the size the shopper asked about (from the last search), used for badges
    requested_size: Optional[str] = None
    # cards accepted by show_products (in order)
    cards: list[dict] = field(default_factory=list)
    shown_skus: list[str] = field(default_factory=list)
    dropped_skus: list[str] = field(default_factory=list)
    # compact summary of tool results for the signal extractor
    tool_log: list[dict] = field(default_factory=list)
    # text emitted so far in the current model response (for skip-summarization)
    text_in_current_response: bool = False
    total_text: str = ""
    pending_products: list[dict] = field(default_factory=list)
    reserved: list[dict] = field(default_factory=list)
    waitlisted: list[dict] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def see(self, skus: list[str]) -> None:
        for s in skus:
            if s and s not in self.seen_skus:
                self.seen_skus.append(s)


TURNS: dict[str, TurnState] = {}


def get_turn(session_id: str | None) -> TurnState | None:
    if not session_id:
        return None
    return TURNS.get(session_id)
