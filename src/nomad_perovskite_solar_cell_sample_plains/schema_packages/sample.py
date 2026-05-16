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
from baseclasses.solar_energy.jvmeasurement import JVMeasurement
from baseclasses.solar_energy.eqemeasurement import EQEMeasurement     # same pattern
from baseclasses.solar_energy.mpp_tracking import MPPTracking      # same pattern

m_package = SchemaPackage()


class PerovskiteSolarCellSample(PerovskiteSolarCell, Entity, EntryData):
    m_def = Section(
        label='Perovskite Solar Cell Sample',
        a_eln=dict(
            properties=dict(
                order=['name', 'lab_id', 'datetime', 'performed_measurements']
            )
        ),
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)


m_package.__init_metainfo__()