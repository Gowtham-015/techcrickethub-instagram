import pytest
from instagram_cricket_balancer import InstagramCricketBalancer


def test_cricket_balancer_target_calculation():
    balancer = InstagramCricketBalancer()
    targets = balancer.calculate_targets(window=30)

    assert targets["min_cricket"] == 23
    assert targets["max_non_cricket"] == 7
    assert targets["target_pct"] == 75


def test_cricket_balancer_evaluation_balanced():
    balancer = InstagramCricketBalancer()

    # Create 30 items: 25 Cricket, 5 Tech
    items = [{"category": "cricket"} for _ in range(25)] + [{"category": "technology"} for _ in range(5)]
    metrics = balancer.evaluate_balance(items)

    assert metrics.status == "BALANCED"
    assert metrics.cricket_count == 25
    assert metrics.cricket_percentage == 83.3
    assert metrics.priority_boost_active is False


def test_cricket_balancer_evaluation_deficit():
    balancer = InstagramCricketBalancer()

    # Create 30 items: 20 Cricket (66.7%), 10 Tech (33.3%)
    items = [{"category": "cricket"} for _ in range(20)] + [{"category": "technology"} for _ in range(10)]
    metrics = balancer.evaluate_balance(items)

    assert metrics.status == "CRICKET_DEFICIT"
    assert metrics.cricket_count == 20
    assert metrics.cricket_percentage == 66.7
    assert metrics.priority_boost_active is True
