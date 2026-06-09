"""Creative behaviour lock — variant generation from briefs.

Tests cover:
  - dry generator (deterministic placeholders)
  - unknown generator falls back to dry
  - variant structure and determinism
"""

from __future__ import annotations

import pytest

from drip.creative import Creative, CreativeVariant

# ---------------------------------------------------------------------------
# dry generator
# ---------------------------------------------------------------------------


def test_dry_produces_n_variants() -> None:
    c = Creative(generator="dry")
    brief = "Double down on winning hook"
    variants = c.produce(brief, n=3)
    assert len(variants) == 3
    for v in variants:
        assert isinstance(v, CreativeVariant)


def test_dry_variant_structure() -> None:
    c = Creative(generator="dry")
    variants = c.produce("Test brief", n=2, kind="video")
    assert len(variants) == 2
    v = variants[0]
    assert v.brief == "Test brief"
    assert v.asset_kind == "video"
    assert v.asset_ref == "(dry-run)"
    assert v.generator == "dry"
    assert len(v.variant_id) > 0  # like "abc123-1"


def test_dry_is_deterministic() -> None:
    """Same brief + same generator → same variant IDs."""
    brief = "Scale the winner with fresh hooks"
    a = Creative(generator="dry").produce(brief, n=3)
    b = Creative(generator="dry").produce(brief, n=3)
    assert len(a) == len(b)
    for va, vb in zip(a, b, strict=True):
        assert va.variant_id == vb.variant_id
        assert va.asset_ref == vb.asset_ref


def test_dry_variant_ids_are_unique() -> None:
    variants = Creative(generator="dry").produce("Brief", n=5)
    ids = {v.variant_id for v in variants}
    assert len(ids) == 5


# ---------------------------------------------------------------------------
# unknown generator → dry fallback
# ---------------------------------------------------------------------------


def test_unknown_generator_falls_back_to_dry() -> None:
    c = Creative(generator="nonexistent-generator-xyz")
    variants = c.produce("Test brief", n=2)
    assert len(variants) == 2
    assert variants[0].generator == "dry"
    assert variants[0].asset_ref == "(dry-run)"


def test_empty_brief() -> None:
    c = Creative(generator="dry")
    variants = c.produce("", n=1)
    assert len(variants) == 1
    assert variants[0].brief == ""


# ---------------------------------------------------------------------------
# live generators fall back to dry when their API key is absent
# ---------------------------------------------------------------------------

# gpt-image / seedance hit a real adapter only when their key is set; offline
# (CI, no key) they degrade to deterministic placeholders so the loop still
# runs. The real-generation path needs the SDK + network and is not unit-tested.


def test_gpt_image_without_key_falls_back_to_dry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    variants = Creative(generator="gpt-image").produce("Brief", n=2)
    assert len(variants) == 2
    assert variants[0].generator == "dry"
    assert variants[0].asset_ref == "(dry-run)"


def test_seedance_without_key_falls_back_to_dry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    variants = Creative(generator="seedance").produce("Brief", n=1)
    assert len(variants) == 1
    assert variants[0].generator == "dry"


def test_produce_default_generator() -> None:
    """Creative() defaults to 'dry'."""
    c = Creative()
    assert c.generator == "dry"
    variants = c.produce("Brief", n=1)
    assert len(variants) == 1
    assert variants[0].generator == "dry"


def test_default_kind_is_image() -> None:
    c = Creative(generator="dry")
    variants = c.produce("Brief", n=1)  # kind defaults to "image"
    assert variants[0].asset_kind == "image"
