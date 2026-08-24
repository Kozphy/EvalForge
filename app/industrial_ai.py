from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Protocol

from pydantic import BaseModel, Field


class EntityKind(str, Enum):
    EQUIPMENT = "equipment"
    INSTRUMENT = "instrument"
    TAG = "tag"
    CONNECTION = "connection"
    SYMBOL = "symbol"


class BoundingBox(BaseModel):
    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)

    def model_post_init(self, __context: object) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bounding box maximums must be >= minimums")


class IndustrialEntity(BaseModel):
    kind: EntityKind
    value: str = Field(min_length=1)
    page: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    source_bbox: BoundingBox | None = None
    source_layer: str


class ValidationFinding(BaseModel):
    code: str
    severity: str
    message: str
    entity_index: int | None = None


class ExtractionResult(BaseModel):
    document_id: str
    entities: list[IndustrialEntity]
    findings: list[ValidationFinding] = Field(default_factory=list)
    extraction_layers: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class Tile:
    page: int
    x: int
    y: int
    width: int
    height: int


def build_tiles(
    *,
    page: int,
    page_width: int,
    page_height: int,
    tile_size: int = 1024,
    overlap: int = 128,
) -> list[Tile]:
    """Create deterministic overlapping tiles for high-resolution drawings.

    The function is model-agnostic and can be used by Qwen-VL, LLaVA,
    Florence-2, or another vision backend.
    """
    if page < 1:
        raise ValueError("page must be >= 1")
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page dimensions must be positive")
    if tile_size <= 0:
        raise ValueError("tile_size must be positive")
    if overlap < 0 or overlap >= tile_size:
        raise ValueError("overlap must satisfy 0 <= overlap < tile_size")

    step = tile_size - overlap
    tiles: list[Tile] = []
    y = 0
    while y < page_height:
        x = 0
        height = min(tile_size, page_height - y)
        while x < page_width:
            width = min(tile_size, page_width - x)
            tiles.append(Tile(page=page, x=x, y=y, width=width, height=height))
            if x + tile_size >= page_width:
                break
            x += step
        if y + tile_size >= page_height:
            break
        y += step
    return tiles


class VisionAdapter(Protocol):
    """Interchangeable interface for multimodal document models."""

    name: str

    def extract(self, *, image_bytes: bytes, page: int) -> list[IndustrialEntity]: ...


class UnavailableVisionAdapter:
    """Explicit placeholder for optional GPU/model integrations.

    This adapter deliberately raises instead of pretending a model ran.
    """

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason

    def extract(self, *, image_bytes: bytes, page: int) -> list[IndustrialEntity]:
        del image_bytes, page
        raise RuntimeError(f"{self.name} adapter is NOT_RUN: {self.reason}")


class IndustrialValidator:
    """Lightweight ISA-5.1-inspired structural checks.

    This is not a formal standards-compliance engine. It provides reusable
    validation hooks without bundling copyrighted standards text.
    """

    def validate(self, entities: Iterable[IndustrialEntity]) -> list[ValidationFinding]:
        rows = list(entities)
        findings: list[ValidationFinding] = []

        seen: dict[tuple[EntityKind, str, int], int] = {}
        for idx, entity in enumerate(rows):
            key = (entity.kind, entity.value.strip().upper(), entity.page)
            if key in seen:
                findings.append(
                    ValidationFinding(
                        code="duplicate_entity",
                        severity="warning",
                        message=f"Duplicate {entity.kind.value} '{entity.value}' on page {entity.page}",
                        entity_index=idx,
                    )
                )
            else:
                seen[key] = idx

            if entity.confidence < 0.5:
                findings.append(
                    ValidationFinding(
                        code="low_confidence",
                        severity="review",
                        message=f"Low-confidence extraction for '{entity.value}'",
                        entity_index=idx,
                    )
                )

            if entity.kind in {EntityKind.TAG, EntityKind.INSTRUMENT} and not any(
                char.isdigit() for char in entity.value
            ):
                findings.append(
                    ValidationFinding(
                        code="tag_without_numeric_identifier",
                        severity="review",
                        message=f"Tag-like entity '{entity.value}' has no numeric identifier",
                        entity_index=idx,
                    )
                )

        return findings


def merge_layers(
    *,
    document_id: str,
    vector_entities: Iterable[IndustrialEntity] = (),
    vision_entities: Iterable[IndustrialEntity] = (),
    validator: IndustrialValidator | None = None,
) -> ExtractionResult:
    entities = [*vector_entities, *vision_entities]
    layers = sorted({entity.source_layer for entity in entities})
    active_validator = validator or IndustrialValidator()
    return ExtractionResult(
        document_id=document_id,
        entities=entities,
        findings=active_validator.validate(entities),
        extraction_layers=layers,
    )
