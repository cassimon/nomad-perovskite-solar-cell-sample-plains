from types import SimpleNamespace

from nomad.metainfo import Section

from unittest.mock import MagicMock, patch
from nomad.metainfo import Section

from nomad_perovskite_solar_cell_sample_plains.schema_packages.schema_package import (
    PerovskiteSolarCellSample,
    PVKMeasurementBase,
    PerformedMeasurements,
)


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


class ConcreteMeasurement(PVKMeasurementBase):
    m_def = Section(label='ConcreteMeasurement')

    def _register_into_sample(self, performed: PerformedMeasurements, logger):
        performed._registered = getattr(performed, '_registered', 0) + 1


def test_pvk_measurement_normalize_registration():
    logger = DummyLogger()

    # Minimal archive stub — satisfies NOMAD base normalize() calls
    archive = MagicMock()
    archive.metadata = MagicMock()
    archive.results  = MagicMock()
    archive.m_context = None   # prevents context-based resolution attempts

    meas = ConcreteMeasurement()

    # ── Case 1: no pvk_sample → warning, no crash ───────────────────────────
    meas.pvk_sample = None

    # Patch super().normalize() to be a no-op so NOMAD internals don't run.
    # We are only testing OUR normalize() logic here, not NOMAD's.
    with patch.object(PVKMeasurementBase.__bases__[0], 'normalize', return_value=None):
        meas.normalize(archive, logger)

    assert any(
        'no pvk_sample' in m[1]
        for m in logger.messages if m[0] == 'warning'
    )

    # ── Case 2: pvk_sample set → performed_measurements created ─────────────
    sample = PerovskiteSolarCellSample()
    meas.pvk_sample = sample
    logger = DummyLogger()

    with patch.object(PVKMeasurementBase.__bases__[0], 'normalize', return_value=None):
        meas.normalize(archive, logger)

    assert isinstance(sample.performed_measurements, PerformedMeasurements)
    assert getattr(sample.performed_measurements, '_registered', 0) == 1


def test_performed_measurements_category_lists():
    """Verify different measurement types register into their respective lists."""
    logger = DummyLogger()

    class JVMeasurement(PVKMeasurementBase):
        m_def = Section(label='JVMeasurement')

        def _register_into_sample(self, performed: PerformedMeasurements, logger):
            performed.jv = getattr(performed, 'jv', [])
            performed.jv.append('JV1')

    class EQEMeasurement(PVKMeasurementBase):
        m_def = Section(label='EQEMeasurement')

        def _register_into_sample(self, performed: PerformedMeasurements, logger):
            performed.eqe = getattr(performed, 'eqe', [])
            performed.eqe.append('EQE1')

    class StabilityMeasurement(PVKMeasurementBase):
        m_def = Section(label='StabilityMeasurement')

        def _register_into_sample(self, performed: PerformedMeasurements, logger):
            performed.stability = getattr(performed, 'stability', [])
            performed.stability.append('STAB1')

    sample = PerovskiteSolarCellSample()

    # create and register one of each
    with patch.object(PVKMeasurementBase.__bases__[0], 'normalize', return_value=None):
        JVMeasurement().__setattr__('pvk_sample', sample) or JVMeasurement().normalize(None, logger)
    # Re-create instance to avoid state carry-over
    jm = JVMeasurement()
    jm.pvk_sample = sample
    with patch.object(PVKMeasurementBase.__bases__[0], 'normalize', return_value=None):
        jm.normalize(None, logger)

    em = EQEMeasurement()
    em.pvk_sample = sample
    with patch.object(PVKMeasurementBase.__bases__[0], 'normalize', return_value=None):
        em.normalize(None, logger)

    sm = StabilityMeasurement()
    sm.pvk_sample = sample
    with patch.object(PVKMeasurementBase.__bases__[0], 'normalize', return_value=None):
        sm.normalize(None, logger)

    performed = sample.performed_measurements
    assert performed is not None
    assert getattr(performed, 'jv', []) == ['JV1', 'JV1'] or len(getattr(performed, 'jv', [])) >= 1
    assert getattr(performed, 'eqe', []) == ['EQE1']
    assert getattr(performed, 'stability', []) == ['STAB1']
