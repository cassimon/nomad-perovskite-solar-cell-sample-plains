"""The sample's jv / eqe / stability sections, derived from linked measurements.

These cover what `_populate_from_*` writes once nomad-chose actually fills the
measurement entries (`jv_curve`, `eqe_data`, and MPPTracking's native `time` /
`efficiency`). Before that, `jv_curve` was empty and every one of these sections
stayed unset.
"""

import numpy as np
import pytest
from baseclasses.solar_energy import SolarCellEQECustom
from baseclasses.solar_energy.eqemeasurement import EQEMeasurement
from baseclasses.solar_energy.jvmeasurement import JVMeasurement, SolarCellJVCurveCustom
from baseclasses.solar_energy.mpp_tracking import MPPTracking, StabilityFiguresOfMerit
from nomad.units import ureg
from perovskite_solar_cell_database.schema_sections.jv import JV

from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import (
    PerovskiteSolarCellSampleArea,
)


@pytest.fixture
def sample():
    sample = PerovskiteSolarCellSampleArea()
    sample.jv = JV()
    return sample


def scan(name, *, efficiency, voc, jsc, ff, vmp=None, jmp=None, rs=None, rsh=None):
    """A curve as nomad-chose now builds it from the instrument's summary table."""
    curve = SolarCellJVCurveCustom()
    curve.cell_name = name
    curve.dark = False
    curve.efficiency = efficiency
    curve.open_circuit_voltage = voc * ureg('V')
    curve.short_circuit_current_density = jsc * ureg('mA/cm**2')
    curve.fill_factor = ff
    if vmp is not None:
        curve.potential_at_maximum_power_point = vmp * ureg('V')
    if jmp is not None:
        curve.current_density_at_maximun_power_point = jmp * ureg('mA/cm**2')
    if rs is not None:
        curve.series_resistance = rs * ureg('ohm*cm**2')
    if rsh is not None:
        curve.shunt_resistance = rsh * ureg('ohm*cm**2')
    curve.voltage = np.linspace(0, 1.2, 5) * ureg('V')
    curve.current_density = np.linspace(-22, 0, 5) * ureg('mA/cm**2')
    return curve


# The real FW/RV rows of tests/data/0001_..._Stability (JV)_AI03-1A.txt.
def chose_measurement():
    measurement = JVMeasurement()
    measurement.jv_curve = [
        scan('FW', efficiency=2.12, voc=0.530612, jsc=15.754854, ff=0.2538,
             vmp=0.253178, jmp=8.381736, rs=38.16, rsh=47.97),
        scan('RV', efficiency=3.67, voc=0.539999, jsc=20.841486, ff=0.3261,
             vmp=0.339130, jmp=10.823427, rs=13.05, rsh=52.83),
    ]
    return measurement


def test_forward_and_reverse_scans_land_in_their_own_fields(sample):
    """The database has a field per scan direction, so neither is averaged away."""
    sample._populate_from_jv([chose_measurement()])
    jv = sample.jv

    assert jv.forward_scan_PCE == pytest.approx(2.12)
    assert jv.forward_scan_Voc.magnitude == pytest.approx(0.530612)
    assert jv.forward_scan_FF == pytest.approx(0.2538)
    assert jv.forward_scan_series_resistance.magnitude == pytest.approx(38.16)

    assert jv.reverse_scan_PCE == pytest.approx(3.67)
    assert jv.reverse_scan_Jsc.magnitude == pytest.approx(20.841486)
    assert jv.reverse_scan_Jmp.magnitude == pytest.approx(10.823427)
    assert jv.reverse_scan_shunt_resistance.magnitude == pytest.approx(52.83)


def test_defaults_take_the_best_scan_and_record_which_one(sample):
    sample._populate_from_jv([chose_measurement()])
    jv = sample.jv

    # RV is the better scan (3.67 % vs 2.12 %).
    assert jv.default_PCE == pytest.approx(3.67)
    assert jv.default_Voc.magnitude == pytest.approx(0.539999)
    assert jv.default_PCE_scan_direction == 'Reversed'
    assert jv.default_Voc_scan_direction == 'Reversed'


def test_hysteresis_index_is_derived_from_the_scan_pair(sample):
    sample._populate_from_jv([chose_measurement()])
    # (PCE_rev - PCE_fwd) / PCE_rev = (3.67 - 2.12) / 3.67
    assert sample.jv.hysteresis_index == pytest.approx((3.67 - 2.12) / 3.67)


def test_hysteresis_index_needs_both_directions(sample):
    measurement = JVMeasurement()
    measurement.jv_curve = [
        scan('RV', efficiency=3.67, voc=0.54, jsc=20.8, ff=0.33),
    ]
    sample._populate_from_jv([measurement])
    assert sample.jv.hysteresis_index is None
    assert sample.jv.reverse_scan_PCE == pytest.approx(3.67)
    assert sample.jv.forward_scan_PCE is None


def test_eqe_measurement_populates_the_eqe_section(sample):
    """`_populate_from_eqe` used to probe attributes EQEMeasurement does not have,
    so it silently wrote nothing at all."""
    data = SolarCellEQECustom(
        photon_energy_array=np.linspace(1.3, 3.0, 40),
        raw_photon_energy_array=np.linspace(1.3, 3.0, 40),
        eqe_array=np.linspace(0.05, 0.85, 40),
        raw_eqe_array=np.linspace(0.05, 0.85, 40),
    )
    data.bandgap_eqe = 1.72 * ureg('eV')

    measurement = EQEMeasurement()
    measurement.eqe_data = [data]

    sample._populate_from_eqe(measurement)

    assert sample.eqe is not None
    assert sample.eqe.measured is True
    assert sample.eqe.bandgap_eqe.magnitude == pytest.approx(1.72)
    assert len(sample.eqe.eqe_array) == 40


def test_mppt_populates_stability_and_stabilised(sample):
    measurement = MPPTracking()
    measurement.time = np.array([0.0, 1800.0, 3600.0]) * ureg('s')
    measurement.efficiency = np.array([10.0, 9.5, 9.0])
    figures = StabilityFiguresOfMerit()
    figures.T80 = 500.0 * ureg('hour')
    measurement.results = [figures]

    sample._populate_from_mppt(measurement)

    # The stabilised PCE is the last valid point of the track.
    assert sample.stabilised.performance_PCE == pytest.approx(9.0)
    assert sample.stabilised.performance_measured is True
    assert sample.stability.PCE_end_of_experiment == pytest.approx(9.0)
    assert sample.stability.PCE_T80.magnitude == pytest.approx(500.0)
    # 3600 s of track, stated in the section's own unit (hours).
    assert sample.stability.time_total_exposure.to('hour').magnitude == pytest.approx(1.0)


def test_a_driven_cell_is_not_recorded_as_a_stabilised_pce(sample):
    """A track that opens above Voc has the cell consuming power (negative
    efficiency). That is not a PCE, and must not be stored as one."""
    measurement = MPPTracking()
    measurement.time = np.array([0.0, 1800.0]) * ureg('s')
    measurement.efficiency = np.array([-17.57, -16.0])  # driven the whole way
    measurement.results = [StabilityFiguresOfMerit()]

    sample._populate_from_mppt(measurement)

    assert sample.stabilised is None
    assert sample.jv.default_PCE is None


def test_a_jv_derived_pce_still_beats_the_mppt_fallback(sample):
    sample._populate_from_jv([chose_measurement()])
    measurement = MPPTracking()
    measurement.time = np.array([0.0, 3600.0]) * ureg('s')
    measurement.efficiency = np.array([1.0, 0.5])
    sample._populate_from_mppt(measurement)

    assert sample.jv.default_PCE == pytest.approx(3.67)
    # …but the stabilised value is still recorded in its own place.
    assert sample.stabilised.performance_PCE == pytest.approx(0.5)
