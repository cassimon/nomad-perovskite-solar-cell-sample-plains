"""Integration-style parsing tests for example upload archives."""

from pathlib import Path

from nomad.client import normalize_all, parse

from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import (
    DepositionRoutine,
    PerovskiteSolarCellSample,
    SubstrateEntity,
)

DATA = Path(__file__).parent.parent / 'data'


def load(filename: str):
    archive = parse(str(DATA / filename))[0]
    normalize_all(archive)
    return archive


class TestAI03Uploads:
    def test_ai03_substrate_parses(self):
        archive = load('AI03_substrate.archive.yaml')
        assert isinstance(archive.data, SubstrateEntity)
        assert archive.data.lab_id == '5ffdda0f-eeb8-4d5b-85c4-aeab273418bd'
        assert archive.data.substrate is not None
        assert archive.data.substrate.stack_sequence == 'Glass | ITO'

    def test_ai03_deposition_parses(self):
        archive = load('AI03_deposition.archive.yaml')
        assert isinstance(archive.data, DepositionRoutine)
        assert archive.data.substrate_entity is not None
        assert len(archive.data.steps) == 7
        assert archive.data.steps[0].step_index == 1
        assert archive.data.steps[-1].step_index == 7

    def test_ai03_deposition_has_valid_time_window(self):
        archive = load('AI03_deposition.archive.yaml')
        assert archive.data.start_time is not None
        assert archive.data.end_time is not None
        assert archive.data.start_time < archive.data.end_time


class TestDevUpload:
    def test_dev_archive_parses(self):
        archive = load('dev.archive.yaml')
        assert isinstance(archive.data, PerovskiteSolarCellSample)
        assert archive.data.lab_id == 'PVK-TEST-001'
        assert archive.data.cell is not None
        assert archive.data.cell.architecture == 'nip'

    def test_dev_archive_links_are_present(self):
        archive = load('dev.archive.yaml')
        assert archive.data.substrate_entity is not None
        assert archive.data.deposition_routine is not None

    def test_dev_archive_stores_quenching_parameters(self):
        archive = load('dev.archive.yaml')
        quenching = archive.data.perovskite_deposition.quenching_parameters
        assert quenching is not None
        assert quenching.antisolvent is not None
        assert quenching.antisolvent.media == 'Chlorobenzene'
        assert quenching.antisolvent.deposition_method == 'drip'
        assert quenching.antisolvent.flow_rate.magnitude == 10.0
