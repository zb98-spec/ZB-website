"""Unit tests: pure functions only, no Flask app, no database, no HTTP.

Run these constantly while developing - they need nothing but the
interpreter and should complete in a fraction of a second.
"""

from decimal import Decimal

from app.recipes import _parse_quantity, _parse_servings, format_qty


def test_format_qty_none_is_blank():
    assert format_qty(None) == ""


def test_format_qty_integral_value_has_no_decimal_point():
    assert format_qty(Decimal("4")) == "4"
    assert format_qty(Decimal("4.0")) == "4"


def test_format_qty_strips_trailing_zeros():
    assert format_qty(Decimal("1.500")) == "1.5"
    assert format_qty(Decimal("0.250")) == "0.25"


def test_parse_servings_valid():
    assert _parse_servings("4") == 4
    assert _parse_servings(4) == 4


def test_parse_servings_rejects_zero_and_negative():
    assert _parse_servings("0") is None
    assert _parse_servings("-2") is None


def test_parse_servings_rejects_non_numeric():
    assert _parse_servings("many") is None
    assert _parse_servings(None) is None


def test_parse_quantity_valid():
    assert _parse_quantity("2.5") == Decimal("2.5")


def test_parse_quantity_blank_is_none():
    assert _parse_quantity("") is None
    assert _parse_quantity("   ") is None
    assert _parse_quantity(None) is None


def test_parse_quantity_non_numeric_is_none():
    assert _parse_quantity("a lot") is None
