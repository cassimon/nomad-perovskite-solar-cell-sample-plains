from types import SimpleNamespace

from nomad.metainfo import Section

from unittest.mock import MagicMock, patch
from nomad.metainfo import Section

from nomad_perovskite_solar_cell_sample_plains.schema_packages.schema_package import (
    PerovskiteSolarCellSample,
    PVKMeasurementBase,
    PerformedMeasurements,
)

from nomad_perovskite_solar_cell_sample_plains.schema_packages.schema_package import SolarCellJV
from baseclasses.solar_energy.eqemeasurement import SolarCellEQE
from baseclasses.solar_energy.eqemeasurement import SolarCellEQE
from baseclasses.solar_energy.mpp_tracking  import MPPTracking

#To be replaced with actual imports when the chose plugin is available
class JVMeasurement(PVKMeasurementBase):
    m_def = Section(label='JVMeasurement')
    def _build_result(self, logger): return SolarCellJV()

class EQEMeasurement(PVKMeasurementBase):
    m_def = Section(label='EQEMeasurement')
    def _build_result(self, logger): return SolarCellEQE()

class MPPMeasurement(PVKMeasurementBase):
    m_def = Section(label='MPPMeasurement')
    def _build_result(self, logger): return MPPTracking()


def test_perovskite_sample_m_def_label():
    assert PerovskiteSolarCellSample.m_def.label == "Perovskite Solar Cell Sample"


class DummyLogger:
    def __init__(self):
        self.messages = []
    def warning(self, msg, **kwargs):
        self.messages.append(('warning', msg))
    def info(self, msg, **kwargs):
        self.messages.append(('info', msg))
    def error(self, msg, **kwargs):
        self.messages.append(('error', msg))


# ── Shared patch helper ───────────────────────────────────────────────────────
# Patches the first base of PVKMeasurementBase (EntryData) so NOMAD
# internals don't run. All tests use this.

def _patched_normalize(meas, archive, logger):
    with patch.object(PVKMeasurementBase.__bases__[0], 'normalize', return_value=None):
        meas.normalize(archive, logger)

def _make_archive(sample=None):
    """Minimal archive stub. Optionally pre-loads a sample as the context."""
    archive = MagicMock()
    archive.metadata = MagicMock()
    archive.results  = MagicMock()
    archive.m_context = None
    return archive


# ── Test 1: no pvk_sample → warning, no crash ────────────────────────────────

class ConcreteMeasurement(PVKMeasurementBase):
    m_def = Section(label='ConcreteMeasurement')

    def _build_result(self, logger):
        # Returns a registered type so dispatch would succeed if sample existed
        return SolarCellJV()


def test_no_pvk_sample_logs_warning():
    logger = DummyLogger()
    meas = ConcreteMeasurement()
    meas.pvk_sample = None

    _patched_normalize(meas, None, logger)

    assert any(
        'no pvk_sample' in m[1]
        for m in logger.messages if m[0] == 'warning'
    )


# ── Test 2: pvk_sample set → PerformedMeasurements created and result registered

def test_performed_measurements_created_and_registered():
    logger = DummyLogger()
    sample = PerovskiteSolarCellSample()
    meas = ConcreteMeasurement()
    meas.pvk_sample = sample

    _patched_normalize(meas, None, logger)

    assert isinstance(sample.performed_measurements, PerformedMeasurements)
    # ConcreteMeasurement returns SolarCellJV → lands in .jv[]
    assert len(sample.performed_measurements.jv) == 1
    assert isinstance(sample.performed_measurements.jv[0], SolarCellJV)


# ── Test 3: None returned from _build_result → nothing registered, no crash ──

class NullMeasurement(PVKMeasurementBase):
    m_def = Section(label='NullMeasurement')
    # _build_result not overridden → returns None by default


def test_none_result_skips_registration():
    logger = DummyLogger()
    sample = PerovskiteSolarCellSample()
    meas = NullMeasurement()
    meas.pvk_sample = sample

    _patched_normalize(meas, None, logger)

    # PerformedMeasurements is still created but all lists are empty
    assert isinstance(sample.performed_measurements, PerformedMeasurements)
    assert len(sample.performed_measurements.jv) == 0
    assert len(sample.performed_measurements.eqe) == 0


# ── Test 4: unregistered type → warning from register(), no crash ─────────────

class UnregisteredSection(MagicMock):
    pass


class UnregisteredMeasurement(PVKMeasurementBase):
    m_def = Section(label='UnregisteredMeasurement')

    def _build_result(self, logger):
        return UnregisteredSection()


def test_unregistered_type_logs_warning():
    logger = DummyLogger()
    sample = PerovskiteSolarCellSample()
    meas = UnregisteredMeasurement()
    meas.pvk_sample = sample

    _patched_normalize(meas, None, logger)

    assert any(
        'unregistered type' in m[1]
        for m in logger.messages if m[0] == 'warning'
    )


# ── Test 5: each type routes to the correct list ─────────────────────────────

class ConcreteJV(PVKMeasurementBase):
    m_def = Section(label='ConcreteJV')
    def _build_result(self, logger): return SolarCellJV()


class ConcreteEQE(PVKMeasurementBase):
    m_def = Section(label='ConcreteEQE')
    def _build_result(self, logger): return SolarCellEQE()


class ConcreteStability(PVKMeasurementBase):
    m_def = Section(label='ConcreteStability')
    def _build_result(self, logger): return MPPTracking()


def test_dispatch_routes_to_correct_lists():
    logger = DummyLogger()
    sample = PerovskiteSolarCellSample()

    for cls in (ConcreteJV, ConcreteEQE, ConcreteStability):
        meas = cls()
        meas.pvk_sample = sample
        _patched_normalize(meas, None, logger)

    performed = sample.performed_measurements
    assert performed is not None
    assert len(performed.jv) == 1
    assert len(performed.eqe) == 1
    assert len(performed.stability) == 1
    assert isinstance(performed.jv[0], SolarCellJV)
    assert isinstance(performed.eqe[0], SolarCellEQE)
    assert isinstance(performed.stability[0], MPPTracking)


# ── Test 6: multiple measurements of same type accumulate ────────────────────

def test_multiple_jv_measurements_accumulate():
    logger = DummyLogger()
    sample = PerovskiteSolarCellSample()

    for _ in range(3):
        meas = ConcreteJV()
        meas.pvk_sample = sample
        _patched_normalize(meas, None, logger)

    assert len(sample.performed_measurements.jv) == 3


def test_five_yaml_upload_scenario():
    """
    Simulates uploading:
      File 1 — PerovskiteSolarCellSample  (lab_id = PVK-TEST-001)
      File 2 — LabJVMeasurement           (pvk_sample_id = PVK-TEST-001)
      File 3 — LabJVMeasurement           (pvk_sample_id = PVK-TEST-001)
      File 4 — LabEQEMeasurement          (pvk_sample_id = PVK-TEST-001)
      File 5 — LabJVMeasurement           (pvk_sample direct reference, Mode A)

    The sample is parsed first and its Python object is reused as the
    resolved reference — this is what NOMAD's context does in production.
    We mock _resolve_sample to inject the sample object directly,
    isolating the registration logic from the NOMAD search infrastructure.
    """
    logger = DummyLogger()

    # ── File 1: sample parsed first ─────────────────────────────────────────
    sample = PerovskiteSolarCellSample()
    sample.lab_id = 'PVK-TEST-001'
    sample.name   = 'Test perovskite cell'

    # ── Files 2–4: pvk_sample_id mode (Mode B) ──────────────────────────────
    # _resolve_sample would normally do a NOMAD search; we patch it to
    # directly inject the sample object, as the context would after
    # File 1 has been processed.

    def inject_sample(meas):
        """Simulate _resolve_sample finding the sample by lab_id."""
        def _resolve(archive, logger):
            if meas.pvk_sample is None and meas.pvk_sample_id == 'PVK-TEST-001':
                meas.pvk_sample = sample
        return _resolve

    measurements_mode_b = [
        JVMeasurement(),   # file 2
        JVMeasurement(),   # file 3
        EQEMeasurement(),  # file 4
    ]
    for m in measurements_mode_b:
        m.pvk_sample_id = 'PVK-TEST-001'

    for meas in measurements_mode_b:
        with patch.object(meas, '_resolve_sample', side_effect=inject_sample(meas)):
            _patched_normalize(meas, _make_archive(), logger)

    # ── File 5: direct entry_id reference (Mode A) ──────────────────────────
    jv_mode_a = JVMeasurement()
    jv_mode_a.pvk_sample = sample   # reference pre-set, _resolve_sample is no-op

    _patched_normalize(jv_mode_a, _make_archive(), logger)

    # ── Assertions ───────────────────────────────────────────────────────────
    performed = sample.performed_measurements
    assert performed is not None, 'performed_measurements was never created'

    # 3 JV measurements (files 2, 3, 5) + 1 EQE (file 4)
    assert len(performed.jv) == 3, (
        f'Expected 3 JV entries, got {len(performed.jv)}'
    )
    assert len(performed.eqe) == 1, (
        f'Expected 1 EQE entry, got {len(performed.eqe)}'
    )
    assert all(isinstance(j, SolarCellJV)  for j in performed.jv)
    assert all(isinstance(e, SolarCellEQE) for e in performed.eqe)

    # No warnings about missing pvk_sample
    missing_warnings = [
        m for m in logger.messages
        if m[0] == 'warning' and 'no pvk_sample' in m[1]
    ]
    assert missing_warnings == [], f'Unexpected warnings: {missing_warnings}'


# ─────────────────────────────────────────────────────────────────────────────
# Test: _resolve_sample falls back gracefully when lab_id not found
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_sample_unknown_id_logs_warning():
    logger = DummyLogger()
    meas = JVMeasurement()
    meas.pvk_sample_id = 'DOES-NOT-EXIST'

    # archive has a context but search returns nothing
    archive = _make_archive()
    archive.m_context = MagicMock()

    with patch('nomad_perovskite_solar_cell_sample_plains.schema_packages.schema_package.search') as mock_search:
        mock_search.return_value = MagicMock(
            pagination=MagicMock(total=0), data=[]
        )
        _patched_normalize(meas, archive, logger)

    assert any(
        'no sample found' in m[1]
        for m in logger.messages if m[0] == 'warning'
    )
    assert meas.pvk_sample is None


# ─────────────────────────────────────────────────────────────────────────────
# Test: pvk_sample takes precedence over pvk_sample_id (Mode A wins)
# ─────────────────────────────────────────────────────────────────────────────

def test_direct_reference_takes_precedence_over_id():
    logger = DummyLogger()
    sample = PerovskiteSolarCellSample()

    meas = JVMeasurement()
    meas.pvk_sample    = sample           # Mode A — direct ref
    meas.pvk_sample_id = 'PVK-TEST-001'  # Mode B — also set, should be ignored

    resolve_called = []

    original_resolve = meas._resolve_sample

    def tracking_resolve(archive, logger):
        resolve_called.append(True)
        original_resolve(archive, logger)

    with patch.object(meas, '_resolve_sample', side_effect=tracking_resolve):
        _patched_normalize(meas, _make_archive(), logger)

    # _resolve_sample was called but pvk_sample was unchanged (not overwritten)
    assert meas.pvk_sample is sample
    assert len(sample.performed_measurements.jv) == 1