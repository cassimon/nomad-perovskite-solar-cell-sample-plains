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
from nomad.datamodel.metainfo.basesections import Entity
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.metainfo import Quantity, Reference, Section, SubSection, SchemaPackage

configuration = config.get_plugin_entry_point(
    'nomad_perovskite_solar_cell_sample_plains.schema_packages:schema_package_entry_point'
)


from perovskite_solar_cell_database.schema import PerovskiteSolarCell

# baseclasses solar energy measurement sections — no tandem anywhere
from baseclasses.solar_energy.jvmeasurement import SolarCellJV
from baseclasses.solar_energy.eqemeasurement import SolarCellEQE      # same pattern
from baseclasses.solar_energy.mpp_tracking import MPPTracking      # same pattern

m_package = SchemaPackage()

class PerformedMeasurements(ArchiveSection):
    """
    Embedded measurement summaries. Each list is populated by the
    normalize() of the corresponding measurement entry.
    Uses baseclasses result sections — no tandem dependency.
    """
    jv = SubSection(section_def=SolarCellJV, repeats=True)
    eqe = SubSection(section_def=SolarCellEQE, repeats=True)
    stability = SubSection(section_def=MPPTracking, repeats=True)


class PerovskiteSolarCellSample(PerovskiteSolarCell, Entity, EntryData):
    m_def = Section(label='Perovskite Solar Cell Sample')
    performed_measurements = SubSection(section_def=PerformedMeasurements)

    def normalize(self, archive, logger):
        super().normalize(archive, logger)


class PVKMeasurementBase(EntryData):
    """
    Minimal abstract base. Does NOT inherit baseclasses.BaseMeasurement here —
    that happens in the lab plugin subclasses, which brings in the full
    SolarCellBaseMeasurement chain including its `samples` subsection.

    This class only defines the reference to PerovskiteSolarCellSample
    and the self-registration contract.
    """
    m_def = Section(abstract=True)

    pvk_sample = Quantity(
        type=Reference(PerovskiteSolarCellSample.m_def),
        description='The PerovskiteSolarCellSample this measurement belongs to.',
        a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)
        if self.pvk_sample is None:
            logger.warning(f'{self.__class__.__name__}: no pvk_sample set.')
            return
        if self.pvk_sample.performed_measurements is None:
            self.pvk_sample.performed_measurements = PerformedMeasurements()
        self._register_into_sample(self.pvk_sample.performed_measurements, logger)

    def _register_into_sample(self, performed: PerformedMeasurements, logger):
        raise NotImplementedError


m_package.__init_metainfo__()
