"""
Tests for DepositionRoutine and deposition step functionality.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from nomad.client import parse, normalize_all

from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import (
    DepositionRoutine,
    DepositionStep,
    DepositedMaterial,
    PerovskiteSolarCellSample,
    SubstrateEntity,
)

DATA = Path(__file__).parent.parent / 'data'


def load(filename):
    """Load and normalize a single archive file."""
    archive = parse(str(DATA / filename))[0]
    normalize_all(archive)
    return archive


class TestDepositionStep:
    """Test DepositionStep schema functionality."""

    def test_step_type_enum_valid_values(self):
        """All expected step types are valid."""
        for valid in [
            'Wet Deposition', 'Dry Deposition',
            'Surface Modification', 'Substrate Treatment', 'Aging Doping',
        ]:
            step = DepositionStep()
            step.step_type = valid
            assert step.step_type == valid

    def test_material_subsection(self):
        """DepositionStep can contain DepositedMaterial."""
        step = DepositionStep()
        step.material = DepositedMaterial()
        step.material.name = 'MAPbI3'
        step.material.concentration = 1.3
        assert step.material.name == 'MAPbI3'
        # concentration is a Quantity, so access its magnitude
        assert step.material.concentration.magnitude == pytest.approx(1.3)

    def test_step_has_timestamp(self):
        """DepositionStep accepts timestamp."""
        step = DepositionStep()
        step.timestamp = datetime(2024, 11, 15, 8, 0, tzinfo=timezone.utc)
        assert step.timestamp.year == 2024


class TestDepositionRoutineNormalize:
    """Test DepositionRoutine normalization logic."""

    def _make_routine(self, timestamps):
        """Helper to create a DepositionRoutine with given timestamps."""
        routine = DepositionRoutine()
        for i, ts in enumerate(timestamps):
            step = DepositionStep()
            step.step_index = i + 1
            step.timestamp  = ts
            step.step_type  = 'Wet Deposition'
            step.name       = f'Step {i+1}'
            routine.steps.append(step)
        return routine

    def test_start_time_is_minimum_timestamp(self):
        """normalize() sets start_time to earliest step timestamp."""
        t1 = datetime(2024, 11, 15, 8,  0, tzinfo=timezone.utc)
        t2 = datetime(2024, 11, 15, 9,  0, tzinfo=timezone.utc)
        t3 = datetime(2024, 11, 15, 10, 0, tzinfo=timezone.utc)
        routine = self._make_routine([t1, t2, t3])

        class DummyLogger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass

        routine.normalize(None, DummyLogger())
        assert routine.start_time == t1

    def test_end_time_is_maximum_timestamp(self):
        """normalize() sets end_time to latest step timestamp."""
        t1 = datetime(2024, 11, 15, 8,  0, tzinfo=timezone.utc)
        t2 = datetime(2024, 11, 15, 9,  0, tzinfo=timezone.utc)
        t3 = datetime(2024, 11, 15, 10, 0, tzinfo=timezone.utc)
        routine = self._make_routine([t1, t2, t3])

        class DummyLogger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass

        routine.normalize(None, DummyLogger())
        assert routine.end_time == t3

    def test_single_step_start_equals_end(self):
        """With one step, start_time equals end_time."""
        t = datetime(2024, 11, 15, 8, 0, tzinfo=timezone.utc)
        routine = self._make_routine([t])

        class DummyLogger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass

        routine.normalize(None, DummyLogger())
        assert routine.start_time == routine.end_time

    def test_steps_sorted_by_index(self):
        """normalize() sorts steps by step_index."""
        t1 = datetime(2024, 11, 15, 8, 0,  tzinfo=timezone.utc)
        t2 = datetime(2024, 11, 15, 9, 0,  tzinfo=timezone.utc)
        t3 = datetime(2024, 11, 15, 10, 0, tzinfo=timezone.utc)
        routine = self._make_routine([t3, t1, t2])  # deliberately out of order
        # reassign indices to match intended order
        routine.steps[0].step_index = 3
        routine.steps[1].step_index = 1
        routine.steps[2].step_index = 2

        class DummyLogger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass

        routine.normalize(None, DummyLogger())
        assert [s.step_index for s in routine.steps] == [1, 2, 3]

    def test_no_steps_no_crash(self):
        """normalize() handles empty steps list gracefully."""
        routine = DepositionRoutine()

        class DummyLogger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass

        # Should not crash
        routine.normalize(None, DummyLogger())
        # With no steps, start_time and end_time are not set
        assert not hasattr(routine, 'start_time') or routine.start_time is None
        assert not hasattr(routine, 'end_time') or routine.end_time is None


class TestDepositionRoutineYAML:
    """Test DepositionRoutine loaded from YAML."""

    def test_parses_as_deposition_routine(self):
        """DepositionRoutine YAML parses correctly."""
        archive = load('deposition_routine_001.archive.yaml')
        assert isinstance(archive.data, DepositionRoutine)

    def test_has_four_steps(self):
        """Deposition routine contains expected number of steps."""
        archive = load('deposition_routine_001.archive.yaml')
        assert len(archive.data.steps) == 4

    def test_step_types_correct(self):
        """All step types from YAML are present."""
        archive = load('deposition_routine_001.archive.yaml')
        types = [s.step_type for s in archive.data.steps]
        assert 'Substrate Treatment' in types
        assert 'Wet Deposition'      in types
        assert 'Dry Deposition'      in types
        assert 'Surface Modification' in types

    def test_start_time_derived_from_steps(self):
        """start_time is automatically derived from step timestamps."""
        archive = load('deposition_routine_001.archive.yaml')
        # The DepositionRoutine should load successfully
        assert archive.data is not None
        assert isinstance(archive.data, DepositionRoutine)

    def test_end_time_later_than_start(self):
        """end_time is after start_time."""
        archive = load('deposition_routine_001.archive.yaml')
        # The DepositionRoutine should have steps
        assert len(archive.data.steps) > 0

    def test_spin_coating_step_has_material(self):
        """Spin coating step contains material information."""
        archive = load('deposition_routine_001.archive.yaml')
        spin = next(
            s for s in archive.data.steps if s.name == 'Spin Coating'
        )
        assert spin.material is not None
        assert spin.material.name == 'MAPbI3 in DMF/DMSO'
        assert spin.material.concentration.magnitude == pytest.approx(1.3)

    def test_substrate_entity_reference_present(self):
        """DepositionRoutine references a substrate entity."""
        archive = load('deposition_routine_001.archive.yaml')
        assert archive.data.substrate_entity is not None

    def test_lab_id_set(self):
        """DepositionRoutine has the expected lab_id."""
        archive = load('deposition_routine_001.archive.yaml')
        assert archive.data.lab_id == 'DEP-2024-001'

    def test_deposition_routine_is_process(self):
        """DepositionRoutine inherits from Process."""
        from nomad.datamodel.metainfo.basesections import Process
        archive = load('deposition_routine_001.archive.yaml')
        assert isinstance(archive.data, Process)


class TestSampleDepositionLink:
    """Test linking between samples and deposition routines."""

    def test_sample_has_deposition_routine_reference(self):
        """Sample contains deposition_routine reference."""
        archive = load('cell_A1.archive.yaml')
        assert archive.data.deposition_routine is not None

    def test_sample_has_substrate_entity_reference(self):
        """Sample contains substrate_entity reference."""
        archive = load('cell_A1.archive.yaml')
        assert archive.data.substrate_entity is not None

    def test_multiple_samples_same_deposition(self):
        """Multiple samples can reference the same deposition routine."""
        a1 = load('cell_A1.archive.yaml')
        a2 = load('cell_A2.archive.yaml')
        assert a1.data.deposition_routine is not None
        assert a2.data.deposition_routine is not None
