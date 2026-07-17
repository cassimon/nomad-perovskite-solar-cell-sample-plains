import copy
import datetime
import math
from typing import NamedTuple

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
from baseclasses.solar_energy.uvvismeasurement import UVvisMeasurement
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
from nomad_perovskite_solar_cell_sample_plains.utils import (
    create_cell_stack_figure,
    create_dark_jv_overview_figure,
    create_eqe_overview_figure,
    create_jv_overview_figure,
    create_stability_overview_figure,
    create_uvvis_overview_figure,
)

configuration = config.get_plugin_entry_point(
    'nomad_perovskite_solar_cell_sample_plains.schema_packages:schema_package_entry_point'
)

m_package = SchemaPackage()

# The figure labels. A `SubstrateSample` mirrors its devices' figures and tells
# them apart by these, so they are named once, here.
STACK_FIGURE_LABEL = 'Device stack'
JV_OVERVIEW_LABEL = 'JV curves (all measurements)'
DARK_JV_OVERVIEW_LABEL = 'Dark JV curves (all measurements)'
STABILITY_OVERVIEW_LABEL = 'MPP tracking (all measurements)'
EQE_OVERVIEW_LABEL = 'EQE (all measurements)'
UVVIS_OVERVIEW_LABEL = 'UV-Vis (all films)'


class LoadedMeasurements(NamedTuple):
    """The measurement entries that reference a sample, sorted by kind.

    They are loaded once, to derive the sample's JV/EQE/stability sections; the
    overview figures are then drawn from the same objects rather than loading
    every archive a second time.
    """

    jv: list
    eqe: list
    mppt: list

    @classmethod
    def none(cls):
        return cls([], [], [])

    def __bool__(self):
        return bool(self.jv or self.eqe or self.mppt)


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

class SubstrateInfo(Substrate):
    """The database's `Substrate`, minus its results side effect.

    `Substrate.normalize` calls `add_solar_cell(archive)` unconditionally, which
    creates `results.properties.optoelectronic.solar_cell` on whatever archive it
    is normalized in. On a `SubstrateSample` that is wrong twice over: the entry
    grows an empty "Solar Cell Properties" panel, and -- worse -- bare substrates
    then match the solar-cell filters of the perovskite-database overview plots
    and are counted as devices.

    Everything the base normalize does is that side effect (it only copies
    `stack_sequence` into the results section), so overriding it to a no-op loses
    nothing: the quantities themselves are still stored and searchable on the
    entry.
    """

    m_def = Section(label='Substrate')

    def normalize(self, archive, logger):
        pass


def _kpi_statistics(values):
    """(best, worst, average) of a KPI, or None when nothing was measured."""
    values = [value for value in values if value is not None]
    if not values:
        return None
    # Summed by hand rather than with `sum()`: these carry units, and pint will not
    # add a bare 0 to a voltage.
    total = values[0]
    for value in values[1:]:
        total = total + value
    return max(values), min(values), total / len(values)


class PerformanceStatistics(ArchiveSection):
    """Best, worst and average device performance over every JV scan of this sample.

    The database's own `jv` section describes a *single* curve -- the best one --
    which says nothing about how reproducible the device is. These are computed
    per KPI over all scans (both directions, all JV measurements), so the best PCE
    and the best FF need not come from the same scan; each answers "what is the
    best/worst/typical value this device reached".

    Dark scans and scans without an efficiency are left out.
    """

    m_def = Section(label='Performance Statistics')

    number_of_jv_scans = Quantity(
        type=int,
        description='Number of JV scans these statistics are taken over.',
        a_eln=ELNAnnotation(component='NumberEditQuantity'),
    )

    pce_best = Quantity(type=float, description='Highest power conversion efficiency (%).')
    pce_worst = Quantity(type=float, description='Lowest power conversion efficiency (%).')
    pce_average = Quantity(type=float, description='Mean power conversion efficiency (%).')

    voc_best = Quantity(type=float, unit='V', description='Highest open-circuit voltage.')
    voc_worst = Quantity(type=float, unit='V', description='Lowest open-circuit voltage.')
    voc_average = Quantity(type=float, unit='V', description='Mean open-circuit voltage.')

    jsc_best = Quantity(
        type=float,
        unit='mA/cm**2',
        description='Highest short-circuit current density.',
    )
    jsc_worst = Quantity(
        type=float,
        unit='mA/cm**2',
        description='Lowest short-circuit current density.',
    )
    jsc_average = Quantity(
        type=float,
        unit='mA/cm**2',
        description='Mean short-circuit current density.',
    )

    ff_best = Quantity(type=float, description='Highest fill factor (fraction).')
    ff_worst = Quantity(type=float, description='Lowest fill factor (fraction).')
    ff_average = Quantity(type=float, description='Mean fill factor (fraction).')


class SubstrateSample(CompositeSystem, PlotSection):
    m_def = Section(
        label='Substrate',
        a_eln=dict(properties=dict(order=['name', 'lab_id', 'datetime', 'substrate'])),
    )

    substrate = SubSection(
        section_def=SubstrateInfo,
        description='Physical and chemical description of the substrate.',
    )

    cell_areas = SubSection(
        section_def=CompositeSystemReference,
        repeats=True,
        description='Areas of the substrate where solar cells are located.',
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)
        figures = self._mirror_device_figures(archive, logger)
        figures.extend(self._uvvis_figures(archive, logger))
        if figures:
            self.figures = figures

    def _mirror_device_figures(self, archive, logger):
        """Show the overview plots of every device on this substrate, side by side.

        Not aggregated: each device keeps its own figures, prefixed with the device
        it belongs to, so the substrate is a contact sheet of its pixels.

        The device figures only exist on the *processed* device archive, so a
        resolved `cell_areas` reference is of no use here -- resolving one goes
        through `Context.load_raw_file`, which re-parses the YAML and hands back an
        archive that never normalized (and so has no figures). Entry ids are
        deterministic, though, so the processed archive can be loaded directly.
        This is also why substrates are processed on a level of their own, after
        the devices (see `parsers/__init__.py`).
        """
        context = getattr(archive, 'm_context', None)
        upload_id = getattr(getattr(archive, 'metadata', None), 'upload_id', None)
        if context is None or upload_id is None or not self.cell_areas:
            return []

        figures = []
        for area in self.cell_areas:
            try:
                figures.extend(self._device_figures(area, context, upload_id))
            except Exception as e:
                if logger:
                    logger.warning(
                        f'Could not mirror the figures of a cell area: {e}', exc_info=e
                    )
        return figures

    def _uvvis_figures(self, archive, logger):
        """The substrate's own UV-Vis transmittance overview.

        UV-Vis is film-level -- it describes the whole substrate, not a pixel -- so
        it is searched for and drawn here rather than mirrored from a device. This
        is the same reference search the device sample runs for its own
        measurements, filtered to UV-Vis.
        """
        try:
            measurements = self._load_uvvis_measurements(archive, logger)
        except Exception as e:
            if logger:
                logger.warning(f'Could not load UV-Vis measurements: {e}', exc_info=e)
            return []

        if not measurements:
            return []
        try:
            figure = create_uvvis_overview_figure(measurements)
        except Exception as e:
            if logger:
                logger.warning(f'Could not build the UV-Vis overview: {e}', exc_info=e)
            return []
        if figure is None:
            return []
        return [
            PlotlyFigure(label=UVVIS_OVERVIEW_LABEL, figure=figure.to_plotly_json())
        ]

    def _load_uvvis_measurements(self, archive, logger):
        """Every UV-Vis measurement entry that references this substrate."""
        if (
            archive is None
            or archive.m_context is None
            or not getattr(getattr(archive, 'metadata', None), 'entry_id', None)
        ):
            return []

        main_author = getattr(archive.metadata, 'main_author', None)
        user_id = getattr(main_author, 'user_id', None)
        if user_id is None:
            return []

        results = search(
            owner='all',
            query={'entry_references.target_entry_id': archive.metadata.entry_id},
            pagination=MetadataPagination(page_size=100),
            required=MetadataRequired(include=['entry_id', 'upload_id']),
            user_id=user_id,
        )

        measurements = []
        for hit in results.data:
            try:
                ref_archive = archive.m_context.load_archive(
                    hit['entry_id'], hit['upload_id'], None
                )
                entry = ref_archive.data
                if isinstance(entry, UVvisMeasurement):
                    measurements.append(entry)
            except Exception as e:
                if logger:
                    logger.warning(
                        f'Could not load referenced entry {hit.get("entry_id")}: {e}'
                    )
        return measurements

    @staticmethod
    def _device_entry_id(area, upload_id):
        """The entry id of the device archive a `cell_areas` entry points at.

        The app writes these references as raw paths (`../upload/raw/<mainfile>`,
        which the context rewrites to `../upload/<upload_id>/raw/<mainfile>`), and
        an entry id is a hash of the upload and the mainfile -- so it can be derived
        without resolving anything. A reference stated as an archive URL already
        carries the id.
        """
        from nomad.utils import generate_entry_id

        target = area.reference
        if target is None:
            return None

        # An unresolved reference still knows its URL; a resolved one was loaded
        # from its raw file, and the archive it lives in records that path.
        url = getattr(target, 'm_proxy_value', None)
        if url is None:
            metadata = getattr(target.m_root(), 'metadata', None)
            mainfile = getattr(metadata, 'mainfile', None)
            return generate_entry_id(upload_id, mainfile) if mainfile else None

        path = str(url).split('#', 1)[0]
        _, is_raw, mainfile = path.partition('/raw/')
        if is_raw:
            return generate_entry_id(upload_id, mainfile)

        _, is_archive, entry_id = path.partition('/archive/')
        return entry_id if is_archive else None

    def _device_figures(self, area, context, upload_id):
        entry_id = self._device_entry_id(area, upload_id)
        if not entry_id:
            return []

        device_archive = context.load_archive(entry_id, upload_id, None)
        device = getattr(device_archive, 'data', None)
        if device is None:
            return []

        name = getattr(device, 'name', None) or getattr(device, 'lab_id', None) or entry_id
        figures = []
        for figure in getattr(device, 'figures', None) or []:
            # The stack is fabrication, not measurement, and is the same for every
            # pixel of the substrate -- showing it four times says nothing.
            if figure.label == STACK_FIGURE_LABEL or figure.figure is None:
                continue
            figures.append(
                PlotlyFigure(
                    label=f'{name}: {figure.label}',
                    figure=copy.deepcopy(figure.figure),
                )
            )
        return figures


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

    performance_statistics = SubSection(
        section_def=PerformanceStatistics,
        description='Best, worst and average performance over all JV scans.',
    )

    images = SubSection(section_def=ImageFile, repeats=True)
    documents = SubSection(section_def=DocumentFile, repeats=True)

    def normalize(self, archive, logger):
        super().normalize(archive, logger)

        # Order matters, and it is the reverse of what it used to be.
        #
        # NOMAD's MetainfoNormalizer walks the archive *post-order*: every
        # subsection is normalized before its parent. So by the time we get here,
        # `self.jv.normalize()` has already run -- against an empty `jv`, because
        # `jv` is only filled below, from the linked measurement entries. It is
        # `JV.normalize` that copies default_PCE/Voc/Jsc/FF and light_intensity
        # into `results.properties.optoelectronic.solar_cell` (the "Solar Cell
        # Properties" panel and the source of the perovskite-database overview
        # plots), which is why that panel stayed empty. Sections we *create* here
        # (eqe, stability, stabilised) were never normalized at all.
        #
        # So: populate first, then re-normalize the sections we touched by hand,
        # then draw the figures from the values that are now actually there.
        measurements = self._populate_jv_from_measurements(archive, logger)
        self._normalize_populated_sections(archive, logger)
        self._populate_performance_statistics(measurements.jv, logger)
        self._build_figures(measurements, logger)

    def _normalize_populated_sections(self, archive, logger):
        """Re-run the database sections' own normalize, now that they hold data."""
        for section in (self.jv, self.eqe, self.stability, self.stabilised):
            if section is None:
                continue
            try:
                section.normalize(archive, logger)
            except Exception as e:
                if logger:
                    logger.warning(
                        f'Could not normalize {section.m_def.name}: {e}', exc_info=e
                    )

        # An EQE-derived band gap belongs on the perovskite, and only `Perovskite`
        # .normalize carries it into `results.properties.electronic`.
        bandgap = self.eqe.bandgap_eqe if self.eqe is not None else None
        if self.perovskite is not None and bandgap is not None and not self.perovskite.band_gap:
            self.perovskite.band_gap = str(bandgap.to('eV').magnitude)
            self.perovskite.band_gap_estimation_basis = 'EQE'
            try:
                self.perovskite.normalize(archive, logger)
            except Exception as e:
                if logger:
                    logger.warning(f'Could not normalize perovskite: {e}', exc_info=e)

    def _populate_performance_statistics(self, measurements, logger=None):
        """Best / worst / average of each JV KPI, over every scan of this sample.

        Per KPI, not per curve: the best FF and the best PCE may well come from
        different scans, and both are worth knowing. `jv` already describes the
        single best curve, which says nothing about spread.
        """
        scans = [
            curve
            for measurement in measurements
            for curve in getattr(measurement, 'jv_curve', None) or []
            if not getattr(curve, 'dark', False) and curve.efficiency is not None
        ]

        if not scans:
            # Rebuild rather than keep: normalize() runs repeatedly on the same
            # archive, and stale statistics are worse than none.
            self.performance_statistics = None
            return

        statistics = PerformanceStatistics(number_of_jv_scans=len(scans))
        for prefix, attribute in (
            ('pce', 'efficiency'),
            ('voc', 'open_circuit_voltage'),
            ('jsc', 'short_circuit_current_density'),
            ('ff', 'fill_factor'),
        ):
            values = _kpi_statistics(
                [getattr(curve, attribute, None) for curve in scans]
            )
            if values is None:
                continue
            best, worst, average = values
            setattr(statistics, f'{prefix}_best', best)
            setattr(statistics, f'{prefix}_worst', worst)
            setattr(statistics, f'{prefix}_average', average)

        self.performance_statistics = statistics
        if logger:
            logger.info(f'Performance statistics over {len(scans)} JV scans.')

    def _build_figures(self, measurements, logger):
        """The sample's figures: the device stack, then one overview per measurement kind.

        Drawn last, so the stack's annotations read the populated `jv` rather than
        the empty one -- that is why every value used to render as N/A. An overview
        with nothing to show is left out rather than drawn empty.
        """
        figures = []

        stack = self._build_stack_figure(logger)
        if stack is not None:
            figures.append(PlotlyFigure(label=STACK_FIGURE_LABEL, figure=stack))

        for label, builder, argument in (
            (
                JV_OVERVIEW_LABEL,
                lambda: create_jv_overview_figure(
                    measurements.jv, self.performance_statistics
                ),
                measurements.jv,
            ),
            (
                # Dark sweeps get their own diagram; the builder returns None when
                # there is no dark curve, so this figure appears only where there is.
                DARK_JV_OVERVIEW_LABEL,
                lambda: create_dark_jv_overview_figure(measurements.jv),
                measurements.jv,
            ),
            (
                STABILITY_OVERVIEW_LABEL,
                lambda: create_stability_overview_figure(measurements.mppt),
                measurements.mppt,
            ),
            (
                EQE_OVERVIEW_LABEL,
                lambda: create_eqe_overview_figure(measurements.eqe),
                measurements.eqe,
            ),
        ):
            if not argument:
                continue
            try:
                figure = builder()
            except Exception as e:
                if logger:
                    logger.warning(f'Could not create the {label} figure: {e}', exc_info=e)
                continue
            if figure is not None:
                figures.append(
                    PlotlyFigure(label=label, figure=figure.to_plotly_json())
                )

        self.figures = figures

    def _build_stack_figure(self, logger):
        """The layer stack, annotated with the device's JV performance.

        Returns the plotly JSON, or None when there is no stack to draw.
        """
        if self.cell is None or not self.cell.stack_sequence:
            return None

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
            return fig.to_plotly_json()
        except (TypeError, ValueError) as e:
            if logger:
                logger.warning(
                    'Could not create cell stack figure.',
                    exc_info=e,
                )
            return None

    def _populate_jv_from_measurements(self, archive, logger):
        """Load every measurement entry that references this sample, and derive from it.

        Returns the loaded measurements, grouped by kind: they are what the overview
        figures are drawn from, and loading each archive once is the point.
        """
        if (
            archive is None
            or archive.m_context is None
            or not hasattr(archive, 'metadata')
            or not hasattr(archive.metadata, 'entry_id')
        ):
            return LoadedMeasurements.none()

        # `owner='visible'` means *published* entries plus the ones `user_id` may
        # view -- and with `user_id=None` that first clause is all there is. A
        # freshly uploaded (unpublished) measurement is therefore never matched,
        # so this search returned nothing, every time. Search as the upload's
        # author over everything they own, which is what baseclasses does.
        main_author = getattr(archive.metadata, 'main_author', None)
        user_id = getattr(main_author, 'user_id', None)
        if user_id is None:
            if logger:
                logger.warning(
                    'No main_author on the archive; cannot search for linked '
                    'measurements.'
                )
            return LoadedMeasurements.none()

        try:
            results = search(
                owner='all',
                query={'entry_references.target_entry_id': archive.metadata.entry_id},
                pagination=MetadataPagination(page_size=100),
                required=MetadataRequired(include=['entry_id', 'upload_id']),
                user_id=user_id,
            )
        except Exception as e:
            if logger:
                logger.warning(f'Failed to search for linked measurements: {e}')
            return LoadedMeasurements.none()

        if not results.data:
            return LoadedMeasurements.none()

        jv_measurements = []
        eqe_measurements = []
        mppt_measurements = []

        # A search hit is a plain dict (MetadataResponse.data is list[dict]).
        # Reading it as an object raised AttributeError into the except below, so
        # even a hit that *was* found never got loaded.
        for hit in results.data:
            try:
                ref_archive = archive.m_context.load_archive(
                    hit['entry_id'], hit['upload_id'], None
                )
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
                    logger.warning(
                        f'Could not load referenced entry {hit.get("entry_id")}: {e}'
                    )

        measurements = LoadedMeasurements(
            jv=jv_measurements, eqe=eqe_measurements, mppt=mppt_measurements
        )
        if not measurements:
            return measurements

        if not self.jv:
            from perovskite_solar_cell_database.schema_sections.jv import JV as JVSection

            self.jv = JVSection()

        self._populate_from_jv(jv_measurements, logger)
        for measurement in eqe_measurements:
            self._populate_from_eqe(measurement)
        for measurement in mppt_measurements:
            self._populate_from_mppt(measurement)

        return measurements

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

        # source (baseclasses SolarCellEQECustom) -> target (database EQE).
        # The two integrated quantities are spelled with a capital J on the target
        # ('integrated_Jsc', 'integrated_J0rad'); copying them under the source's
        # lower-case name meant the all_properties guard below dropped them both.
        for source, target in (
            ('bandgap_eqe', 'bandgap_eqe'),
            ('integrated_jsc', 'integrated_Jsc'),
            ('integrated_j0rad', 'integrated_J0rad'),
            ('voc_rad', 'voc_rad'),
            ('urbach_energy', 'urbach_energy'),
            ('eqe_array', 'eqe_array'),
            ('photon_energy_array', 'photon_energy_array'),
            ('wavelength_array', 'wavelength_array'),
            ('raw_eqe_array', 'raw_eqe_array'),
            ('raw_photon_energy_array', 'raw_photon_energy_array'),
            ('raw_wavelength_array', 'raw_wavelength_array'),
            ('light_bias', 'light_bias'),
        ):
            value = getattr(data, source, None)
            if value is not None and eqe.m_def.all_properties.get(target) is not None:
                setattr(eqe, target, value)

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
        #
        # Only points where the cell actually *delivers* power count. A track that
        # starts above Voc (a fixed-voltage algorithm does) opens with the cell
        # being driven, i.e. a negative efficiency -- which is not a PCE.
        efficiency = measurement.efficiency
        stabilised = []
        if efficiency is not None and len(efficiency):
            stabilised = [
                float(value)
                for value in efficiency
                if math.isfinite(float(value)) and float(value) > 0
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
