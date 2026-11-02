"""Synthetic example test module (fake shop — obviously invented data).

This module intentionally has an import side effect (a print) so the README can
show that collection imports test modules even though no test body or fixture
runs during --collect-only.
"""

print("example: importing test_example_shop.py (collection side effect)")

import pytest


@pytest.fixture
def cart():
    """Never executed during --collect-only."""
    return {"items": [], "discount": 0}


def test_add_item(cart):
    cart["items"].append("example-item-1")
    assert cart["items"] == ["example-item-1"]


def test_apply_discount_v2(cart):
    cart["discount"] = 10
    assert cart["discount"] == 10


@pytest.mark.parametrize("method", ["card", "paypal"], ids=["card", "paypal"])
def test_checkout(cart, method):
    assert method in {"card", "paypal"}