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
from nomad.search import search
from nomad.app.v1.models import MetadataPagination

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
    Embedded scalar summaries — no references back to measurement entries.
    This avoids cycles. Each SolarCellJV item carries a data_file
    quantity (inherited from baseclasses) which links the raw file.
    The measurement entry separately holds pvk_sample → sample reference.
    """
    jv = SubSection(section_def=SolarCellJV, repeats=True)
    eqe = SubSection(section_def=SolarCellEQE, repeats=True)
    stability = SubSection(section_def=MPPTracking, repeats=True)


class PerovskiteSolarCellSample(PerovskiteSolarCell, Entity, EntryData):
    m_def = Section(
        label='Perovskite Solar Cell Sample',
        a_eln=dict(
            properties=dict(
                order=['name', 'lab_id', 'datetime', 'performed_measurements']
            )
        ),
    )
    performed_measurements = SubSection(section_def=PerformedMeasurements)

    def normalize(self, archive, logger):
        super().normalize(archive, logger)


m_package.__init_metainfo__()