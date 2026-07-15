"""The sample's jv / eqe / stability sections, derived from linked measurements.

These cover what `_populate_from_*` writes once nomad-chose actually fills the
measurement entries (`jv_curve`, `eqe_data`, and MPPTracking's native `time` /
`efficiency`). Before that, `jv_curve` was empty and every one of these sections
stayed unset.
"""

import logging

import numpy as np
import pytest
from baseclasses.solar_energy import SolarCellEQECustom
from baseclasses.solar_energy.eqemeasurement import EQEMeasurement
from baseclasses.solar_energy.jvmeasurement import JVMeasurement, SolarCellJVCurveCustom
from baseclasses.solar_energy.mpp_tracking import MPPTracking, StabilityFiguresOfMerit
from nomad.datamodel import EntryArchive, EntryMetadata, User
from nomad.datamodel.metainfo.basesections import CompositeSystemReference
from nomad.datamodel.metainfo.plot import PlotlyFigure
from nomad.units import ureg
from nomad.utils import generate_entry_id
from perovskite_solar_cell_database.schema_sections.cell import Cell
from perovskite_solar_cell_database.schema_sections.jv import JV

from baseclasses.solar_energy.uvvismeasurement import UVvisData, UVvisMeasurement

from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import (
    EQE_OVERVIEW_LABEL,
    JV_OVERVIEW_LABEL,
    STABILITY_OVERVIEW_LABEL,
    STACK_FIGURE_LABEL,
    UVVIS_OVERVIEW_LABEL,
    PerovskiteSolarCellSampleArea,
    SubstrateSample,
)

LOGGER = logging.getLogger('test')


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


# ── Solar Cell Properties ─────────────────────────────────────────────────────


def archive_for(section):
    archive = EntryArchive(metadata=EntryMetadata(entry_id='e', upload_id='u'))
    archive.data = section
    return archive


class _LoadingContext:
    """An m_context that hands back the JV measurement the search "found"."""

    def __init__(self):
        self.loaded = []

    def load_archive(self, entry_id, upload_id, _):
        self.loaded.append((entry_id, upload_id))
        return type('A', (), {'data': chose_measurement()})()


def _one_hit():
    """A search response: `MetadataResponse.data` is a list of plain dicts."""
    return type('R', (), {'data': [{'entry_id': 'e1', 'upload_id': 'u1'}]})()


def _stub_figure():
    return type('F', (), {'to_plotly_json': lambda self: {'data': [], 'layout': {}}})()


def test_the_solar_cell_properties_panel_is_populated(sample):
    """The panel the user saw as "unavailable".

    It is filled by `JV.normalize`, which copies default_PCE/Voc/Jsc/FF and
    light_intensity into results. NOMAD's MetainfoNormalizer walks the archive
    post-order, so it had already run `JV.normalize` -- against an empty `jv` --
    *before* the sample's own normalize got the chance to fill it from the linked
    measurements. Hence the explicit re-normalize.
    """
    archive = archive_for(sample)
    sample._populate_from_jv([chose_measurement()])
    sample.jv.light_intensity = 100.0 * ureg('mW/cm**2')

    sample._normalize_populated_sections(archive, LOGGER)

    solar_cell = archive.results.properties.optoelectronic.solar_cell
    assert solar_cell.efficiency == pytest.approx(3.67)
    assert solar_cell.open_circuit_voltage.to('V').magnitude == pytest.approx(0.539999)
    assert solar_cell.fill_factor == pytest.approx(0.3261)
    assert solar_cell.illumination_intensity.to('mW/cm**2').magnitude == pytest.approx(
        100.0
    )


def test_the_stack_figure_is_drawn_from_the_populated_jv(sample, monkeypatch):
    """The figure was built *before* the JV was populated, so every performance
    value it annotates rendered as N/A."""
    captured = {}

    def fake_figure(**kwargs):
        captured.update(kwargs)
        return _stub_figure()

    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.'
        'create_cell_stack_figure',
        fake_figure,
    )
    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.search',
        lambda **kwargs: _one_hit(),
    )

    sample.cell = Cell(stack_sequence='SLG | ITO | SnO2 | Perovskite | Spiro | Au')
    archive = archive_for(sample)
    archive.metadata.main_author = User(user_id='user-1')
    archive.m_context = _LoadingContext()

    sample.normalize(archive, LOGGER)

    # The figure saw the measured performance, not None.
    assert captured['efficiency'] == pytest.approx(3.67)
    assert captured['voc'].to('V').magnitude == pytest.approx(0.539999)
    assert sample.figures


def test_eqe_uses_the_databases_capital_j_spelling(sample):
    """`integrated_Jsc` / `integrated_J0rad` on the target section; the source
    spells them lower-case. Copying under the source's name meant the guard in
    _populate_from_eqe dropped both."""
    data = SolarCellEQECustom(
        photon_energy_array=np.linspace(1.3, 3.0, 40),
        raw_photon_energy_array=np.linspace(1.3, 3.0, 40),
        eqe_array=np.linspace(0.05, 0.85, 40),
        raw_eqe_array=np.linspace(0.05, 0.85, 40),
    )
    data.bandgap_eqe = 1.72 * ureg('eV')
    data.integrated_jsc = 21.0 * ureg('A/m**2')

    measurement = EQEMeasurement()
    measurement.eqe_data = [data]

    sample._populate_from_eqe(measurement)

    assert sample.eqe.integrated_Jsc is not None
    assert sample.eqe.integrated_Jsc.to('A/m**2').magnitude == pytest.approx(21.0)


# ── Performance statistics and the overview figures ───────────────────────────


def test_the_statistics_span_every_scan_of_every_measurement(sample):
    """`jv` describes the single best curve, which says nothing about spread. These
    are per KPI over all scans -- the best FF and the best PCE need not be the same
    scan."""
    sample._populate_performance_statistics([chose_measurement(), chose_measurement()])
    statistics = sample.performance_statistics

    assert statistics.number_of_jv_scans == 4  # two measurements, FW + RV each
    assert statistics.pce_best == pytest.approx(3.67)
    assert statistics.pce_worst == pytest.approx(2.12)
    assert statistics.pce_average == pytest.approx((3.67 + 2.12) / 2)
    assert statistics.voc_best.to('V').magnitude == pytest.approx(0.539999)
    assert statistics.jsc_worst.to('mA/cm**2').magnitude == pytest.approx(15.754854)
    assert statistics.ff_average == pytest.approx((0.3261 + 0.2538) / 2)


def test_a_dark_scan_is_not_a_performance(sample):
    measurement = JVMeasurement()
    lit = scan('RV', efficiency=3.67, voc=0.54, jsc=20.8, ff=0.33)
    dark = scan('RV dark', efficiency=0.01, voc=0.0, jsc=0.0, ff=0.0)
    dark.dark = True
    measurement.jv_curve = [lit, dark]

    sample._populate_performance_statistics([measurement])

    assert sample.performance_statistics.number_of_jv_scans == 1
    assert sample.performance_statistics.pce_worst == pytest.approx(3.67)


def test_no_scans_means_no_statistics_section(sample):
    sample.performance_statistics = None
    sample._populate_performance_statistics([JVMeasurement()])
    assert sample.performance_statistics is None


class _AllKindsContext:
    """An m_context handing back one measurement of each kind."""

    def __init__(self):
        eqe = EQEMeasurement()
        eqe.name = 'eqe run'
        eqe.eqe_data = [
            SolarCellEQECustom(
                photon_energy_array=np.linspace(1.3, 3.0, 40),
                raw_photon_energy_array=np.linspace(1.3, 3.0, 40),
                eqe_array=np.linspace(0.05, 0.85, 40),
                raw_eqe_array=np.linspace(0.05, 0.85, 40),
            )
        ]

        mppt = MPPTracking()
        mppt.name = 'mpp run'
        mppt.time = np.linspace(0, 3600, 5) * ureg('s')
        mppt.efficiency = np.linspace(10.0, 9.0, 5)

        self.entries = {
            'jv': chose_measurement(),
            'eqe': eqe,
            'mppt': mppt,
        }

    def load_archive(self, entry_id, upload_id, _):
        return type('A', (), {'data': self.entries[entry_id]})()


def _hits(*entry_ids):
    return type(
        'R',
        (),
        {'data': [{'entry_id': entry_id, 'upload_id': 'u'} for entry_id in entry_ids]},
    )()


def test_the_sample_plots_every_measurement_made_on_it(sample, monkeypatch):
    """One figure per measurement kind, each holding all measurements of that kind."""
    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.search',
        lambda **kwargs: _hits('jv', 'eqe', 'mppt'),
    )

    sample.cell = Cell(stack_sequence='SLG | ITO | SnO2 | Perovskite | Spiro | Au')
    archive = archive_for(sample)
    archive.metadata.main_author = User(user_id='user-1')
    archive.m_context = _AllKindsContext()

    sample.normalize(archive, LOGGER)

    assert [figure.label for figure in sample.figures] == [
        STACK_FIGURE_LABEL,
        JV_OVERVIEW_LABEL,
        STABILITY_OVERVIEW_LABEL,
        EQE_OVERVIEW_LABEL,
    ]
    # The JV overview holds both scans of the measurement, and the statistics.
    jv_figure = sample.figures[1].figure
    assert len(jv_figure['data']) == 2
    assert 'PCE (%): 3.67' in jv_figure['layout']['annotations'][0]['text']


def test_a_kind_that_was_never_measured_gets_no_figure(sample, monkeypatch):
    """An empty plot is worse than no plot."""
    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.search',
        lambda **kwargs: _hits('jv'),
    )

    archive = archive_for(sample)
    archive.metadata.main_author = User(user_id='user-1')
    archive.m_context = _AllKindsContext()

    sample.normalize(archive, LOGGER)

    # No stack sequence either, so the JV overview is the only figure.
    assert [figure.label for figure in sample.figures] == [JV_OVERVIEW_LABEL]


# ── Searching for the linked measurements ─────────────────────────────────────


def test_the_search_can_actually_match_an_unpublished_upload(sample, monkeypatch):
    """`owner='visible'` with no user_id means *published* entries only -- and a
    fresh upload is never published, so this search returned nothing, always."""
    calls = {}

    class _Results:
        data = []

    def fake_search(**kwargs):
        calls.update(kwargs)
        return _Results()

    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.search',
        fake_search,
    )

    archive = archive_for(sample)
    archive.metadata.main_author = User(user_id='user-1')
    archive.m_context = object()

    sample._populate_jv_from_measurements(archive, LOGGER)

    assert calls['owner'] == 'all'
    assert calls['user_id'] == 'user-1'


def test_a_search_hit_is_read_as_the_dict_it_is(sample, monkeypatch):
    """MetadataResponse.data is a list of dicts. Reading `hit.entry_id` raised an
    AttributeError that the per-hit `except` swallowed, so even a hit that *was*
    found never got loaded."""
    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.search',
        lambda **kwargs: _one_hit(),
    )

    archive = archive_for(sample)
    archive.metadata.main_author = User(user_id='user-1')
    archive.m_context = _LoadingContext()

    sample._populate_jv_from_measurements(archive, LOGGER)

    assert archive.m_context.loaded == [('e1', 'u1')]
    # …and the measurement it loaded was actually used.
    assert sample.jv.default_PCE == pytest.approx(3.67)


# ── The substrate is not a solar cell ─────────────────────────────────────────


def test_the_substrate_shows_the_figures_of_every_device_on_it(monkeypatch):
    """The substrate is a contact sheet of its pixels: it repeats each device's
    overview plots, labelled with the device they came from -- not aggregated."""
    loaded = []

    class _Context:
        def load_archive(self, entry_id, upload_id, _):
            loaded.append((entry_id, upload_id))
            device = PerovskiteSolarCellSampleArea(name=f'device {len(loaded)}')
            device.figures = [
                PlotlyFigure(label=STACK_FIGURE_LABEL, figure={'data': [], 'layout': {}}),
                PlotlyFigure(
                    label=JV_OVERVIEW_LABEL,
                    figure={'data': [{'x': [0.0], 'y': [0.0]}], 'layout': {}},
                ),
            ]
            return type('A', (), {'data': device})()

    substrate = SubstrateSample()
    substrate.cell_areas = [
        CompositeSystemReference(
            reference=f'../upload/raw/AI03_dev{index}_sample.archive.yaml#/data'
        )
        for index in (1, 2)
    ]
    archive = archive_for(substrate)
    archive.m_context = _Context()

    substrate.normalize(archive, LOGGER)

    # The device archives were loaded by their (deterministic) entry ids.
    assert loaded == [
        (generate_entry_id('u', f'AI03_dev{index}_sample.archive.yaml'), 'u')
        for index in (1, 2)
    ]
    # …and each device's overview plot is on the substrate, under its own name.
    assert [figure.label for figure in substrate.figures] == [
        f'device 1: {JV_OVERVIEW_LABEL}',
        f'device 2: {JV_OVERVIEW_LABEL}',
    ]


def test_the_substrate_does_not_repeat_the_stack_of_every_pixel():
    """Fabrication, not measurement -- and identical for all four pixels."""

    class _Context:
        def load_archive(self, entry_id, upload_id, _):
            device = PerovskiteSolarCellSampleArea(name='device 1')
            device.figures = [
                PlotlyFigure(label=STACK_FIGURE_LABEL, figure={'data': [], 'layout': {}})
            ]
            return type('A', (), {'data': device})()

    substrate = SubstrateSample()
    substrate.cell_areas = [
        CompositeSystemReference(
            reference='../upload/raw/AI03_dev1_sample.archive.yaml#/data'
        )
    ]
    archive = archive_for(substrate)
    archive.m_context = _Context()

    substrate.normalize(archive, LOGGER)

    assert not substrate.figures


def test_a_reference_stated_as_an_archive_url_is_followed_too():
    """The app writes raw-file references, but a hand-written archive URL already
    carries the entry id and must not be hashed a second time."""
    loaded = []

    class _Context:
        def load_archive(self, entry_id, upload_id, _):
            loaded.append(entry_id)
            device = PerovskiteSolarCellSampleArea(name='device 1')
            device.figures = [
                PlotlyFigure(label=JV_OVERVIEW_LABEL, figure={'data': [], 'layout': {}})
            ]
            return type('A', (), {'data': device})()

    substrate = SubstrateSample()
    substrate.cell_areas = [
        CompositeSystemReference(reference='../uploads/u/archive/abc123#/data')
    ]
    archive = archive_for(substrate)
    archive.m_context = _Context()

    substrate.normalize(archive, LOGGER)

    assert loaded == ['abc123']
    assert substrate.figures


def test_one_unreadable_device_does_not_cost_the_substrate_the_others():
    class _Context:
        def load_archive(self, entry_id, upload_id, _):
            if 'dev1' in entry_id or not loaded:
                loaded.append(entry_id)
                raise RuntimeError('archive not found')
            device = PerovskiteSolarCellSampleArea(name='device 2')
            device.figures = [
                PlotlyFigure(label=JV_OVERVIEW_LABEL, figure={'data': [], 'layout': {}})
            ]
            return type('A', (), {'data': device})()

    loaded = []
    substrate = SubstrateSample()
    substrate.cell_areas = [
        CompositeSystemReference(
            reference=f'../upload/raw/AI03_dev{index}_sample.archive.yaml#/data'
        )
        for index in (1, 2)
    ]
    archive = archive_for(substrate)
    archive.m_context = _Context()

    substrate.normalize(archive, LOGGER)

    assert [figure.label for figure in substrate.figures] == [
        f'device 2: {JV_OVERVIEW_LABEL}'
    ]


def test_a_substrate_does_not_grow_a_solar_cell_section():
    """`Substrate.normalize` calls `add_solar_cell(archive)` unconditionally, which
    gave every bare substrate entry a "Solar Cell Properties" panel -- and made it
    match the solar-cell filters of the overview plots."""
    substrate = SubstrateSample()
    substrate.substrate = substrate.m_def.all_properties['substrate'].sub_section.section_cls(
        stack_sequence='SLG | ITO'
    )
    archive = archive_for(substrate)

    substrate.normalize(archive, LOGGER)

    assert (
        archive.results is None
        or archive.results.properties is None
        or archive.results.properties.optoelectronic is None
    )


# ── The substrate carries the film-level UV-Vis overview ──────────────────────


def _uvvis_entry(name):
    measurement = UVvisMeasurement()
    measurement.name = name
    measurement.measurements = [
        UVvisData(
            wavelength=np.linspace(300, 1100, 40) * ureg('nm'),
            intensity=np.linspace(0.1, 85.0, 40),
        )
    ]
    return measurement


def test_the_substrate_shows_its_own_uvvis_overview(monkeypatch):
    """UV-Vis is film-level: it describes the whole substrate, not a pixel, so the
    substrate searches for it directly and draws one combined transmittance plot."""
    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.search',
        lambda **kwargs: _hits('uvvis-100', 'uvvis-150'),
    )

    class _Context:
        def load_archive(self, entry_id, upload_id, _):
            return type('A', (), {'data': _uvvis_entry(entry_id)})()

    substrate = SubstrateSample()
    archive = archive_for(substrate)
    archive.metadata.main_author = User(user_id='user-1')
    archive.m_context = _Context()

    substrate.normalize(archive, LOGGER)

    assert [figure.label for figure in substrate.figures] == [UVVIS_OVERVIEW_LABEL]
    # Both films are in the one plot.
    assert len(substrate.figures[0].figure['data']) == 2


def test_a_substrate_without_uvvis_gets_no_uvvis_figure(monkeypatch):
    monkeypatch.setattr(
        'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.search',
        lambda **kwargs: _hits(),
    )

    substrate = SubstrateSample()
    archive = archive_for(substrate)
    archive.metadata.main_author = User(user_id='user-1')
    archive.m_context = type('C', (), {'load_archive': lambda *a: None})()

    substrate.normalize(archive, LOGGER)

    assert not substrate.figures
