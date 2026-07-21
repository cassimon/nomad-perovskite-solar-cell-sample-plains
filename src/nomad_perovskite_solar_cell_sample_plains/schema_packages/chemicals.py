"""First-class ELN entities for the materials and solutions the Plains app tracks.

The app knows a material as a full inventory record (identifiers, supplier,
purity, ...) and a solution as a structured recipe (which components, how much,
and which *other* solutions were mixed into it). Both used to reach NOMAD only as
flattened strings on the perovskite-database layer sections and as a
`DepositedMaterial` summary on the deposition step.

These two classes give each of them an entry of its own, reusing the NOMAD/HZB
`baseclasses` ELN base sections so the app data lands on standard, searchable,
cross-referenceable quantities:

- `PlainsMaterial(Chemical)` -- `Chemical -> eln.Substance -> System/Entity`. The
  identifier block (`cas_number`, `molecular_mass`, InChI/SMILES, `lab_id`) comes
  for free, and because `baseclasses.solution.SolutionChemical.chemical` is a
  `Reference(Chemical)`, a material entry is natively referenceable from a
  solution's components.
- `PlainsSolution(Solution)` -- `Solution -> CompositeSystem`. Its `solvent` /
  `solute` / `additive` rows reference `Chemical` entries, and `other_solution`
  references *another* `Solution` entry, which is exactly how the app models a
  solution built from stock solutions.
"""

from baseclasses import PubChemPureSubstanceSectionCustom
from baseclasses.chemical import Chemical
from baseclasses.product_info import ProductInfo
from baseclasses.solution import Solution
from nomad.config import config
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.datamodel.metainfo.plot import PlotlyFigure, PlotSection
from nomad.metainfo import Quantity, SchemaPackage, Section, SubSection

from nomad_perovskite_solar_cell_sample_plains.utils import (
    create_solution_composition_figure,
)

configuration = config.get_plugin_entry_point(
    'nomad_perovskite_solar_cell_sample_plains.schema_packages:chemicals_entry_point'
)

m_package = SchemaPackage()


class PlainsMaterial(Chemical):
    """A chemical from the Plains inventory.

    Inherits the `Substance` identifier block (`name`, `lab_id`, `cas_number`,
    `molecular_mass`, `molecular_formula`, InChI/SMILES, `description`) and
    `Chemical.state_of_matter`. The app's inventory label maps onto `lab_id` --
    the Entity notion of a lab-unique identifier -- so it is searchable; supplier
    metadata goes into `product_info`, and the verified PubChem identity into
    `substance` (pre-filled, `load_data=False`, so processing never calls out to
    PubChem).
    """

    m_def = Section(
        label='Material',
        a_eln=dict(
            properties=dict(
                order=[
                    'name',
                    'lab_id',
                    'material_category',
                    'cas_number',
                    'purity',
                    'molecular_mass',
                    'density',
                    'state_of_matter',
                    'component_substances',
                ]
            )
        ),
    )

    material_category = Quantity(
        type=str,
        description='The app material category / type (e.g. solvent, salt, substrate).',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    purity = Quantity(
        type=str,
        description='Purity as recorded in the app inventory (free text, e.g. "99.99%").',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    density = Quantity(
        type=float,
        unit='g/cm**3',
        description='Mass density.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity', defaultDisplayUnit='g/cm**3'
        ),
    )

    substance = SubSection(
        section_def=PubChemPureSubstanceSectionCustom,
        description='PubChem identity of the material (CID and derived identifiers).',
    )
    component_substances = SubSection(
        section_def=PubChemPureSubstanceSectionCustom,
        repeats=True,
        description=(
            'PubChem identities of the constituents, for a material that is a '
            'mixture (PEDOT:PSS and the like) and so has no single CID of its own.'
        ),
    )
    product_info = SubSection(
        section_def=ProductInfo,
        description='Supplier and product information for this material.',
    )


class PlainsSolution(Solution, PlotSection):
    """A solution mixed in the Plains lab (a `LabSolution` or a process recipe).

    `Solution` already carries everything the app records: `solvent` / `solute` /
    `additive` rows (each referencing a `Chemical` entry, with volume/mass/mol
    amounts), `other_solution` rows referencing another `Solution` entry (the
    stock-solution case), `preparation`, `storage`, and the `datetime` creation
    timestamp. Only the app's free-text handling instructions and its solution
    category have no home on the base, so they are added here.

    Being a `PlotSection`, it also draws a "Materials" table on the Overview: the
    per-row concentrations and amounts live on `solute`/`solvent`/`additive`, which
    are not `components`, so NOMAD's built-in composition card never shows them.
    """

    m_def = Section(
        label='Solution',
        a_eln=dict(
            properties=dict(
                order=[
                    'name',
                    'lab_id',
                    'datetime',
                    'solution_type',
                    'handling',
                    'solvent_ratio',
                    'solute',
                    'solvent',
                    'additive',
                    'other_solution',
                ]
            )
        ),
    )

    handling = Quantity(
        type=str,
        description='Handling instructions recorded in the app (free text).',
        a_eln=ELNAnnotation(component='RichTextEditQuantity'),
    )
    solution_type = Quantity(
        type=str,
        description=(
            'The app solution category (e.g. "perovskite precursor", "n-type (ETL)").'
        ),
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )

    def normalize(self, archive, logger):
        # Built from the raw solute/solvent/additive/other_solution rows, before
        # `super().normalize()`, so the Materials table is drawn even if a base
        # normalizer trips over an unresolved cross-entry reference. `PlotSection`
        # in the base chain leaves these figures alone (it only clears `figures`
        # when the section carries plotly annotations, which this one does not).
        figure = create_solution_composition_figure(self)
        if figure is not None:
            self.figures = [
                PlotlyFigure(label='Materials', figure=figure.to_plotly_json())
            ]
        super().normalize(archive, logger)


m_package.__init_metainfo__()
