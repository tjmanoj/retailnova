"""Shared schemas. The block below is copied exactly from docs/contracts.md §4."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

Category = Literal["sarees","kurta_sets","mens_ethnic","home_decor","gifting","footwear"]

class StoreStock(BaseModel):
    store_id: str
    store_name: str
    on_hand: int                      # total across sizes
    sizes_in_stock: list[str]

class ProductCard(BaseModel):
    sku: str
    name: str
    category: Category
    color: str
    material: str
    price_inr: int
    mrp_inr: int
    image_url: str
    image_alt: str
    sizes: list[str]
    availability: list[StoreStock]    # all physical stores + ONLINE
    requested_store_id: str
    requested_store_on_hand: int
    badge: Literal["in_stock","low","out_of_stock","other_store"]
    reason: Optional[str] = None      # one line: why it was recommended

class DemandSignal(BaseModel):
    signal_id: str
    ts: str                           # ISO-8601 UTC
    date: str                         # YYYY-MM-DD
    source: Literal["live","simulated"]
    session_id: Optional[str] = None
    store_id: str
    channel: Literal["chat","image_search","store_assist"]
    category: Category
    sku: Optional[str] = None         # requested or closest SKU
    attributes: dict[str, str] = {}   # color, size, material, occasion
    price_band: Optional[dict[str, int]] = None   # {"min_inr":..,"max_inr":..}
    outcome: Literal["fulfilled","substituted","unmet"]
    reason: Optional[Literal["out_of_stock","size_unavailable","not_carried","price_too_high","other"]] = None
    quantity: int = 1
    est_value_inr: int
    intent_strength: float = Field(ge=0, le=1)
    summary: str                      # ≤ 120 chars, no personal data
    language: str = "en"

class PlanStep(BaseModel):
    id: Literal["forecast","unmet_demand","inventory","transfers","trends","planner"]
    label: str
    status: Literal["running","done","skipped","error"]
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: str = ""
    data: Optional[dict] = None

class Evidence(BaseModel):
    kind: Literal["forecast","signals","inventory","trend"]
    text: str
    value: Optional[float] = None

class ActionProposal(BaseModel):
    action_id: str
    plan_id: str
    type: Literal["transfer","reorder","markdown","assortment"]
    store_id: str                     # destination store
    category: Category
    sku: Optional[str] = None
    size: Optional[str] = None
    quantity: int
    from_store_id: Optional[str] = None      # transfers only
    supplier_lead_days: Optional[int] = None # reorders only
    eta_date: str
    rationale: str                    # ≤ 300 chars
    evidence: list[Evidence]
    confidence: float = Field(ge=0, le=1)
    expected_revenue_protected_inr: int
    status: Literal["proposed","approved","rejected","executed"] = "proposed"
    created_at: str
    decided_at: Optional[str] = None

class Notification(BaseModel):
    notification_id: str
    session_id: str
    kind: Literal["back_in_stock","reserved","transfer_eta"]
    sku: str
    store_id: str
    message: str
    created_at: str
    read: bool = False


# ---------------------------------------------------------------------------
# Request bodies (contracts §5, routes table)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str = ""
    store_id: str = "CHN-TNG"
    image_base64: Optional[str] = None
    image_mime: Optional[Literal["image/jpeg", "image/png", "image/webp"]] = None
    language_hint: Optional[Literal["auto", "en", "hi", "ta"]] = "auto"


class ItemRequest(BaseModel):
    session_id: str
    sku: str
    size: str = "FREE"
    store_id: str = "CHN-TNG"


class PlanRequest(BaseModel):
    store_id: str = "CHN-TNG"
    category: Optional[Category] = None
    horizon_days: int = 21
    question: Optional[str] = None
    session_id: Optional[str] = None  # optional, only used for rate limiting


class AskRequest(BaseModel):
    store_id: str = "CHN-TNG"
    question: str
    session_id: Optional[str] = None
