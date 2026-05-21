from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import (
        EntryArchive,
    )
    from structlog.stdlib import (
        BoundLogger,
    )


from nomad.config import config
from nomad.datamodel.data import EntryData, ArchiveSection
from nomad.datamodel.metainfo.basesections import (
    Entity,
    Process,
    CompositeSystem,
)
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.metainfo import (
    Datetime,
    MEnum,
    Quantity,
    Reference,
    Section,
    SubSection,
    SchemaPackage,
)
from nomad.search import search
from nomad.app.v1.models import MetadataPagination

configuration = config.get_plugin_entry_point(
    'nomad_perovskite_solar_cell_sample_plains.schema_packages:schema_package_entry_point'
)


from perovskite_solar_cell_database.schema import PerovskiteSolarCell, Substrate, PerovskiteDeposition

# baseclasses solar energy measurement sections — no tandem anywhere
from baseclasses.solar_energy.jvmeasurement import JVMeasurement
from baseclasses.solar_energy.eqemeasurement import EQEMeasurement
from baseclasses.solar_energy.mpp_tracking import MPPTracking

m_package = SchemaPackage()


# ── Material / Solution used in a deposition step ────────────────────────────

class DepositedMaterial(ArchiveSection):
    """
    A material or solution applied during a deposition step.
    Kept as a descriptive ArchiveSection — for a full lab entity
    (e.g. a prepared solution batch) use a separate SolutionEntity
    and reference it here.
    """
    name = Quantity(
        type=str,
        description='Name of the material or solution, e.g. "MAPbI3 in DMF/DMSO".',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    concentration = Quantity(
        type=float,
        unit='mol/l',
        description='Concentration of the solution if applicable.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='mol/l',
        ),
    )
    supplier = Quantity(
        type=str,
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )


# ── Abstract base for all deposition steps ───────────────────────────────────

STEP_TYPES = MEnum(
    'Wet Deposition',
    'Dry Deposition',
    'Surface Modification',
    'Substrate Treatment',
    'Aging Doping',
)


class DepositionStep(ArchiveSection):
    """
    A single step in a deposition routine.
    The step_type field classifies the step; name gives the specific
    technique (e.g. 'Spin Coating', 'Thermal Evaporation').
    """
    step_index = Quantity(
        type=int,
        description='Ordinal index of this step in the deposition sequence.',
        a_eln=ELNAnnotation(component='NumberEditQuantity'),
    )
    step_type = Quantity(
        type=STEP_TYPES,
        description='Classification of the deposition step.',
        a_eln=ELNAnnotation(component='EnumEditQuantity'),
    )
    name = Quantity(
        type=str,
        description='Specific technique name, e.g. "Spin Coating", '
                    '"Thermal Evaporation", "UV-Ozone Treatment".',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    color = Quantity(
        type=str,
        description='Color code for visual representation of this step.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    timestamp = Quantity(
        type=Datetime,
        description='Absolute date and time at which this step was executed (deposition start time).',
        a_eln=ELNAnnotation(component='DateTimeEditQuantity'),
    )
    duration = Quantity(
        type=float,
        unit='minute',
        description='Duration of this step.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='minute',
        ),
    )
    deposition_method = Quantity(
        type=str,
        description='Specific deposition technique method.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    atmosphere = Quantity(
        type=str,
        description='Atmosphere during the deposition step, e.g. "N2 glovebox", "ambient".',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    temperature = Quantity(
        type=float,
        unit='celsius',
        description='Substrate or process temperature during this step.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='celsius',
        ),
    )
    deposition_parameters = Quantity(
        type=str,
        description='Additional deposition parameters and settings.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    solution_volume = Quantity(
        type=float,
        unit='milliliter',
        description='Volume of solution deposited in this step.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='milliliter',
        ),
    )
    drying_method = Quantity(
        type=str,
        description='Method used for drying after deposition.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    annealing_start_time = Quantity(
        type=Datetime,
        description='Absolute date and time at which annealing started.',
        a_eln=ELNAnnotation(component='DateTimeEditQuantity'),
    )
    annealing_time = Quantity(
        type=float,
        unit='minute',
        description='Duration of annealing process.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='minute',
        ),
    )
    annealing_temperature = Quantity(
        type=float,
        unit='celsius',
        description='Temperature during annealing process.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='celsius',
        ),
    )
    annealing_atmosphere = Quantity(
        type=str,
        description='Atmosphere during annealing, e.g. "N2", "Air", "Vacuum".',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    notes = Quantity(
        type=str,
        description='Additional notes and observations about this step.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    material = SubSection(
        section_def=DepositedMaterial,
        description='Material or solution deposited in this step.',
    )


# ── DepositionRoutine — a Process Activity ───────────────────────────────────

class DepositionRoutine(Process, EntryData):
    """
    A deposition experiment that takes a SubstrateEntity as input and
    produces one or more PerovskiteSolarCellSample entries.

    Inheriting Process (→ Activity → BaseSection) gives:
      - name, lab_id, datetime, description   (BaseSection)
      - start_time, end_time                  (Activity — auto-derived from steps)
      - appears in /search/eln as a Process

    The substrate_entity reference drives the History tab on SubstrateEntity:
    every DepositionRoutine performed on a substrate appears there automatically.

    start_time and end_time are derived in normalize() from the minimum and
    maximum timestamps of the deposition steps — no manual entry needed.
    """
    m_def = Section(
        label='Deposition Routine',
        a_eln=dict(
            properties=dict(
                order=[
                    'name', 'lab_id', 'datetime',
                    'substrate_entity',
                    'start_time', 'end_time',
                    'steps',
                ]
            )
        ),
    )

    substrate_entity = Quantity(
        type=Reference(None),    # forward reference — resolved below
        description=(
            'The physical substrate on which this deposition was performed. '
            'Multiple solar cells fabricated in one routine share this substrate.'
        ),
        a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    )

    steps = SubSection(
        section_def=DepositionStep,
        repeats=True,
        description='Ordered list of deposition steps.',
    )

    def normalize(self, archive, logger):
        # Handle case where archive is None (in unit tests)
        if archive is not None:
            super().normalize(archive, logger)

        if not self.steps:
            return

        # Derive start_time and end_time from step timestamps
        timestamps = [
            s.timestamp for s in self.steps
            if s.timestamp is not None
        ]
        if timestamps:
            self.start_time = min(timestamps)
            self.end_time   = max(timestamps)
            if logger:
                logger.info(
                    f'DepositionRoutine: derived start={self.start_time}, '
                    f'end={self.end_time} from {len(timestamps)} step timestamps.'
                )

        # Ensure steps are sorted by step_index if indices are set
        indexed = [s for s in self.steps if s.step_index is not None]
        if len(indexed) == len(self.steps):
            self.steps = sorted(self.steps, key=lambda s: s.step_index)


# ── SubstrateEntity ───────────────────────────────────────────────────────────

class SubstrateEntity(CompositeSystem, EntryData):
    """
    A physical substrate as a laboratory entity.

    Inheriting CompositeSystem (→ System → Entity → BaseSection) gives:
      - lab_id, name, datetime           (from BaseSection via Entity)
      - elemental_composition            (from System)
      - History tab auto-populated       (from Entity membership)
        showing all PerovskiteSolarCellSample entries that reference this substrate

    The `substrate` subsection reuses the existing pvk database descriptive
    section so no properties are duplicated.
    Multiple solar cells can be fabricated on one substrate — each gets a
    reference to the same SubstrateEntity entry. The History tab on the
    SubstrateEntity then lists all of them automatically.
    """
    m_def = Section(
        label='Substrate',
        a_eln=dict(
            properties=dict(
                order=['name', 'lab_id', 'datetime', 'substrate']
            )
        ),
    )

    # Reuse the existing descriptive subsection verbatim
    substrate = SubSection(
        section_def=Substrate,
        description='Physical and chemical description of the substrate.',
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)


# Resolve forward reference on DepositionRoutine.substrate_entity
DepositionRoutine.substrate_entity.type = Reference(SubstrateEntity.m_def)


# ── Quenching / Drying Parameters ────────────────────────────────────────────


class GasQuenchingParameters(ArchiveSection):
    """Quenching parameters for gas-assisted drying/quenching."""

    gas_type = Quantity(
        type=str,
        description='Gas type, e.g. N2, Air, O2, Ar, He.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    pressure = Quantity(
        type=float,
        unit='Pa',
        description='Pressure value.',
        a_eln=ELNAnnotation(component='NumberEditQuantity'),
    )

    flow_rate = Quantity(
        type=float,
        description='Flow-rate value.',
        unit='Slm',
        a_eln=ELNAnnotation(component='NumberEditQuantity'),
    )

    height = Quantity(
        type=float,
        unit='centimeter',
        description='Nozzle-to-substrate distance.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
    )

    nozzle_width = Quantity(
        type=float,
        unit='millimeter',
        description='Nozzle width.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
    )

    nozzle_form = Quantity(
        type=str,
        description='Nozzle form, e.g. round, slit, wide.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )


class AntisolventQuenchingParameters(ArchiveSection):
    """Quenching parameters for antisolvent-assisted drying/quenching."""

    media = Quantity(
        type=str,
        description='Reference string for media, e.g. material:<id> or solution:<id>.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    deposition_method = Quantity(
        type=str,
        description='Antisolvent deposition method, e.g. drip, spray, bath.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    flow_rate = Quantity(
        type=float,
        unit='microliter/second',
        description='Antisolvent flow rate.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='microliter/second',
        ),
    )
    height = Quantity(
        type=float,
        unit='millimeter',
        description='Delivery height above substrate.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
    )

    volume = Quantity(
        type=float,
        unit='microliter',
        description='Antisolvent volume.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='microliter',
        ),
    )


class VacuumQuenchingParameters(ArchiveSection):
    """Quenching parameters for vacuum-assisted drying/quenching."""

    height = Quantity(
        type=float,
        unit='millimeter',
        description='Gap height.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
    )

    base_area = Quantity(
        type=float,
        unit='centimeter ** 2',
        description='Vacuum base area.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='centimeter ** 2',
        ),
    )

    pump_model = Quantity(
        type=str,
        description='Pump model identifier.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    dead_volume = Quantity(
        type=float,
        unit='meter ** 3',
        description='Dead volume in the vacuum setup.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='meter ** 3',
        ),
    )
    evacuation_time = Quantity(
        type=float,
        unit='second',
        description='Evacuation time.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='second',
        ),
    )


class QuenchingParameters(ArchiveSection):
    """Unified quenching/drying parameters from the process dialog."""

    m_def = Section(
        label='Quenching Parameters',
        a_eln=dict(
            properties=dict(
                order=[
                    'quenching_type',
                    'gas',
                    'antisolvent',
                    'vacuum',
                ]
            )
        ),
    )

    gas = SubSection(
        section_def=GasQuenchingParameters,
        description='Gas-mode quenching parameters.',
    )
    antisolvent = SubSection(
        section_def=AntisolventQuenchingParameters,
        description='Antisolvent-mode quenching parameters.',
    )
    vacuum = SubSection(
        section_def=VacuumQuenchingParameters,
        description='Vacuum-mode quenching parameters.',
    )


class ExtendedPerovskiteDeposition(PerovskiteDeposition):
    """
    Extends the pvk database PerovskiteDeposition with quenching_parameters.
    All existing quantities and subsections are inherited unchanged.
    """
    m_def = Section()

    quenching_parameters = SubSection(
        section_def=QuenchingParameters,
        description='Quenching step applied after perovskite deposition.',
    )


class PerovskiteSolarCellSample(PerovskiteSolarCell, Entity, EntryData):
    m_def = Section(
        label='Perovskite Solar Cell Sample',
        a_eln=dict(
            properties=dict(
                order=[
                    'name', 'lab_id', 'datetime',
                    'substrate_entity',
                    'deposition_routine',
                ]
            )
        ),
    )

    # Shadow the upstream quantity with the extended type.
    # NOMAD resolves quantities by MRO — this declaration takes
    # precedence over the one inherited from PerovskiteSolarCell.
    perovskite_deposition = SubSection(
        section_def=ExtendedPerovskiteDeposition,
        description='Perovskite deposition parameters including quenching.',
    )


    substrate_entity = Quantity(
        type=Reference(SubstrateEntity.m_def),
        description='The physical substrate this cell was fabricated on.',
        a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    )

    deposition_routine = Quantity(
        type=Reference(DepositionRoutine.m_def),
        description=(
            'The DepositionRoutine Activity that produced this solar cell. '
            'Links the cell to its full fabrication history.'
        ),
        a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)

        # Propagate substrate from entity → pvk substrate subsection
        if self.substrate_entity is not None:
            if self.substrate_entity.substrate is not None:
                self.substrate = self.substrate_entity.substrate
                logger.info(
                    f'Propagated substrate properties from '
                    f'{self.substrate_entity.lab_id} into sample.substrate'
                )

        # Propagate substrate_entity from deposition_routine if not set directly
        if (self.substrate_entity is None
                and self.deposition_routine is not None
                and self.deposition_routine.substrate_entity is not None):
            self.substrate_entity = self.deposition_routine.substrate_entity
            logger.info(
                'Propagated substrate_entity from deposition_routine '
                f'{self.deposition_routine.lab_id}'
            )

        self._populate_jv_from_measurements(archive, logger)

    def _populate_jv_from_measurements(self, archive, logger):
        """
        Automatically finds and populates JV data from measurements that reference this sample.
        Uses NOMAD search to find JVMeasurement, EQEMeasurement, and MPPTracking entries.
        """
        if archive is None or archive.m_context is None:
            return

        if not hasattr(archive, 'metadata') or not hasattr(archive.metadata, 'entry_id'):
            return

        try:
            # Search for all entries that reference this sample
            results = search(
                owner='visible',
                query={
                    'entry_references.target_entry_id': archive.metadata.entry_id,
                },
                pagination=MetadataPagination(page_size=100),
                required='entry_id,upload_id',
            )
        except Exception as e:
            logger.warning(f'Failed to search for linked measurements: {e}')
            return

        if not results.data:
            logger.info('No measurements found referencing this sample.')
            return

        # Initialize jv section if it doesn't exist
        if not self.jv:
            from perovskite_solar_cell_database.schema_sections.jv import JV
            self.jv = JV()

        jv_count = 0
        eqe_count = 0
        mppt_count = 0

        # Process each found entry
        for hit in results.data:
            try:
                ref_archive = archive.m_context.load_archive(
                    hit.entry_id, hit.upload_id, None
                )
                entry = ref_archive.data
                if entry is None:
                    continue

                # Process JVMeasurement entries
                if isinstance(entry, JVMeasurement):
                    logger.info(f'Found JVMeasurement: {getattr(entry, "name", hit.entry_id)}')
                    self._populate_from_jv(entry, logger)
                    jv_count += 1

                # Process EQEMeasurement entries (only if JV fields not set)
                elif isinstance(entry, EQEMeasurement):
                    logger.info(f'Found EQEMeasurement: {getattr(entry, "name", hit.entry_id)}')
                    self._populate_from_eqe(entry, logger)
                    eqe_count += 1

                # Process MPPTracking entries (only if JV fields not set)
                elif isinstance(entry, MPPTracking):
                    logger.info(f'Found MPPTracking: {getattr(entry, "name", hit.entry_id)}')
                    self._populate_from_mppt(entry, logger)
                    mppt_count += 1

            except Exception as e:
                logger.warning(f'Could not load referenced entry {hit.entry_id}: {e}')

        logger.info(
            f'Populated JV data from measurements: '
            f'{jv_count} JV, {eqe_count} EQE, {mppt_count} MPPT'
        )

    def _populate_from_jv(self, measurement, logger):
        """Populate JV section from JVMeasurement."""
        jv = self.jv

        # Populate basic parameters
        if hasattr(measurement, 'open_circuit_voltage') and measurement.open_circuit_voltage is not None:
            jv.default_Voc = measurement.open_circuit_voltage
        if hasattr(measurement, 'short_circuit_current_density') and measurement.short_circuit_current_density is not None:
            jv.default_Jsc = measurement.short_circuit_current_density
        if hasattr(measurement, 'fill_factor') and measurement.fill_factor is not None:
            jv.default_FF = measurement.fill_factor
        if hasattr(measurement, 'efficiency') and measurement.efficiency is not None:
            jv.default_PCE = measurement.efficiency

        # Populate measurement conditions
        if hasattr(measurement, 'light_intensity') and measurement.light_intensity is not None:
            jv.light_intensity = measurement.light_intensity
        if hasattr(measurement, 'temperature') and measurement.temperature is not None:
            jv.test_temperature = measurement.temperature

        # Populate JV curves if available
        if hasattr(measurement, 'jv_curve') and measurement.jv_curve:
            from perovskite_solar_cell_database.schema_sections.jv import JVcurve
            if not jv.jv_curve:
                jv.jv_curve = []
            for curve in measurement.jv_curve:
                if hasattr(curve, 'voltage') and hasattr(curve, 'current_density'):
                    jv_set = JVcurve(
                        cell_name=getattr(curve, 'cell_name', 'Cell'),
                        voltage=curve.voltage,
                        current_density=curve.current_density,
                    )
                    jv.jv_curve.append(jv_set)

    def _populate_from_eqe(self, measurement, logger):
        """Populate JV section from EQEMeasurement (limited fields)."""
        jv = self.jv
        # Only populate if not already set from JV measurement
        if hasattr(measurement, 'temperature') and measurement.temperature is not None and not jv.test_temperature:
            jv.test_temperature = measurement.temperature
        if hasattr(measurement, 'light_intensity') and measurement.light_intensity is not None and not jv.light_intensity:
            jv.light_intensity = measurement.light_intensity

    def _populate_from_mppt(self, measurement, logger):
        """Populate JV section from MPPTracking (limited fields)."""
        jv = self.jv
        # Only populate if not already set from JV measurement
        if hasattr(measurement, 'efficiency') and measurement.efficiency is not None and not jv.default_PCE:
            jv.default_PCE = measurement.efficiency


m_package.__init_metainfo__()