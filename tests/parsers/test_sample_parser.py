"""The sample must be processed *after* the measurements it searches for.

`PerovskiteSolarCellSampleArea.normalize` finds its JV / EQE / stability entries
with an Elasticsearch query, so they have to be indexed by the time it runs. The
built-in archive parser puts every archive YAML on level -1 -- sample and
measurements together, concurrently -- which makes that a race. NOMAD processes
levels strictly in order, so the sample gets a level of its own.
"""

from pathlib import Path

from nomad_perovskite_solar_cell_sample_plains.parsers import (
    sample_parser_entry_point,
    substrate_parser_entry_point,
)
from nomad_perovskite_solar_cell_sample_plains.parsers.parsers import PlainsSampleParser

DATA = Path(__file__).parent.parent / 'data'

SAMPLE_M_DEF = (
    'nomad_perovskite_solar_cell_sample_plains.schema_packages.sample.'
    'PerovskiteSolarCellSampleArea'
)


def parser(entry_point=sample_parser_entry_point):
    return PlainsSampleParser(**entry_point.model_dump())


def is_mainfile(filename, entry_point=sample_parser_entry_point):
    text = (DATA / filename).read_text()
    return parser(entry_point).is_mainfile(
        str(DATA / filename), 'text/plain', text.encode(), text
    )


def test_the_sample_is_processed_after_the_measurement_archives():
    """Above -1, the level the built-in archive parser puts the measurements on."""
    assert sample_parser_entry_point.level > -1
    assert parser().level == sample_parser_entry_point.level


def test_it_claims_the_sample_archives():
    assert is_mainfile('dev1.archive.yaml')


def test_it_leaves_the_other_archives_to_the_built_in_parser():
    """A deposition archive has no measurements to wait for; moving it to a later
    level would only delay the upload."""
    assert not is_mainfile('substrate.archive.yaml')
    assert not is_mainfile('deposition.archive.yaml')


# ── The substrate comes after the devices ─────────────────────────────────────


def test_the_substrate_is_processed_after_the_devices_it_mirrors():
    """`SubstrateSample.normalize` copies the overview figures of each device on it,
    and those figures only exist once the *device* has normalized."""
    assert substrate_parser_entry_point.level > sample_parser_entry_point.level


def test_the_substrate_parser_claims_only_substrate_archives():
    assert is_mainfile('substrate.archive.yaml', substrate_parser_entry_point)
    assert not is_mainfile('dev1.archive.yaml', substrate_parser_entry_point)
    assert not is_mainfile('deposition.archive.yaml', substrate_parser_entry_point)


def test_a_substrate_archive_still_parses_into_the_substrate_section():
    from nomad.client import parse

    archive = parse(str(DATA / 'substrate.archive.yaml'))[0]
    assert type(archive.data).__name__ == 'SubstrateSample'


def test_a_sample_archive_still_parses_into_the_sample_section():
    """The parsing itself is the built-in one -- only the level differs."""
    from nomad.client import parse

    archive = parse(str(DATA / 'dev1.archive.yaml'))[0]
    assert SAMPLE_M_DEF.endswith(type(archive.data).__name__)
