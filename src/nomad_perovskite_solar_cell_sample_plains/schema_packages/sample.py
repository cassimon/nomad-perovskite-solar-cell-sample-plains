import datetime
import math

from nomad.app.v1.models import MetadataPagination
from nomad.config import config
from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.datamodel.metainfo.basesections import CompositeSystem,CompositeSystemReference, Process, ProcessStep
from nomad.datamodel.metainfo.plot import PlotSection, PlotlyFigure
from nomad.metainfo import Datetime, MEnum, Quantity, Reference, SchemaPackage, Section, SubSection
from nomad.search import search, MetadataRequired

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
from nomad_perovskite_solar_cell_sample_plains.utils import create_cell_stack_figure

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
    """
    One step of a `DepositionRoutine`.

    This is a plain `ProcessStep` in the NOMAD ELN workflow sense: the step is
    positioned in time by the inherited `start_time` and `duration`, which is
    what `Process.normalize` and `ActivityStep.to_task` (and therefore
    `archive.workflow2.tasks`) build the workflow from. `duration` is the time
    until the *next* step starts -- for the last step, the time until the end of
    the routine -- not the time the sample spent on the hotplate; the latter is
    `annealing_time`.
    """

    m_def = Section(label='Deposition Step')

    step_index = Quantity(type=int, a_eln=ELNAnnotation(component='NumberEditQuantity'))
    step_type = Quantity(
        type=STEP_TYPES,
        a_eln=ELNAnnotation(component='EnumEditQuantity'),
    )
    color = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    # Redeclared only to carry the `timestamp` alias: archives uploaded before
    # this schema moved onto the canonical workflow field still carry the step
    # start as `timestamp`, and the alias keeps them readable.
    start_time = Quantity(
        type=Datetime,
        aliases=['timestamp'],
        description='When this step was started.',
        a_eln=ELNAnnotation(component='DateTimeEditQuantity', label='starting time'),
    )
    duration = Quantity(
        type=float,
        unit='minute',
        description='Time from the start of this step until the start of the next one.',
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
    """
    The sequence of `DepositionStep`s a substrate went through.

    `datetime` is the start of the routine and `end_time` its end -- the two
    quantities `Process` already defines; there is no separate `start_time` on a
    `Process` (only its *steps* have one), which is why the ELN order below and
    the normalization use `datetime`.
    """

    m_def = Section(
        label='Deposition Routine',
        a_eln=dict(
            properties=dict(
                order=['name', 'lab_id', 'datetime', 'end_time', 'samples', 'steps']
            )
        ),
    )

    steps = SubSection(section_def=DepositionStep, repeats=True)

    def normalize(self, archive, logger):
        # Order the steps *before* the base normalization runs: `Activity.normalize`
        # turns `self.steps` into `archive.workflow2.tasks` in list order, so an
        # unsorted list would produce an out-of-order workflow.
        indexed = [step for step in self.steps if step.step_index is not None]
        if self.steps and len(indexed) == len(self.steps):
            self.steps = sorted(self.steps, key=lambda step: step.step_index)

        start_times = [
            step.start_time for step in self.steps if step.start_time is not None
        ]
        if start_times and self.datetime is None:
            self.datetime = min(start_times)

        # `Process.normalize` back-fills any missing step start_time from
        # `datetime` + the preceding durations, and sets `end_time` from the last
        # step's end when it is still unset -- so both only need seeding here.
        if archive is not None:
            super().normalize(archive, logger)

        if self.end_time is None and start_times:
            last = self.steps[-1]
            end = last.start_time if last.start_time is not None else max(start_times)
            if last.duration is not None:
                end = end + datetime.timedelta(
                    seconds=float(last.duration.to('second').magnitude)
                )
            self.end_time = end


class GasQuenchingParameters(ArchiveSection):
    gas_type = Quantity(type=str, a_eln=ELNAnnotation(component='StringEditQuantity'))
    pressure = Quantity(type=float, unit='Pa', a_eln=ELNAnnotation(component='NumberEditQuantity'))
    flow_rate = Quantity(
        type=float,
        unit='liter/minute',
        a_eln=ELNAnnotation(component='NumberEditQuantity'),
    )
    velocity = Quantity(
        type=float,
        unit='meter/second',
        description='Gas velocity at the nozzle, when the flow is specified as a velocity rather than a volumetric flow rate.',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='meter/second'),
    )
    height = Quantity(
        type=float,
        unit='millimeter',
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
    media_pubchem_cid = Quantity(
        type=str,
        description='PubChem CID of the antisolvent, when the lab software resolved one.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )
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
        a_eln=dict(properties=dict(order=['time_until_start', 'gas', 'antisolvent', 'vacuum'])),
    )

    time_until_start = Quantity(
        type=float,
        unit='second',
        description='Time from the start of the deposition step until the quenching was applied.',
        a_eln=ELNAnnotation(component='NumberEditQuantity', defaultDisplayUnit='second'),
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

            try:
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
            except (TypeError, ValueError) as e:
                logger.warning(
                    'Could not create cell stack figure.',
                    exc_info=e,
                )

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
                required=MetadataRequired(
        include=['entry_id', 'upload_id']
    ),
            )
        except Exception as e:
            if logger:
                logger.warning(f'Failed to search for linked measurements: {e}')
            return

        if not results.data:
            return

        jv_measurements = []
        eqe_measurements = []
        mppt_measurements = []

        for hit in results.data:
            try:
                ref_archive = archive.m_context.load_archive(hit.entry_id, hit.upload_id, None)
                entry = ref_archive.data
                if entry is None:
                    continue

                if isinstance(entry, JVMeasurement):
                    jv_measurements.append(entry)
                elif isinstance(entry, EQEMeasurement):
                    eqe_measurements.append(entry)
                elif isinstance(entry, MPPTracking):
                    mppt_measurements.append(entry)
            except Exception as e:
                if logger:
                    logger.warning(f'Could not load referenced entry {hit.entry_id}: {e}')

        if not (jv_measurements or eqe_measurements or mppt_measurements):
            return

        if not self.jv:
            from perovskite_solar_cell_database.schema_sections.jv import JV as JVSection

            self.jv = JVSection()

        self._populate_from_jv(jv_measurements, logger)
        for measurement in eqe_measurements:
            self._populate_from_eqe(measurement)
        for measurement in mppt_measurements:
            self._populate_from_mppt(measurement)

    def _populate_from_jv(self, measurements, logger=None):
        """
        Derives the default JV parameters from every linked JV measurement.

        The measured values live on the repeating `jv_curve` subsections (one per cell
        and scan direction), not on the JVMeasurement itself. The device defaults are
        taken from the single best-performing curve -- highest efficiency, ignoring dark
        curves -- so that Voc/Jsc/FF/PCE all describe the same curve instead of being
        mixed across measurements.
        """
        from perovskite_solar_cell_database.schema_sections.jv import JVcurve

        jv = self.jv

        best_curve = None
        curves = []

        for measurement in measurements:
            for curve in measurement.jv_curve or []:
                if curve.voltage is not None and curve.current_density is not None:
                    curves.append(
                        JVcurve(
                            cell_name=getattr(curve, 'cell_name', None) or 'Cell',
                            voltage=curve.voltage,
                            current_density=curve.current_density,
                        )
                    )

                if getattr(curve, 'dark', False) or curve.efficiency is None:
                    continue
                if best_curve is None or curve.efficiency > best_curve.efficiency:
                    best_curve = curve

        # Rebuild rather than append: normalize() runs repeatedly on the same archive.
        if curves:
            jv.jv_curve = curves

        self._populate_scan_directions(measurements, best_curve)
        self._populate_jv_settings(measurements)

        if best_curve is None:
            if logger and measurements:
                logger.info(
                    'No JV curve with an efficiency found; '
                    'leaving the default JV parameters unset.'
                )
            return

        jv.default_PCE = best_curve.efficiency
        jv.default_PCE_scan_direction = self._scan_direction(best_curve)
        if best_curve.open_circuit_voltage is not None:
            jv.default_Voc = best_curve.open_circuit_voltage
            jv.default_Voc_scan_direction = self._scan_direction(best_curve)
        if best_curve.short_circuit_current_density is not None:
            jv.default_Jsc = best_curve.short_circuit_current_density
            jv.default_Jsc_scan_direction = self._scan_direction(best_curve)
        if best_curve.fill_factor is not None:
            jv.default_FF = best_curve.fill_factor
            jv.default_FF_scan_direction = self._scan_direction(best_curve)
        if best_curve.light_intensity is not None:
            jv.light_intensity = best_curve.light_intensity

    @staticmethod
    def _scan_direction(curve):
        """The instrument's 'FW'/'RV' as the perovskite database spells it.

        The database's own enum suggestions are 'Forward' and 'Reversed'.
        """
        name = (getattr(curve, 'cell_name', None) or '').strip().upper()
        if name.startswith('FW') or 'FORWARD' in name:
            return 'Forward'
        if name.startswith('RV') or 'REVERSE' in name:
            return 'Reversed'
        return None

    def _populate_scan_directions(self, measurements, best_curve):
        """Map the per-scan curves onto the database's forward_/reverse_scan_* fields.

        The CHOSE summary table states Voc, Jsc, V_MPP, J_MPP, FF, Eff, Rs and R//
        separately for the forward and reverse scan, and the perovskite database
        has a field for each -- so nothing needs to be averaged away.
        """
        jv = self.jv
        prefixes = {'Forward': 'forward_scan', 'Reversed': 'reverse_scan'}
        fields = {
            'Voc': 'open_circuit_voltage',
            'Jsc': 'short_circuit_current_density',
            'FF': 'fill_factor',
            'PCE': 'efficiency',
            'Vmp': 'potential_at_maximum_power_point',
            'Jmp': 'current_density_at_maximun_power_point',
            'series_resistance': 'series_resistance',
            'shunt_resistance': 'shunt_resistance',
        }

        seen = {}
        for measurement in measurements:
            for curve in measurement.jv_curve or []:
                if getattr(curve, 'dark', False):
                    continue
                direction = self._scan_direction(curve)
                if direction is None:
                    continue
                # Keep the best scan per direction, so the FW/RV pair is comparable.
                previous = seen.get(direction)
                if (
                    previous is None
                    or curve.efficiency is not None
                    and (previous.efficiency is None or curve.efficiency > previous.efficiency)
                ):
                    seen[direction] = curve

        for direction, curve in seen.items():
            prefix = prefixes[direction]
            for suffix, attribute in fields.items():
                value = getattr(curve, attribute, None)
                if value is None:
                    continue
                setattr(jv, f'{prefix}_{suffix}', value)

        forward = seen.get('Forward')
        reverse = seen.get('Reversed')
        if (
            forward is not None
            and reverse is not None
            and forward.efficiency is not None
            and reverse.efficiency is not None
            and reverse.efficiency
        ):
            # As defined by the perovskite database: (PCE_rev - PCE_fwd) / PCE_rev.
            jv.hysteresis_index = float(
                (reverse.efficiency - forward.efficiency) / reverse.efficiency
            )

    def _populate_jv_settings(self, measurements):
        """Carry the instrument's scan settings into the database's JV section."""
        jv = self.jv
        for measurement in measurements:
            settings = getattr(measurement, 'settings', None)
            if settings is None:
                continue
            if settings.scan_rate is not None and jv.scan_speed is None:
                jv.scan_speed = settings.scan_rate
            if settings.voltage_step is not None and jv.scan_voltage_step is None:
                jv.scan_voltage_step = settings.voltage_step
            if getattr(measurement, 'active_area', None) is not None and jv.light_mask_area is None:
                jv.light_mask_area = measurement.active_area

    def _populate_from_eqe(self, measurement):
        """Populate the sample's `eqe` section from an EQE measurement.

        This used to probe `measurement.temperature` / `.light_intensity`, neither
        of which exists on baseclasses' `EQEMeasurement` -- so both `hasattr`
        checks were always false and nothing was ever written.
        """
        from perovskite_solar_cell_database.schema_sections.eqe import EQE as EQESection

        jv = self.jv

        temperature = getattr(measurement, 'temperature', None)
        if temperature is not None and not jv.test_temperature:
            jv.test_temperature = temperature

        data = (measurement.eqe_data or [None])[0]
        if data is None:
            return

        if not self.eqe:
            self.eqe = EQESection()
        eqe = self.eqe
        eqe.measured = True

        for attribute in (
            'bandgap_eqe',
            'integrated_jsc',
            'integrated_j0rad',
            'voc_rad',
            'urbach_energy',
            'eqe_array',
            'photon_energy_array',
            'wavelength_array',
            'raw_eqe_array',
            'raw_photon_energy_array',
            'raw_wavelength_array',
            'light_bias',
        ):
            value = getattr(data, attribute, None)
            if value is not None and eqe.m_def.all_properties.get(attribute) is not None:
                setattr(eqe, attribute, value)

    def _populate_from_mppt(self, measurement):
        """Populate the sample's `stability` and `stabilised` sections from an MPP track."""
        from perovskite_solar_cell_database.schema_sections.stability import (
            Stability as StabilitySection,
        )
        from perovskite_solar_cell_database.schema_sections.stabilised import (
            Stabilised as StabilisedSection,
        )

        jv = self.jv

        # MPPTracking.efficiency is the efficiency *over time*, not a scalar; the
        # stabilised value is the last valid point of the track.
        efficiency = measurement.efficiency
        stabilised = []
        if efficiency is not None and len(efficiency):
            stabilised = [
                float(value) for value in efficiency if math.isfinite(float(value))
            ]

        if stabilised:
            if not self.stabilised:
                self.stabilised = StabilisedSection()
            self.stabilised.performance_measured = True
            self.stabilised.performance_PCE = stabilised[-1]

            # Only a fallback: a JV-derived PCE always wins. Note `is not None`
            # rather than a truth test, so a legitimately measured 0 % PCE is kept.
            if jv.default_PCE is None:
                jv.default_PCE = stabilised[-1]

        figures = (measurement.results or [None])[0]
        time = measurement.time

        if figures is None and time is None:
            return

        if not self.stability:
            self.stability = StabilitySection()
        stability = self.stability
        stability.measured = True

        if time is not None and len(time):
            stability.time_total_exposure = time[-1]
        if stabilised:
            stability.PCE_end_of_experiment = stabilised[-1]
        if figures is not None and getattr(figures, 'T80', None) is not None:
            stability.PCE_T80 = figures.T80


m_package.__init_metainfo__()
