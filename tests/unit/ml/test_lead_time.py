from ml.domain.lead_time import estimate_lead_days


def test_cooling_creeping_up_toward_threshold():
    # 5.6C over 7 days -> 0.8C/day; 110 - 103 = 7C left -> 8.75 days
    row = {"max_coolant_c": 103.0, "coolant_slope_7d": 5.6}
    assert round(estimate_lead_days("cooling", row), 2) == 8.75


def test_cooling_already_past_threshold_returns_none():
    row = {"max_coolant_c": 112.0, "coolant_slope_7d": 5.6}
    assert estimate_lead_days("cooling", row) is None


def test_cooling_flat_or_improving_trend_returns_none():
    assert estimate_lead_days("cooling", {"max_coolant_c": 95.0, "coolant_slope_7d": 0.0}) is None
    assert estimate_lead_days("cooling", {"max_coolant_c": 95.0, "coolant_slope_7d": -2.0}) is None


def test_lubrication_oil_pressure_falling_toward_threshold():
    # dropping 14 kPa over 7 days -> 2/day; 128 - 100 = 28 left -> 14 days
    row = {"min_oil_kpa": 128.0, "oil_kpa_slope_7d": -14.0}
    assert round(estimate_lead_days("lubrication", row), 2) == 14.0


def test_battery_charge_voltage_falling():
    row = {"min_charge_v": 13.2, "charge_v_slope_7d": -0.7}
    assert estimate_lead_days("battery", row) is not None


def test_brake_wear_pad_percentage_falling():
    row = {"min_brake_pad_pct": 30.0, "brake_pad_slope_7d": -3.5}
    assert estimate_lead_days("brake_wear", row) is not None


def test_misfire_has_no_estimator():
    assert estimate_lead_days("misfire", {}) is None


def test_tyre_pressure_falling_toward_threshold():
    # dropping 35 kPa over 7 days -> 5/day; 650 - 550 = 100 left -> 20 days
    row = {"min_tire_kpa": 650.0, "min_tire_kpa_slope_7d": -35.0}
    assert estimate_lead_days("tyre", row) == 20.0


def test_transmission_fluid_temp_rising():
    row = {"max_trans_c": 120.0, "trans_c_slope_7d": 7.0}
    assert estimate_lead_days("transmission", row) is not None


def test_ev_battery_cell_temp_rising():
    row = {"max_cell_temp_c": 50.0, "max_cell_temp_c_slope_7d": 5.0}
    assert estimate_lead_days("ev_battery", row) is not None


def test_barely_moving_slope_is_outside_the_horizon():
    # a barely-moving slope projects years away: not at risk, so no lead time (not a capped 30)
    assert estimate_lead_days("cooling", {"max_coolant_c": 20.0, "coolant_slope_7d": 0.001}) is None


def test_beyond_horizon_is_none_not_a_capped_30():
    # 0.1 degC/day from 95 -> 110 degC is 150 days out: not at risk within 30 days.
    assert estimate_lead_days("cooling", {"max_coolant_c": 95.0, "coolant_slope_7d": 0.7}) is None


def test_inside_horizon_boundary_is_kept():
    # exactly 30 days: (110 - 95) / (0.5 / 1 per day) = 30
    assert estimate_lead_days("cooling", {"max_coolant_c": 95.0, "coolant_slope_7d": 3.5}) == 30.0


def test_already_past_threshold_is_none():
    assert estimate_lead_days("cooling", {"max_coolant_c": 115.0, "coolant_slope_7d": 5.0}) is None
