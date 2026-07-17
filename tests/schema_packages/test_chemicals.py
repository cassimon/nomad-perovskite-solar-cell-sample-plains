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
    assert solution.lab_id == 'sol-main'
    assert solution.handling == 'Prepared in glovebox'
    assert solution.storage[0].storage_condition == 'N2 fridge'

    # A solvent carries a volume; a solute carries a molar amount.
    assert [chemical.name for chemical in solution.solvent] == ['DMF']
    assert solution.solvent[0].chemical_volume.to('ml').magnitude == 1.0
    assert [chemical.name for chemical in solution.solute] == ['PbI2']
    assert solution.solute[0].amount_mol.to('mol').magnitude == 1.4
    assert solution.solute[0].chemical_2.pub_chem_cid == 24956

    # A stock solution mixed in is an other_solution row, not a flattened string.
    assert [other.name for other in solution.other_solution] == ['PbI2 stock']
    assert solution.other_solution[0].solution_volume.to('ml').magnitude == 0.5
