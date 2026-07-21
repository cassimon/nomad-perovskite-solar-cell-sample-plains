"""The material / solution ELN entities the Plains app emits.

These check that the archive shape the backend writes deserializes onto the
intended `baseclasses` ELN quantities -- the identifiers land on `Substance`
fields, supplier metadata on `ProductInfo`, and a solution's components split into
the solvent / solute / other-solution buckets. `nomad.client.parse` deserializes
without running the (potentially network-touching) normalizers, which is exactly
the round-trip we want to pin down.
"""

from pathlib import Path

from nomad.client import parse

DATA = Path(__file__).parent.parent / 'data'


def test_material_archive_parses_onto_the_eln_quantities():
    material = parse(str(DATA / 'material.archive.yaml'))[0].data

    assert type(material).__name__ == 'PlainsMaterial'
    # The inventory label is the lab-unique id; the identifiers land on Substance.
    assert material.lab_id == 'INV-PBI2'
    assert material.cas_number == '13462-72-8'
    assert material.purity == '99.99%'
    assert material.material_category == 'lead salt'
    assert str(material.state_of_matter) == 'Solid'
    assert material.molecular_mass.to('Da').magnitude == 461.0
    assert material.density.to('g/cm**3').magnitude == 6.16
    # The verified PubChem identity, pinned so processing never re-fetches it.
    assert material.substance.pub_chem_cid == 24956
    assert material.substance.load_data is False
    # Supplier metadata on the standard ProductInfo section.
    assert material.product_info.supplier == 'TCI'
    assert material.product_info.product_number == 'L0279'


def test_solution_archive_parses_components_into_the_right_buckets():
    solution = parse(str(DATA / 'solution.archive.yaml'))[0].data

    assert type(solution).__name__ == 'PlainsSolution'
    # The batch's vial label, which is how a lab finds it again.
    assert solution.lab_id == 'PVK_2026-03-01'
    # The category, split out of `description` so the two are separately
    # recoverable instead of one unsplittable blob.
    assert solution.solution_type == 'perovskite precursor'
    assert solution.handling == (
        'Preparation: Stir at 60 C\n\nBefore use: Filter with 0.45 um PTFE'
    )
    assert solution.solvent_ratio == '4:1'
    assert solution.storage[0].storage_condition == 'N2 fridge'
    assert solution.properties.final_volume.to('ml').magnitude == 2.0

    # A solvent carries a volume, its recipe ratio, and its inventory label.
    assert [chemical.name for chemical in solution.solvent] == ['DMF', 'DMSO']
    assert solution.solvent[0].chemical_volume.to('ml').magnitude == 1.6
    assert solution.solvent[0].amount_relative == 4.0
    assert solution.solvent[0].chemical_id == 'INV-DMF'
    assert solution.solvent[1].amount_relative == 1.0

    # A solute carries an amount and a strength.
    assert [chemical.name for chemical in solution.solute] == ['PbI2']
    assert solution.solute[0].amount_mol.to('mol').magnitude == 1.4
    assert solution.solute[0].chemical_mass.to('mg').magnitude == 922.0
    assert solution.solute[0].concentration_mass.to('mg/ml').magnitude == 461.0
    assert solution.solute[0].chemical_2.pub_chem_cid == 24956
    assert solution.solute[0].chemical_id == 'INV-PBI2'

    # A mixed-in commercial product is an additive, not a mislabelled solute.
    assert [chemical.name for chemical in solution.additive] == ['Surfactant X']
    assert solution.additive[0].chemical_mass.to('mg').magnitude == 5.0
    assert solution.additive[0].chemical_id == 'INV-SURF'

    # A stock solution mixed in is an other_solution row, not a flattened string.
    assert [other.name for other in solution.other_solution] == ['PbI2 stock']
    assert solution.other_solution[0].solution_volume.to('ml').magnitude == 0.5
    assert solution.other_solution[0].amount_relative == 1.0


def test_solution_components_drive_the_composition_overview():
    """`solute`/`solvent`/`additive` rows are not `components`, NOMAD reads the latter."""
    solution = parse(str(DATA / 'solution.archive.yaml'))[0].data

    assert [type(c).__name__ for c in solution.components] == [
        'PureSubstanceComponent',
        'Component',
    ]
    substance_component = solution.components[0]
    assert substance_component.substance_name == 'PbI2'
    assert substance_component.pure_substance.pub_chem_cid == 24956
    assert substance_component.pure_substance.load_data is False

    # The nested solution: name only, deliberately no `system` reference (see
    # the fixture comment for why) -- still reconstructable via other_solution.
    nested_component = solution.components[1]
    assert nested_component.name == 'PbI2 stock'


def test_solution_composition_table_gathers_every_row_with_its_concentration():
    """The Overview "Materials" table shows the concentrations `components` omit."""
    from nomad_perovskite_solar_cell_sample_plains.utils import (
        create_solution_composition_figure,
    )

    solution = parse(str(DATA / 'solution.archive.yaml'))[0].data
    figure = create_solution_composition_figure(solution)

    table = figure.data[0]
    assert table.type == 'table'
    names, roles, concentrations, amounts = table.cells.values

    # Every solute / solvent / additive / other_solution row, in that order.
    assert list(names) == ['PbI2', 'DMF', 'DMSO', 'Surfactant X', 'PbI2 stock']
    assert list(roles) == ['Solute', 'Solvent', 'Solvent', 'Additive', 'Solution']
    # The recorded concentration is shown where present, blank otherwise.
    assert concentrations[0] == '461 mg/ml'
    assert concentrations[1] == ''
    # The first recorded absolute amount is shown per row.
    assert list(amounts) == ['922 mg', '1.6 ml', '0.4 ml', '5 mg', '0.5 ml']


def test_solution_composition_table_is_none_without_components():
    """An empty solution shows no empty card."""
    from nomad_perovskite_solar_cell_sample_plains.schema_packages.chemicals import (
        PlainsSolution,
    )
    from nomad_perovskite_solar_cell_sample_plains.utils import (
        create_solution_composition_figure,
    )

    assert create_solution_composition_figure(PlainsSolution()) is None


def test_material_records_the_constituents_of_a_mixture():
    """A mixture has no CID of its own, so each constituent gets a section."""
    material = parse(str(DATA / 'mixture.archive.yaml'))[0].data

    assert type(material).__name__ == 'PlainsMaterial'
    assert material.lab_id == 'INV-PEDOT'
    assert [substance.pub_chem_cid for substance in material.component_substances] == [
        61503,
        62717,
    ]
    assert all(
        substance.load_data is False for substance in material.component_substances
    )
