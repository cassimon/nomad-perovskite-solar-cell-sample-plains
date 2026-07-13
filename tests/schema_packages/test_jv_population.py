import numpy as np
import pytest
from baseclasses.solar_energy.jvmeasurement import JVMeasurement, SolarCellJVCurveCustom
from baseclasses.solar_energy.mpp_tracking import MPPTracking
from nomad.units import ureg
from perovskite_solar_cell_database.schema_sections.jv import JV

from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import (
    PerovskiteSolarCellSampleArea,
)
from nomad_perovskite_solar_cell_sample_plains.utils import create_cell_stack_figure


def make_curve(  # noqa: PLR0913
    cell_name,
    efficiency=None,
    voc=None,
    jsc=None,
    fill_factor=None,
    dark=False,
):
    """Builds a single JV curve as it appears on a JVMeasurement."""
    curve = SolarCellJVCurveCustom()
    curve.cell_name = cell_name
    curve.dark = dark
    if efficiency is not None:
        curve.efficiency = efficiency
    if voc is not None:
        curve.open_circuit_voltage = voc * ureg('V')
    if jsc is not None:
        curve.short_circuit_current_density = jsc * ureg('mA/cm**2')
    if fill_factor is not None:
        curve.fill_factor = fill_factor
    curve.voltage = np.linspace(0, 1.2, 5) * ureg('V')
    curve.current_density = np.linspace(-22, 0, 5) * ureg('mA/cm**2')
    return curve


def make_jv_measurement(*curves):
    measurement = JVMeasurement()
    measurement.jv_curve = list(curves)
    return measurement


@pytest.fixture
def sample():
    sample = PerovskiteSolarCellSampleArea()
    sample.jv = JV()
    return sample


def test_defaults_come_from_the_best_curve_across_all_measurements(sample):
    """The measured values live on the jv_curve subsections, not on the JVMeasurement.

    All defaults must be taken from the same best-performing curve, so that they
    describe one consistent measurement rather than a mix of several.
    """
    first = make_jv_measurement(
        make_curve('c1-fwd', efficiency=17.2, voc=1.10, jsc=21.0, fill_factor=0.74),
        make_curve('c1-rev', efficiency=18.5, voc=1.12, jsc=21.5, fill_factor=0.77),
    )
    second = make_jv_measurement(
        make_curve('c2-fwd', efficiency=19.8, voc=1.15, jsc=22.9, fill_factor=0.75),
    )

    sample._populate_from_jv([first, second])

    assert sample.jv.default_PCE == pytest.approx(19.8)
    assert sample.jv.default_Voc.magnitude == pytest.approx(1.15)
    assert sample.jv.default_Jsc.magnitude == pytest.approx(22.9)
    assert sample.jv.default_FF == pytest.approx(0.75)


def test_dark_curves_are_ignored(sample):
    measurement = make_jv_measurement(
        make_curve('light', efficiency=18.5, voc=1.12, jsc=21.5, fill_factor=0.77),
        make_curve('dark', efficiency=99.9, voc=9.9, jsc=99.9, fill_factor=0.99, dark=True),
    )

    sample._populate_from_jv([measurement])

    assert sample.jv.default_PCE == pytest.approx(18.5)


def test_curves_are_not_duplicated_when_normalize_runs_again(sample):
    measurement = make_jv_measurement(
        make_curve('c1-fwd', efficiency=17.2, voc=1.10, jsc=21.0, fill_factor=0.74),
        make_curve('c1-rev', efficiency=18.5, voc=1.12, jsc=21.5, fill_factor=0.77),
    )

    sample._populate_from_jv([measurement])
    sample._populate_from_jv([measurement])

    assert len(sample.jv.jv_curve) == 2
    assert [curve.cell_name for curve in sample.jv.jv_curve] == ['c1-fwd', 'c1-rev']


def test_missing_efficiency_leaves_the_defaults_unset(sample):
    """A device without JV results is normal and must normalize without error."""
    measurement = make_jv_measurement(make_curve('no-results'))

    sample._populate_from_jv([measurement])

    assert sample.jv.default_PCE is None
    assert sample.jv.default_Voc is None


def test_mppt_efficiency_track_yields_the_stabilised_value(sample):
    """MPPTracking.efficiency is an array over time, not a scalar."""
    tracking = MPPTracking()
    tracking.efficiency = np.array([15.0, 16.2, 16.9])

    sample._populate_from_mppt(tracking)

    assert sample.jv.default_PCE == pytest.approx(16.9)


def test_mppt_does_not_override_a_jv_derived_efficiency(sample):
    measurement = make_jv_measurement(
        make_curve('c1-rev', efficiency=18.5, voc=1.12, jsc=21.5, fill_factor=0.77),
    )
    tracking = MPPTracking()
    tracking.efficiency = np.array([15.0, 16.2, 16.9])

    sample._populate_from_jv([measurement])
    sample._populate_from_mppt(tracking)

    assert sample.jv.default_PCE == pytest.approx(18.5)


def test_mppt_does_not_override_a_measured_zero_efficiency(sample):
    """A dead cell measured at 0 % is a result, not a missing value."""
    sample.jv.default_PCE = 0.0
    tracking = MPPTracking()
    tracking.efficiency = np.array([15.0, 16.2, 16.9])

    sample._populate_from_mppt(tracking)

    assert sample.jv.default_PCE == pytest.approx(0.0)


def test_cell_stack_figure_renders_without_jv_results():
    """Regression: missing device parameters used to raise a TypeError."""
    figure = create_cell_stack_figure(
        layers=['Glass', 'Perovskite', 'Au'],
        thicknesses=[1.0, 0.5, 0.1],
        colors=['lightblue', 'red', 'orange'],
        efficiency=None,
        voc=None,
        jsc=None,
        ff=None,
    )

    annotation = figure.layout.annotations[0].text
    assert 'Efficiency = N/A' in annotation
    assert 'FF = N/A' in annotation
