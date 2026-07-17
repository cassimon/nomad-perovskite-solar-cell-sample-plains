"""The overview figures: every measurement of one kind, on one sample, in one plot.

A device is measured many times -- several JV scans, an MPP track, an EQE spectrum --
and each measurement lands in an entry of its own, plotting only itself. These
figures combine them, so the sample entry shows everything that was measured on it.
"""

import numpy as np
import pytest
from baseclasses.solar_energy import SolarCellEQECustom
from baseclasses.solar_energy.eqemeasurement import EQEMeasurement
from baseclasses.solar_energy.jvmeasurement import JVMeasurement, SolarCellJVCurveCustom
from baseclasses.solar_energy.mpp_tracking import MPPTracking
from nomad.units import ureg

from baseclasses.solar_energy.uvvismeasurement import UVvisData, UVvisMeasurement

from nomad_perovskite_solar_cell_sample_plains.utils import (
    create_dark_jv_overview_figure,
    create_eqe_overview_figure,
    create_jv_overview_figure,
    create_stability_overview_figure,
    create_uvvis_overview_figure,
)


def curve(name, *, efficiency=3.67, dark=False):
    curve = SolarCellJVCurveCustom()
    curve.cell_name = name
    curve.dark = dark
    curve.efficiency = efficiency
    curve.open_circuit_voltage = 0.54 * ureg('V')
    curve.short_circuit_current_density = 20.8 * ureg('mA/cm**2')
    curve.fill_factor = 0.3261
    curve.voltage = np.linspace(0, 1.2, 5) * ureg('V')
    curve.current_density = np.linspace(-22, 0, 5) * ureg('mA/cm**2')
    return curve


def jv_measurement(name, *curves):
    measurement = JVMeasurement()
    measurement.name = name
    measurement.jv_curve = list(curves)
    return measurement


# ── JV ────────────────────────────────────────────────────────────────────────


def test_every_scan_of_every_jv_measurement_is_drawn():
    figure = create_jv_overview_figure(
        [
            jv_measurement('run 1', curve('FW'), curve('RV')),
            jv_measurement('run 2', curve('FW'), curve('RV')),
        ]
    )

    assert len(figure.data) == 4
    # Grouped by the measurement they came from, so the legend stays readable.
    assert [trace.legendgroup for trace in figure.data] == [
        'run 1',
        'run 1',
        'run 2',
        'run 2',
    ]
    assert [trace.name for trace in figure.data] == ['FW', 'RV', 'FW', 'RV']


def test_a_curve_carries_its_own_performance_into_the_hover():
    figure = create_jv_overview_figure([jv_measurement('run 1', curve('RV'))])

    hover = figure.data[0].hovertemplate
    assert 'run 1 · RV' in hover
    assert 'PCE = 3.67 %' in hover
    # The fill factor is stored as a fraction and read as a percentage.
    assert 'FF = 32.6 %' in hover


def test_the_statistics_are_written_onto_the_plot():
    class _Statistics:
        number_of_jv_scans = 4
        pce_best = 3.67
        pce_worst = 2.12
        pce_average = 2.9
        voc_best = 0.54 * ureg('V')
        voc_worst = 0.53 * ureg('V')
        voc_average = 0.535 * ureg('V')
        jsc_best = 20.8 * ureg('mA/cm**2')
        jsc_worst = 15.7 * ureg('mA/cm**2')
        jsc_average = 18.25 * ureg('mA/cm**2')
        ff_best = 0.3261
        ff_worst = 0.2538
        ff_average = 0.29

    figure = create_jv_overview_figure(
        [jv_measurement('run 1', curve('RV'))], _Statistics()
    )

    text = figure.layout.annotations[0].text
    assert 'over 4 scans' in text
    assert 'PCE (%): 3.67 / 2.90 / 2.12' in text
    assert 'FF (%): 32.6 / 29.0 / 25.4' in text


def test_nothing_to_draw_means_no_figure():
    """An empty plot is worse than no plot: the entry should not offer it at all."""
    assert create_jv_overview_figure([]) is None
    assert create_jv_overview_figure([jv_measurement('run 1')]) is None


def test_dark_sweeps_are_kept_out_of_the_light_overview():
    """A dark curve must never be drawn on the illuminated JV overview."""
    figure = create_jv_overview_figure(
        [jv_measurement('run 1', curve('RV'), curve('Dark RV', dark=True))]
    )

    assert len(figure.data) == 1
    assert figure.data[0].name == 'RV'
    assert 'dark scan' not in figure.data[0].hovertemplate
    assert 'light measurements' in figure.layout.title.text


def test_dark_overview_draws_only_the_dark_sweeps():
    """The dark overview holds the dark curves and nothing else."""
    figure = create_dark_jv_overview_figure(
        [
            jv_measurement('run 1', curve('FW'), curve('Dark FW', dark=True)),
            jv_measurement('run 2', curve('Dark RV', dark=True)),
        ]
    )

    assert [trace.name for trace in figure.data] == ['Dark FW', 'Dark RV']
    assert all('dark scan' in trace.hovertemplate for trace in figure.data)
    assert 'Dark JV' in figure.layout.title.text


def test_dark_and_light_overviews_are_each_none_without_their_kind():
    """Neither figure is offered when the sample has no curve of its kind."""
    only_light = [jv_measurement('run 1', curve('RV'))]
    only_dark = [jv_measurement('run 1', curve('Dark RV', dark=True))]

    assert create_dark_jv_overview_figure(only_light) is None
    assert create_jv_overview_figure(only_dark) is None


# ── Stability ─────────────────────────────────────────────────────────────────


def track(name, points=5):
    measurement = MPPTracking()
    measurement.name = name
    measurement.time = np.linspace(0, 3600, points) * ureg('s')
    measurement.efficiency = np.linspace(10.0, 9.0, points)
    return measurement


class _JVParameters:
    """The JV curves the CHOSE stability run samples along the track."""

    time = np.array([0.0, 0.5, 1.0]) * ureg('hour')
    efficiency_fw = np.array([9.9, 9.5, 9.1])
    efficiency_rv = np.array([10.0, 9.6, 9.2])


def test_every_track_is_drawn_on_one_time_axis():
    figure = create_stability_overview_figure([track('run 1'), track('run 2')])

    assert len(figure.data) == 2
    assert figure.layout.xaxis.title.text == 'Time (h)'
    # Seconds on the measurement, hours on the plot.
    assert figure.data[0].x[-1] == pytest.approx(1.0)


def test_the_jv_parameters_sampled_along_the_track_are_drawn_too():
    """The track of a short run is a single point; its JV series is the whole story."""
    measurement = track('run 1', points=1)
    measurement.jv_parameters = _JVParameters()

    figure = create_stability_overview_figure([measurement])

    modes = {trace.name: trace.mode for trace in figure.data}
    assert modes['JV forward'] == 'markers'
    assert modes['JV reverse'] == 'markers'
    reverse = next(trace for trace in figure.data if trace.name == 'JV reverse')
    assert list(reverse.y) == pytest.approx([10.0, 9.6, 9.2])


def test_a_track_with_nothing_in_it_yields_no_figure():
    assert create_stability_overview_figure([MPPTracking()]) is None


# ── EQE ───────────────────────────────────────────────────────────────────────


def eqe_measurement(name, *, spectra=1):
    measurement = EQEMeasurement()
    measurement.name = name
    measurement.eqe_data = []
    for _ in range(spectra):
        spectrum = SolarCellEQECustom(
            photon_energy_array=np.linspace(1.3, 3.0, 40),
            raw_photon_energy_array=np.linspace(1.3, 3.0, 40),
            eqe_array=np.linspace(0.05, 0.85, 40),
            raw_eqe_array=np.linspace(0.05, 0.85, 40),
        )
        spectrum.bandgap_eqe = 1.698 * ureg('eV')
        measurement.eqe_data.append(spectrum)
    return measurement


def test_every_spectrum_is_drawn_in_percent_over_wavelength():
    figure = create_eqe_overview_figure([eqe_measurement('run 1')])

    assert len(figure.data) == 1
    assert figure.layout.xaxis.title.text == 'Wavelength (nm)'
    # Stored as a fraction (0.05 … 0.85), plotted as a percentage.
    assert max(figure.data[0].y) == pytest.approx(85.0)
    # No wavelength array was set, so it came from the photon energy: 1.3 eV ≈ 954 nm.
    assert max(figure.data[0].x) == pytest.approx(953.7, abs=0.5)
    assert 'band gap = 1.698 eV' in figure.data[0].hovertemplate


def test_several_spectra_of_one_measurement_stay_apart():
    figure = create_eqe_overview_figure([eqe_measurement('run 1', spectra=2)])

    assert [trace.name for trace in figure.data] == ['run 1 #1', 'run 1 #2']


def test_no_spectrum_means_no_figure():
    assert create_eqe_overview_figure([EQEMeasurement()]) is None


# ── UV-Vis ────────────────────────────────────────────────────────────────────


def uvvis_measurement(name, *, spectra=1):
    measurement = UVvisMeasurement()
    measurement.name = name
    measurement.measurements = []
    for _ in range(spectra):
        measurement.measurements.append(
            UVvisData(
                wavelength=np.linspace(300, 1100, 40) * ureg('nm'),
                intensity=np.linspace(0.1, 85.0, 40),
            )
        )
    return measurement


def test_every_transmittance_spectrum_is_drawn_over_wavelength():
    figure = create_uvvis_overview_figure([uvvis_measurement('film 100 uL')])

    assert len(figure.data) == 1
    assert figure.layout.xaxis.title.text == 'Wavelength (nm)'
    assert figure.layout.yaxis.title.text == 'Transmittance (%)'
    assert figure.data[0].name == 'film 100 uL'
    assert max(figure.data[0].x) == pytest.approx(1100.0)
    assert max(figure.data[0].y) == pytest.approx(85.0)


def test_several_films_stay_apart():
    figure = create_uvvis_overview_figure(
        [uvvis_measurement('film A'), uvvis_measurement('film B')]
    )

    assert [trace.name for trace in figure.data] == ['film A', 'film B']


def test_no_transmittance_means_no_figure():
    assert create_uvvis_overview_figure([UVvisMeasurement()]) is None
