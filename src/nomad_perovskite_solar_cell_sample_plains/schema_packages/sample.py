from nomad.app.v1.models import MetadataPagination
from nomad.config import config
from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.datamodel.metainfo.basesections import CompositeSystem,CompositeSystemReference, Process, ProcessStep
from nomad.datamodel.metainfo.plot import PlotSection, PlotlyFigure
from nomad.metainfo import Datetime, MEnum, Quantity, Reference, SchemaPackage, Section, SubSection
from nomad.search import search

from baseclasses.solar_energy.eqemeasurement import EQEMeasurement
from baseclasses.solar_energy.jvmeasurement import JVMeasurement
from baseclasses.solar_energy.mpp_tracking import MPPTracking
from perovskite_solar_cell_database.schema import PerovskiteDeposition, Substrate
from perovskite_solar_cell_database.schema_sections import (
    Add,
    Backcontact,
    Cell,
    EQE,
    ETL,
    HTL,
    JV,
    Encapsulation,
    Module,
    Outdoor,
    Perovskite,
    Ref,
    Stability,
    Stabilised,
)
from perovskite_solar_cell_database.utils import create_cell_stack_figure

configuration = config.get_plugin_entry_point(
    'nomad_perovskite_solar_cell_sample_plains.schema_packages:schema_package_entry_point'
)

m_package = SchemaPackage()


class ImageFile(ArchiveSection):
    image = Quantity(
        type=str,
        description='An image file attached to this entry.',
        a_eln=ELNAnnotation(component='FileEditQuantity', label='Image file'),
        a_browser=dict(adaptor='RawFileAdaptor'),
    )
    caption = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))


class DocumentFile(ArchiveSection):
    document = Quantity(
        type=str,
        description='A PDF or document file attached to this entry.',
        a_eln=ELNAnnotation(component='FileEditQuantity', label='Document (PDF)'),
        a_browser=dict(adaptor='RawFileAdaptor'),
    )
    title = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))


class DepositedMaterial(ArchiveSection):
    name = Quantity(
        type=str,
        description='Name of the material or solution.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
    concentration = Quantity(
        type=float,
        unit='mol/l',
        description='Concentration of the solution if applicable.',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='mol/l'),
    )
    supplier = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))


STEP_TYPES = MEnum(
    'Wet Deposition',
    'Dry Deposition',
    'Surface Modification',
    'Substrate Treatment',
    'Aging Doping',
)


class DepositionStep(ProcessStep):
    m_def = Section(label='Deposition Step')

    step_index = Quantity(type=int, a_eln=ELNAnnotation(component='NumberEditQuantity'))
    step_type = Quantity(
        type=STEP_TYPES,
        a_eln=ELNAnnotation(component='EnumEditQuantity'),
    )
    name = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    color = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    timestamp = Quantity(type=Datetime, a_eln=ELNAnnotation(component='DateTimeEditQuantity'))
    duration = Quantity(
        type=float,
        unit='minute',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='minute'),
    )
    deposition_method = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    atmosphere = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    temperature = Quantity(
        type=float,
        unit='celsius',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='celsius'),
    )
    deposition_parameters = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    solution_volume = Quantity(
        type=float,
        unit='milliliter',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='milliliter'),
    )
    drying_method = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    annealing_start_time = Quantity(type=Datetime, a_eln=ELNAnnotation(component='DateTimeEditQuantity'))
    annealing_time = Quantity(
        type=float,
        unit='minute',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='minute'),
    )
    annealing_temperature = Quantity(
        type=float,
        unit='celsius',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='celsius'),
    )
    annealing_atmosphere = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    notes = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    material = SubSection(section_def=DepositedMaterial)





class DepositionRoutine(Process):
    m_def = Section(
        label='Deposition Routine',
        a_eln=dict(
            properties=dict(
                order=['name', 'lab_id', 'datetime', 'substrate_entity', 'samples', 'start_time', 'end_time', 'steps']
            )
        ),
    )

    # substrate_entity = Quantity(
    #     type=Reference(SubstrateEntity.m_def),
    #     description='Substrate used by this routine.',
    #     a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    # )

    steps = SubSection(section_def=DepositionStep, repeats=True)

    def normalize(self, archive, logger):
        if archive is not None:
            super().normalize(archive, logger)

        if not self.steps:
            return

        timestamps = [step.timestamp for step in self.steps if step.timestamp is not None]
        if timestamps:
            self.start_time = min(timestamps)
            self.end_time = max(timestamps)

        indexed = [step for step in self.steps if step.step_index is not None]
        if len(indexed) == len(self.steps):
            self.steps = sorted(self.steps, key=lambda step: step.step_index)


class GasQuenchingParameters(ArchiveSection):
    gas_type = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    pressure = Quantity(type=float, unit='Pa', a_eln=ELNAnnotation(component='NumberEditQuantity'))
    flow_rate = Quantity(
        type=float,
        unit='liter/minute',
        a_eln=ELNAnnotation(component='NumberEditQuantity'),
    )
    height = Quantity(
        type=float,
        unit='centimeter',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='millimeter'),
    )
    nozzle_width = Quantity(
        type=float,
        unit='millimeter',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='millimeter'),
    )
    nozzle_form = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))


class AntisolventQuenchingParameters(ArchiveSection):
    media = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    deposition_method = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    flow_rate = Quantity(
        type=float,
        unit='microliter/second',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='microliter/second'),
    )
    height = Quantity(
        type=float,
        unit='millimeter',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='millimeter'),
    )
    volume = Quantity(
        type=float,
        unit='microliter',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='microliter'),
    )


class VacuumQuenchingParameters(ArchiveSection):
    height = Quantity(
        type=float,
        unit='millimeter',
        description='Gap height.',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='millimeter'),
    )
    base_area = Quantity(
        type=float,
        unit='centimeter ** 2',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='centimeter ** 2'),
    )
    pump_model = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    dead_volume = Quantity(
        type=float,
        unit='meter ** 3',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='meter ** 3'),
    )
    evacuation_time = Quantity(
        type=float,
        unit='second',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='second'),
    )


class QuenchingParameters(ArchiveSection):
    m_def = Section(
        label='Quenching Parameters',
        a_eln=dict(properties=dict(order=['gas', 'antisolvent', 'vacuum'])),
    )

    gas = SubSection(section_def=GasQuenchingParameters)
    antisolvent = SubSection(section_def=AntisolventQuenchingParameters)
    vacuum = SubSection(section_def=VacuumQuenchingParameters)


class ExtendedPerovskiteDeposition(PerovskiteDeposition):
    m_def = Section()

    quenching_parameters = SubSection(
        section_def=QuenchingParameters,
        description='Quenching step applied after perovskite deposition.',
    )

class SubstrateSample(CompositeSystem):
    m_def = Section(
        label='Substrate',
        a_eln=dict(properties=dict(order=['name', 'lab_id', 'datetime', 'substrate'])),
    )

    substrate = SubSection(
        section_def=Substrate,
        description='Physical and chemical description of the substrate.',
    )

    cell_areas = SubSection(
        section_def=CompositeSystemReference,
        repeats=True,
        description='Areas of the substrate where solar cells are located.',
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)

class PerovskiteSolarCellSampleArea(CompositeSystem, PlotSection):
    m_def = Section(
        label='Perovskite Solar Cell Sample',
        a_eln=dict(
            properties=dict(order=['name', 'lab_id', 'datetime', 'substrate_entity', 'deposition_routine'])
        ),
    )

    # substrate_entity = Quantity(
    #     type=Reference(SubstrateEntity.m_def),
    #     description='The physical substrate this cell was fabricated on.',
    #     a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    # )
    # deposition_routine = Quantity(
    #     type=Reference(DepositionRoutine.m_def),
    #     description='The DepositionRoutine activity that produced this solar cell.',
    #     a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    # )

    ref = SubSection(section_def=Ref)
    cell = SubSection(section_def=Cell)
    module = SubSection(section_def=Module)
    substrate = SubSection(section_def=Substrate)
    etl = SubSection(section_def=ETL)
    perovskite = SubSection(section_def=Perovskite)
    perovskite_deposition = SubSection(section_def=ExtendedPerovskiteDeposition)
    htl = SubSection(section_def=HTL)
    backcontact = SubSection(section_def=Backcontact)
    add = SubSection(section_def=Add)
    encapsulation = SubSection(section_def=Encapsulation)
    jv = SubSection(section_def=JV)
    stabilised = SubSection(section_def=Stabilised)
    eqe = SubSection(section_def=EQE)
    stability = SubSection(section_def=Stability)
    outdoor = SubSection(section_def=Outdoor)

    images = SubSection(section_def=ImageFile, repeats=True)
    documents = SubSection(section_def=DocumentFile, repeats=True)

    def normalize(self, archive, logger):
        super().normalize(archive, logger)

        if self.cell is not None and self.cell.stack_sequence:
            layers = self.cell.stack_sequence.split(' | ')
            thicknesses = []
            colors = []
            gray_shades = ['#D3D3D3', '#BEBEBE', '#A9A9A9', '#909090']
            gray_index = 0

            for i, layer in enumerate(layers):
                if i == 0:
                    thicknesses.append(1.0)
                    colors.append('lightblue')
                elif 'Perovskite' in layer:
                    thicknesses.append(0.5)
                    colors.append('red')
                elif i == len(layers) - 1:
                    thicknesses.append(0.1)
                    colors.append('orange')
                else:
                    thicknesses.append(0.1)
                    colors.append(gray_shades[gray_index % len(gray_shades)])
                    gray_index += 1

            efficiency = self.jv.default_PCE if self.jv else None
            voc = self.jv.default_Voc if self.jv else None
            jsc = self.jv.default_Jsc if self.jv else None
            ff = self.jv.default_FF if self.jv else None

            fig = create_cell_stack_figure(
                layers=layers,
                thicknesses=thicknesses,
                colors=colors,
                efficiency=efficiency,
                voc=voc,
                jsc=jsc,
                ff=ff,
                x_min=0,
                x_max=10,
                y_min=0,
                y_max=10,
            )
            self.figures = [PlotlyFigure(figure=fig.to_plotly_json())]

        self._populate_jv_from_measurements(archive, logger)

    def _populate_jv_from_measurements(self, archive, logger):
        if archive is None or archive.m_context is None:
            return

        if not hasattr(archive, 'metadata') or not hasattr(archive.metadata, 'entry_id'):
            return

        try:
            results = search(
                owner='visible',
                query={'entry_references.target_entry_id': archive.metadata.entry_id},
                pagination=MetadataPagination(page_size=100),
                required=['entry_id', 'upload_id'],
            )
        except Exception as e:
            if logger:
                logger.warning(f'Failed to search for linked measurements: {e}')
            return

        if not results.data:
            return

        if not self.jv:
            from perovskite_solar_cell_database.schema_sections.jv import JV as JVSection

            self.jv = JVSection()

        for hit in results.data:
            try:
                ref_archive = archive.m_context.load_archive(hit.entry_id, hit.upload_id, None)
                entry = ref_archive.data
                if entry is None:
                    continue

                if isinstance(entry, JVMeasurement):
                    self._populate_from_jv(entry)
                elif isinstance(entry, EQEMeasurement):
                    self._populate_from_eqe(entry)
                elif isinstance(entry, MPPTracking):
                    self._populate_from_mppt(entry)
            except Exception as e:
                if logger:
                    logger.warning(f'Could not load referenced entry {hit.entry_id}: {e}')

    def _populate_from_jv(self, measurement):
        jv = self.jv
        if hasattr(measurement, 'open_circuit_voltage') and measurement.open_circuit_voltage is not None:
            jv.default_Voc = measurement.open_circuit_voltage
        if (
            hasattr(measurement, 'short_circuit_current_density')
            and measurement.short_circuit_current_density is not None
        ):
            jv.default_Jsc = measurement.short_circuit_current_density
        if hasattr(measurement, 'fill_factor') and measurement.fill_factor is not None:
            jv.default_FF = measurement.fill_factor
        if hasattr(measurement, 'efficiency') and measurement.efficiency is not None:
            jv.default_PCE = measurement.efficiency
        if hasattr(measurement, 'light_intensity') and measurement.light_intensity is not None:
            jv.light_intensity = measurement.light_intensity
        if hasattr(measurement, 'temperature') and measurement.temperature is not None:
            jv.test_temperature = measurement.temperature

        if hasattr(measurement, 'jv_curve') and measurement.jv_curve:
            from perovskite_solar_cell_database.schema_sections.jv import JVcurve

            if not jv.jv_curve:
                jv.jv_curve = []
            for curve in measurement.jv_curve:
                if hasattr(curve, 'voltage') and hasattr(curve, 'current_density'):
                    jv.jv_curve.append(
                        JVcurve(
                            cell_name=getattr(curve, 'cell_name', 'Cell'),
                            voltage=curve.voltage,
                            current_density=curve.current_density,
                        )
                    )

    def _populate_from_eqe(self, measurement):
        jv = self.jv
        if hasattr(measurement, 'temperature') and measurement.temperature is not None and not jv.test_temperature:
            jv.test_temperature = measurement.temperature
        if hasattr(measurement, 'light_intensity') and measurement.light_intensity is not None and not jv.light_intensity:
            jv.light_intensity = measurement.light_intensity

    def _populate_from_mppt(self, measurement):
        jv = self.jv
        if hasattr(measurement, 'efficiency') and measurement.efficiency is not None and not jv.default_PCE:
            jv.default_PCE = measurement.efficiency


m_package.__init_metainfo__()
