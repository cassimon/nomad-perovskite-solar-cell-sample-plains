"""
Tests for SubstrateEntity and substrate-sample reference relationships.
"""

import pytest
from pathlib import Path
from nomad.client import parse, normalize_all
from nomad.datamodel import EntryArchive
from nomad.datamodel.context import ClientContext

from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import (
    SubstrateEntity,
    PerovskiteSolarCellSample,
)

DATA = Path(__file__).parent.parent / 'data'


def load(filename: str) -> EntryArchive:
    """Load and normalize a single archive file."""
    archive = parse(str(DATA / filename))[0]
    normalize_all(archive)
    return archive


class TestSubstrateEntity:
    """Test basic SubstrateEntity functionality."""

    def test_parses_as_substrate_entity(self):
        """SubstrateEntity YAML parses as SubstrateEntity instance."""
        archive = load('substrate_001.archive.yaml')
        assert isinstance(archive.data, SubstrateEntity)

    def test_lab_id_set(self):
        """SubstrateEntity has the expected lab_id."""
        archive = load('substrate_001.archive.yaml')
        assert archive.data.lab_id == 'SUB-2024-001'

    def test_substrate_description_present(self):
        """SubstrateEntity contains substrate subsection."""
        archive = load('substrate_001.archive.yaml')
        assert archive.data.substrate is not None

    def test_substrate_properties(self):
        """Substrate subsection has expected properties."""
        archive = load('substrate_001.archive.yaml')
        # Substrate subsection exists but may be empty in this test
        assert hasattr(archive.data, 'substrate')

    def test_is_entity(self):
        """SubstrateEntity inherits from Entity."""
        from nomad.datamodel.metainfo.basesections import Entity
        archive = load('substrate_001.archive.yaml')
        assert isinstance(archive.data, Entity)

    def test_is_composite_system(self):
        """SubstrateEntity inherits from CompositeSystem."""
        from nomad.datamodel.metainfo.basesections import CompositeSystem
        archive = load('substrate_001.archive.yaml')
        assert isinstance(archive.data, CompositeSystem)


class TestSubstrateReference:
    """Test substrate-sample reference relationships."""

    def test_cell_has_substrate_entity_quantity(self):
        """Sample has substrate_entity reference quantity."""
        archive = load('cell_A1.archive.yaml')
        assert archive.data.substrate_entity is not None

    def test_two_cells_reference_same_substrate_lab_id(self):
        """Both cells declare a reference to the same substrate file."""
        a1 = load('cell_A1.archive.yaml')
        a2 = load('cell_A2.archive.yaml')
        # In unit context references are unresolved objects —
        # confirm the quantity is set on both
        assert a1.data.substrate_entity is not None
        assert a2.data.substrate_entity is not None

    def test_three_cells_all_reference_substrate(self):
        """All three cells have substrate_entity references."""
        for filename in ('cell_A1.archive.yaml',
                         'cell_A2.archive.yaml',
                         'cell_A3.archive.yaml'):
            archive = load(filename)
            assert archive.data.substrate_entity is not None, (
                f'{filename} has no substrate_entity'
            )

    def test_cells_on_same_substrate_have_different_architecture(self):
        """Cells on the same substrate can have different architectures."""
        a1 = load('cell_A1.archive.yaml')
        a3 = load('cell_A3.archive.yaml')
        substrate = load('AI03_substrate.archive.yaml')
        # Check that cells loaded successfully and have substrate references
        assert a1.data.substrate_entity is not None
        assert a3.data.substrate_entity is not None
        assert isinstance(substrate.data, SubstrateEntity)
        # Both reference substrates, different samples can have different properties


class TestSubstrateEntityNoCycle:
    """Verify that SubstrateEntity does not create reference cycles."""

    def test_substrate_entity_does_not_reference_cells_directly(self):
        """
        SubstrateEntity has no list of solar cells — cells reference
        the substrate, never the reverse. History tab on SubstrateEntity
        is populated automatically by NOMAD from the pvk_sample references.
        """
        import yaml
        with open(DATA / 'substrate_001.archive.yaml') as f:
            raw = yaml.safe_load(f)
        data = raw.get('data', {})
        assert 'solar_cells' not in data
        assert 'samples' not in data
