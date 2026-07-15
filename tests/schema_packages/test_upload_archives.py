from pathlib import Path

import pytest
from nomad.client import normalize_all, parse

from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import (
    DepositionRoutine,
    PerovskiteSolarCellSampleArea,
    SubstrateSample,
)


DATA = Path(__file__).parent.parent / 'data'


def load(filename: str):
    archive = parse(str(DATA / filename))[0]
    normalize_all(archive)
    return archive


def test_substrate_and_deposition_archives_upload():
    substrate_archive = load('substrate.archive.yaml')
    deposition_archive = load('deposition.archive.yaml')

    assert isinstance(substrate_archive.data, SubstrateSample)
    assert substrate_archive.data.m_def.label == 'Substrate'
    assert substrate_archive.data.lab_id == '5ffdda0f-eeb8-4d5b-85c4-aeab273418bd'
    assert substrate_archive.data.substrate is not None
    assert len(substrate_archive.data.cell_areas) == 4

    assert isinstance(deposition_archive.data, DepositionRoutine)
    assert deposition_archive.data.m_def.label == 'Deposition Routine'
    assert deposition_archive.data.lab_id == '5ffdda0f-eeb8-4d5b-85c4-aeab273418bd_deposition'
    assert len(deposition_archive.data.samples) == 1
    assert len(deposition_archive.data.steps) == 7
    # A `DepositionRoutine` is a `Process`: its start is the inherited `datetime`
    # (only its *steps* carry a `start_time`), back-filled from the earliest step.
    assert deposition_archive.data.datetime.isoformat() == '2026-05-21T08:00:00+00:00'
    assert deposition_archive.data.end_time.isoformat() == '2026-05-22T11:00:00+00:00'


@pytest.mark.parametrize(
    'filename, expected_name, expected_lab_id',
    [
        ('dev1.archive.yaml', 'AI03', '0354238c-8890-4124-8cfe-9997aa011623'),
        ('dev2.archive.yaml', 'AI03 device 2', '5ffdda0f-eeb8-4d5b-85c4-aeab273418bd_dev2'),
        ('dev3.archive.yaml', 'AI03 device 3', '5ffdda0f-eeb8-4d5b-85c4-aeab273418bd_dev3'),
        ('dev4.archive.yaml', 'AI03 device 4', '5ffdda0f-eeb8-4d5b-85c4-aeab273418bd_dev4'),
    ],
)
def test_sample_area_archives_upload(filename, expected_name, expected_lab_id):
    archive = load(filename)

    assert isinstance(archive.data, PerovskiteSolarCellSampleArea)
    assert archive.data.m_def.label == 'Perovskite Solar Cell Sample'
    assert archive.data.name == expected_name
    assert archive.data.lab_id == expected_lab_id
    assert archive.data.substrate is not None
    assert archive.data.cell is not None
    assert archive.data.perovskite_deposition is not None

    quenching_parameters = archive.data.perovskite_deposition.quenching_parameters
    assert quenching_parameters is not None
    assert quenching_parameters.antisolvent is not None
    assert quenching_parameters.antisolvent.media == 'Chlorobenzene'
    assert quenching_parameters.antisolvent.deposition_method == 'drip'
    assert quenching_parameters.antisolvent.flow_rate.magnitude == pytest.approx(10.0)