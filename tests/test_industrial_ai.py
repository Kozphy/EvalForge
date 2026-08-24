import pytest

from app.industrial_ai import (
    EntityKind,
    IndustrialEntity,
    IndustrialValidator,
    UnavailableVisionAdapter,
    build_tiles,
    merge_layers,
)


def test_build_tiles_covers_large_page_with_overlap():
    tiles = build_tiles(page=1, page_width=2000, page_height=1500, tile_size=1024, overlap=128)
    assert len(tiles) == 4
    assert tiles[0].x == 0
    assert tiles[1].x == 896
    assert max(t.x + t.width for t in tiles) == 2000
    assert max(t.y + t.height for t in tiles) == 1500


def test_build_tiles_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        build_tiles(page=1, page_width=100, page_height=100, tile_size=64, overlap=64)


def test_validator_flags_low_confidence_and_tag_without_number():
    entity = IndustrialEntity(
        kind=EntityKind.TAG,
        value="PT",
        page=1,
        confidence=0.4,
        source_layer="vision",
    )
    findings = IndustrialValidator().validate([entity])
    assert {f.code for f in findings} == {"low_confidence", "tag_without_numeric_identifier"}


def test_merge_layers_keeps_provenance():
    vector = IndustrialEntity(
        kind=EntityKind.EQUIPMENT,
        value="P-101",
        page=1,
        confidence=0.95,
        source_layer="vector_text",
    )
    vision = IndustrialEntity(
        kind=EntityKind.INSTRUMENT,
        value="PT-101",
        page=1,
        confidence=0.88,
        source_layer="qwen-vl",
    )
    result = merge_layers(document_id="demo", vector_entities=[vector], vision_entities=[vision])
    assert len(result.entities) == 2
    assert result.extraction_layers == ["qwen-vl", "vector_text"]


def test_unavailable_adapter_never_fabricates_execution():
    adapter = UnavailableVisionAdapter("qwen-vl", "GPU is not configured")
    with pytest.raises(RuntimeError, match="NOT_RUN"):
        adapter.extract(image_bytes=b"fake", page=1)
