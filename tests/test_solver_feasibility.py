"""Tests for the energy management solver."""

import pulp
import pytest

from homeassistant.core import HomeAssistant

DOMAIN = "energy_management"
INTEGRATION_MODE_MANAGE = "manage"
ELECTRIC_HEATER = "electric"
COMBI_HEATER = "combi"


@pytest.fixture
def coordinator_config():
    """Return default solver coordinator configuration."""
    return {
        "bat_capacity": 10.0,  # kWh
        "bat_power": 5.0,  # kW
        "min_soc": 20,  # %
        "max_soc": 80,  # %
        "inverter_power": "sensor.inverter_power",
        "initial_soc_entity": "sensor.battery_soc",
        "weather": "weather.home",
        "heater": "",
        "ac": "",
        "heater_power": 3000,
        "heater_volume": 100,
        "heater_type": ELECTRIC_HEATER,
        "integration_mode": INTEGRATION_MODE_MANAGE,
    }


@pytest.fixture
def mock_hass_with_entities(hass: HomeAssistant) -> HomeAssistant:
    """Set up mock Home Assistant with required entities."""
    hass.states.set("sensor.inverter_power", "9000")
    hass.states.set("sensor.battery_soc", "65.5")
    return hass


def build_and_solve_optimization(
    solar_forecast: list[float],
    load_forecast: list[float],
    secondary_load: list[float],
    buy_price: list[float],
    sell_price: list[float],
    initial_soc: float,
    bat_capacity: float,
    bat_power: float,
    inverter_power: float,
    min_soc_pct: float,
    max_soc_pct: float,
    ac_enabled: bool = False,
    heater_enabled: bool = False,
    heater_power: float = 0.0,
    heater_type: str = ELECTRIC_HEATER,
    heater_volume: float = 0.0,
) -> dict:
    """Build and solve the energy management LP problem.

    Returns a dictionary with optimization results.
    """
    H = len(solar_forecast)

    # Create optimization model
    m = pulp.LpProblem("EnergyManagement", pulp.LpMinimize)

    # Decision variables
    battery = pulp.LpVariable.dicts(
        "battery", range(H), cat=pulp.LpBinary
    )  # 1 if charging
    charge = pulp.LpVariable.dicts("charge", range(H), lowBound=0, upBound=bat_power)
    discharge = pulp.LpVariable.dicts(
        "discharge", range(H), lowBound=0, upBound=inverter_power
    )
    soc = pulp.LpVariable.dicts(
        "soc",
        range(H + 1),
        lowBound=0,
        upBound=bat_capacity,
    )

    grid = pulp.LpVariable.dicts("grid", range(H), cat=pulp.LpBinary)
    grid_import = pulp.LpVariable.dicts(
        "import", range(H), lowBound=0, upBound=inverter_power
    )
    grid_export = pulp.LpVariable.dicts(
        "export", range(H), lowBound=0, upBound=inverter_power
    )

    pen_low_soc = pulp.LpVariable.dicts("pen_low_soc", range(H), cat=pulp.LpBinary)

    v_ac = pulp.LpVariable.dicts("v_ac", range(H), cat=pulp.LpBinary)
    v_ewh = pulp.LpVariable.dicts("v_ewh", range(H), cat=pulp.LpBinary)

    obj_sum = pulp.LpVariable.dicts("obj_sum", range(H), cat=pulp.LpContinuous)

    M = 1000  # Big-M constant
    eff_charge = 0.97
    eff_discharge = 0.95

    p_ac = 1.1 if ac_enabled else 0
    p_ewh = heater_power if heater_enabled else 0

    # Initial SoC
    m += soc[0] == initial_soc

    # Heater constraints
    if heater_enabled and heater_type == ELECTRIC_HEATER:
        ewh_hours = heater_volume * 5 / heater_power / 100
        window_size = 3 if ewh_hours <= 8 else 1  # max hours in a row to turn on heater
        for i in range(H - window_size + 1):
            m += pulp.lpSum(v_ewh[t] for t in range(i, i + window_size)) <= 1
        m += pulp.lpSum(v_ewh[t] for t in range(H)) == ewh_hours

    elif heater_enabled and heater_type == COMBI_HEATER:
        for t in range(H):
            m += grid_import[t] <= M * (1 - v_ewh[t])
            m += discharge[t] <= M * (1 - v_ewh[t])

    # AC constraints
    if ac_enabled:
        for t in range(H):
            m += grid_import[t] <= M * (1 - v_ac[t])
            m += discharge[t] <= M * (1 - v_ac[t])

    # Hourly constraints
    min_soc_kwh = min_soc_pct / 100 * bat_capacity
    for t in range(H):
        # Grid constraints
        m += grid_import[t] <= inverter_power * grid[t]
        m += grid_export[t] <= inverter_power * (1 - grid[t])

        # Battery charge source
        m += charge[t] <= solar_forecast[t] + grid_import[t]
        m += charge[t] <= bat_power * battery[t]
        m += discharge[t] <= bat_power * (1 - battery[t])

        # Battery SoC dynamics
        m += (
            soc[t + 1] == soc[t] + charge[t] * eff_charge - discharge[t] / eff_discharge
        )

        # Low SoC penalty
        m += soc[t] - min_soc_kwh <= bat_capacity * (1 - pen_low_soc[t])
        m += soc[t] - min_soc_kwh >= -bat_capacity * pen_low_soc[t]

        # Hourly cost
        m += obj_sum[t] == (
            grid_import[t] * (buy_price[t] + 1.2)
            - grid_export[t] * (sell_price[t] - min(buy_price))
        )

        # Energy conservation
        m += (
            solar_forecast[t] + grid_import[t] + discharge[t]
            == load_forecast[t]
            + secondary_load[t]
            + p_ac * v_ac[t]
            + p_ewh * v_ewh[t]
            + charge[t]
            + grid_export[t]
        )

    # Objective function
    m += pulp.lpSum(
        [
            obj_sum[t] + pen_low_soc[t] * 5 - charge[t] * 1.2 - v_ewh[t] * 1.1 - v_ac[t]
            for t in range(H)
        ]
    )

    # Solve
    m.solve(pulp.PULP_CBC_CMD(msg=False))

    if m.status != pulp.LpStatusOptimal:
        raise ValueError(f"Optimization failed: {pulp.LpStatus[m.status]}")

    return {
        "status": pulp.LpStatus[m.status],
        "objective": pulp.value(m.objective),
        "charge": [charge[t].varValue or 0 for t in range(H)],
        "discharge": [discharge[t].varValue or 0 for t in range(H)],
        "grid_import": [grid_import[t].varValue or 0 for t in range(H)],
        "grid_export": [grid_export[t].varValue or 0 for t in range(H)],
        "soc": [soc[t].varValue or 0 for t in range(H + 1)],
        "ac_enabled": [bool(v_ac[t].varValue) for t in range(H)],
        "ewh_enabled": [bool(v_ewh[t].varValue) for t in range(H)],
    }


class TestHighPVLowPriceScenarios:
    """Test Case 1: High PV production, low electricity price."""

    def test_high_pv_low_price_maximizes_battery_charging(self):
        """Test that battery charges preferentially with high PV and low price."""
        solar_forecast = [4.0] * 24  # High PV throughout day
        load_forecast = [1.0] * 24  # Baseline load
        secondary_load = [0.2] * 24
        buy_price = [0.05] * 24  # Low electricity price
        sell_price = [0.02] * 24
        initial_soc = 6.5  # 65% of 10 kWh

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # Battery should charge significantly
        total_charge = sum(result["charge"])
        total_discharge = sum(result["discharge"])
        assert total_charge > total_discharge, "Should charge more than discharge"

        # Final SoC should be higher than initial (if below max)
        assert result["soc"][-1] >= result["soc"][0], "Final SoC >= Initial"

    def test_high_pv_activates_water_heater(self):
        """Test that controllable loads activate with high PV."""
        solar_forecast = [0.0] * 8 + [3.05] * 8 + [0.0] * 8
        load_forecast = [0.8] * 24
        secondary_load = [0.2] * 24
        buy_price = [5.03] * 24
        sell_price = [1.01] * 24
        initial_soc = 6.0

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
            heater_enabled=True,
            heater_power=1,
            heater_volume=100,
            heater_type=ELECTRIC_HEATER,
        )

        assert result["status"] == "Optimal"
        # Water heater should activate during high PV period
        total_ewh = sum(result["ewh_enabled"])
        assert total_ewh > 0, "Water heater should activate"

        # EWH should activate during daytime hours primarily
        daytime_ewh = sum(result["ewh_enabled"][6:18])
        nighttime_ewh = sum(result["ewh_enabled"][0:6] + result["ewh_enabled"][18:])
        assert daytime_ewh >= nighttime_ewh, "More EWH activity during day"


class TestLowPVHighPriceScenarios:
    """Test Case 2: Low PV production, high electricity price."""

    def test_low_pv_high_price_respects_soc_minimum(self):
        """Test that minimum SoC is never violated."""
        solar_forecast = [0.3] * 24
        load_forecast = [1.2] * 24
        secondary_load = [0.3] * 24
        buy_price = [0.32] * 24
        sell_price = [0.05] * 24
        initial_soc = 4.0  # Starting 40% (well above min 20%)
        min_soc_kwh = 2.0  # 20% of 10 kWh

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # Verify all SoC values respect minimum
        for soc_value in result["soc"][:-1]:
            assert soc_value >= min_soc_kwh - 0.01, (
                f"SoC {soc_value} violates minimum {min_soc_kwh}"
            )

    def test_low_pv_no_grid_export_with_low_sell_price(self):
        """Test that grid export is avoided when uneconomical."""
        solar_forecast = [0.5] * 24
        load_forecast = [1.0] * 24
        secondary_load = [0.2] * 24
        buy_price = [0.35] * 24
        sell_price = [0.02] * 24  # Very low export price
        initial_soc = 5.0

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # Export should be minimal or zero
        total_export = sum(result["grid_export"])
        assert total_export < 2, "Minimize uneconomical export"


class TestLowSOCScenarios:
    """Test Case 3: Low battery SoC scenarios."""

    def test_low_soc_prioritizes_charging_at_low_tariff(self):
        """Test charging priority during low-tariff hours."""
        solar_forecast = [0.3] * 24
        load_forecast = [1.0] * 24
        secondary_load = [0.2] * 24
        # Low prices early, high prices later
        buy_price = [0.05] * 8 + [0.25] * 8 + [0.15] * 8
        sell_price = [0.02] * 24
        initial_soc = 2.5  # 25% (near minimum 20%)

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # Charging should concentrate in early hours (low price)
        early_hours_charge = sum(result["charge"][:8])
        middle_hours_charge = sum(result["charge"][8:16])
        assert early_hours_charge > middle_hours_charge, (
            "Prioritize charging during low-tariff hours"
        )

    def test_low_soc_restricts_discharge(self):
        """Test that discharge is restricted near minimum SoC."""
        solar_forecast = [0.2] * 24
        load_forecast = [1.5] * 24
        secondary_load = [0.3] * 24
        buy_price = [0.20] * 24
        sell_price = [0.08] * 24
        initial_soc = 2.2  # 22% (very close to minimum 20%)

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"

        # Verify minimum SoC is maintained
        min_soc_kwh = 2.0
        for soc_value in result["soc"][:-1]:
            assert soc_value >= min_soc_kwh - 0.01


class TestHighSOCScenarios:
    """Test Case 4: High battery SoC scenarios."""

    def test_high_soc_delays_charging(self):
        """Test that charging is delayed when battery is nearly full."""
        solar_forecast = [0.4] * 24
        load_forecast = [0.8] * 24
        secondary_load = [0.2] * 24
        # High price early, low price later
        buy_price = [0.25] * 8 + [0.05] * 8 + [0.20] * 8
        sell_price = [0.10] * 24
        initial_soc = 7.8  # 78% (near maximum 80%)
        max_soc_kwh = 8.0

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # Charging should be minimal in high tariff (already full)
        total_charge = sum(result["charge"][:8])
        assert total_charge < 3, "Minimize charging when near maximum"

        # Final SoC should not exceed maximum
        assert result["soc"][-1] <= max_soc_kwh + 0.01

    def test_high_soc_avoids_export(self):
        """Test grid export minimization with high initial SoC."""
        solar_forecast = [0.8] * 24
        load_forecast = [0.5] * 24
        secondary_load = [0.2] * 24
        buy_price = [0.10] * 24
        sell_price = [0.08] * 24
        initial_soc = 7.5  # 75% (already high)

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # Export should be avoided due to high SOC constraint
        total_export = sum(result["grid_export"])
        assert total_export < 5, "Avoid export when battery is full"


class TestEnergyConservation:
    """Test energy conservation constraints."""

    def test_energy_balance_satisfied(self):
        """Test that energy conservation equation is satisfied."""
        solar_forecast = [2.0] * 24
        load_forecast = [1.0] * 24
        secondary_load = [0.2] * 24
        buy_price = [0.10] * 24
        sell_price = [0.05] * 24
        initial_soc = 5.0

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # Verify energy balance equation at each hour
        for t in range(24):
            supply = (
                solar_forecast[t] + result["grid_import"][t] + result["discharge"][t]
            )
            demand = (
                load_forecast[t]
                + secondary_load[t]
                + result["charge"][t]
                + result["grid_export"][t]
            )
            # Allow small tolerance for numerical precision
            assert abs(supply - demand) < 0.01, (
                f"Energy imbalance at hour {t}: {supply} != {demand}"
            )

    def test_simultaneous_charge_discharge_prevented(self):
        """Test that battery cannot charge and discharge simultaneously."""
        solar_forecast = [3.0] * 24
        load_forecast = [1.0] * 24
        secondary_load = [0.2] * 24
        buy_price = [0.10] * 24
        sell_price = [0.08] * 24
        initial_soc = 5.0

        result = build_and_solve_optimization(
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            secondary_load=secondary_load,
            buy_price=buy_price,
            sell_price=sell_price,
            initial_soc=initial_soc,
            bat_capacity=10.0,
            bat_power=5.0,
            inverter_power=9.0,
            min_soc_pct=20,
            max_soc_pct=80,
        )

        assert result["status"] == "Optimal"
        # At each hour, charge and discharge should not both be significant
        for t in range(24):
            if result["charge"][t] > 0.1:  # Charging
                assert result["discharge"][t] < 0.01, (
                    f"Simultaneous charge/discharge at hour {t}"
                )
            if result["discharge"][t] > 0.1:  # Discharging
                assert result["charge"][t] < 0.01, (
                    f"Simultaneous charge/discharge at hour {t}"
                )
