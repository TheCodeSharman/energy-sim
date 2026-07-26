"""CostBreakdown value object: net = import cost - export credit + supply charge."""
from energy_sim.domain.cost import CostBreakdown
from energy_sim.domain.money import Money


def test_net_cost_combines_components():
    breakdown = CostBreakdown(
        import_cost=Money.from_dollars(10),
        export_credit=Money.from_dollars(2),
        supply_charge=Money.from_dollars(1),
        peak_import_kwh=5.0,
        offpeak_import_kwh=3.0,
    )
    assert breakdown.net_cost == Money.from_dollars(9)  # 10 - 2 + 1


def test_usage_cost_excludes_supply():
    # "usage-only" figure used for validation against Aurora's usage dollars.
    breakdown = CostBreakdown(
        import_cost=Money.from_dollars(10),
        export_credit=Money.from_dollars(2),
        supply_charge=Money.from_dollars(1),
        peak_import_kwh=5.0,
        offpeak_import_kwh=3.0,
    )
    assert breakdown.usage_cost == Money.from_dollars(8)  # 10 - 2, no supply
