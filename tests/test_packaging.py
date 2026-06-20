"""Guard the critical packaging fix: the schema + design-packs must be resolvable.

This is what would have caught the wheel that shipped without ``schemas/`` and ``packs/``.
The CI also installs the built wheel and runs a smoke import, but these run in-tree too.
"""
import os

from matrix_designer._resources import packs_dir, schema_path
from matrix_designer.packs import load_pack
from matrix_designer.rules import rule_ids


def test_schema_is_resolvable():
    p = schema_path()
    assert os.path.exists(p), f"design-bundle.schema.json not found at {p}"


def test_real_packs_load_not_generic():
    game = load_pack("web-game-platformer-v1")
    assert game.get("id") == "web-game-platformer-v1"
    assert len(game.get("rules", [])) >= 1
    saas = load_pack("web-saas-product-v1")
    assert saas.get("id") == "web-saas-product-v1"


def test_rule_families_present():
    ids = rule_ids()
    families = {r.split("-")[0] for r in ids}
    assert {"DESIGN", "GAME", "APP"}.issubset(families)


def test_packs_dir_exists():
    assert os.path.isdir(packs_dir())
