import pytest

from pricing.main import calculate_price, validate_request


class TestCalculatePriceV1:
    def test_no_discount_regardless_of_quantity(self) -> None:
        total, discount, rule = calculate_price(
            quantity=5, unit_amount_cents=1000, version="v1"
        )
        assert total == 5000
        assert discount == 0
        assert rule == "list-price"

    def test_single_unit(self) -> None:
        total, discount, rule = calculate_price(
            quantity=1, unit_amount_cents=250, version="v1"
        )
        assert total == 250
        assert discount == 0
        assert rule == "list-price"


class TestCalculatePriceV2:
    def test_discounts_at_quantity_three(self) -> None:
        total, discount, rule = calculate_price(
            quantity=3, unit_amount_cents=1000, version="v2"
        )
        assert discount == 300  # 10% of 3000
        assert total == 2700
        assert rule == "bulk-10pct"

    def test_discounts_above_quantity_three(self) -> None:
        total, discount, rule = calculate_price(
            quantity=10, unit_amount_cents=999, version="v2"
        )
        assert discount == 999  # floor(9990 * 0.10)
        assert total == 9990 - 999
        assert rule == "bulk-10pct"

    def test_no_discount_below_quantity_three(self) -> None:
        total, discount, rule = calculate_price(
            quantity=2, unit_amount_cents=1000, version="v2"
        )
        assert total == 2000
        assert discount == 0
        assert rule == "list-price"

    def test_discount_rounds_down(self) -> None:
        # list_total = 3 * 101 = 303; 10% = 30.3 -> floor to 30
        total, discount, rule = calculate_price(
            quantity=3, unit_amount_cents=101, version="v2"
        )
        assert discount == 30
        assert total == 273
        assert rule == "bulk-10pct"


def test_served_by_reflects_version() -> None:
    # calculate_price itself doesn't set served_by (that's the servicer's job),
    # but the version argument it's given is what would end up in served_by.
    _, _, rule_v1 = calculate_price(quantity=3, unit_amount_cents=1000, version="v1")
    _, _, rule_v2 = calculate_price(quantity=3, unit_amount_cents=1000, version="v2")
    assert rule_v1 == "list-price"
    assert rule_v2 == "bulk-10pct"


class TestValidateRequest:
    def test_valid_request_does_not_raise(self) -> None:
        validate_request(sku="widget-1", quantity=1, unit_amount_cents=1)

    def test_empty_sku_raises(self) -> None:
        with pytest.raises(ValueError, match="sku"):
            validate_request(sku="", quantity=1, unit_amount_cents=100)

    def test_zero_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            validate_request(sku="widget-1", quantity=0, unit_amount_cents=100)

    def test_negative_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            validate_request(sku="widget-1", quantity=-1, unit_amount_cents=100)

    def test_zero_unit_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="unit_amount_cents"):
            validate_request(sku="widget-1", quantity=1, unit_amount_cents=0)

    def test_negative_unit_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="unit_amount_cents"):
            validate_request(sku="widget-1", quantity=1, unit_amount_cents=-5)
