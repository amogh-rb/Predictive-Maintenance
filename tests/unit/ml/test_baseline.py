from ml.domain import baseline


def _healthy_row(**overrides):
    row = {
        "any_dtc_today": 0,
        "max_coolant_c": 92.0,
        "min_oil_kpa": 300.0,
        "min_charge_v": 13.8,
        "min_brake_pad_pct": 60.0,
    }
    row.update(overrides)
    return row


def test_healthy_row_predicts_negative():
    assert baseline.predict(_healthy_row()) == 0


def test_active_dtc_predicts_positive():
    assert baseline.predict(_healthy_row(any_dtc_today=1)) == 1


def test_coolant_breach_predicts_positive():
    assert baseline.predict(_healthy_row(max_coolant_c=111.0)) == 1


def test_coolant_at_threshold_is_negative():
    assert baseline.predict(_healthy_row(max_coolant_c=baseline.COOLANT_ALERT_C)) == 0


def test_oil_pressure_breach_predicts_positive():
    assert baseline.predict(_healthy_row(min_oil_kpa=20.0)) == 1


def test_charge_v_breach_predicts_positive():
    assert baseline.predict(_healthy_row(min_charge_v=12.0)) == 1


def test_brake_pad_breach_predicts_positive():
    assert baseline.predict(_healthy_row(min_brake_pad_pct=5.0)) == 1


def test_missing_fields_default_to_negative():
    assert baseline.predict({}) == 0


def test_transmission_overheat_breach_predicts_positive():
    assert baseline.predict(_healthy_row(max_trans_c=140.0)) == 1


def test_tyre_pressure_breach_predicts_positive():
    assert baseline.predict(_healthy_row(min_tire_kpa=400.0)) == 1


def test_ev_cell_overtemp_breach_predicts_positive():
    assert baseline.predict(_healthy_row(max_cell_temp_c=70.0)) == 1
