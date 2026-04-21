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
    jv        = SubSection(section_def=SolarCellJV,       repeats=True)
    eqe       = SubSection(section_def=SolarCellEQE,      repeats=True)
    stability = SubSection(section_def=MPPTracking, repeats=True)

    _DISPATCH: dict[type, str] = {
        SolarCellJV:        'jv',
        SolarCellEQE:       'eqe',
        MPPTracking:     'stability',
    }

    def register(self, result: ArchiveSection, logger) -> None:
        target = self._DISPATCH.get(type(result))
        if target is None:
            logger.warning(
                f'PerformedMeasurements.register: unregistered type '
                f'{type(result).__name__}, skipping.'
            )
            return
        getattr(self, target).append(result)


class PerovskiteSolarCellSample(PerovskiteSolarCell, Entity, EntryData):
    m_def = Section(label='Perovskite Solar Cell Sample')
    performed_measurements = SubSection(section_def=PerformedMeasurements)

    def normalize(self, archive, logger):
        self.performed_measurements = self.performed_measurements or PerformedMeasurements()
        super().normalize(archive, logger)


class PVKMeasurementBase(EntryData):
    m_def = Section(abstract=True)

    pvk_sample = Quantity(
        type=Reference(PerovskiteSolarCellSample.m_def),
        a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    )

    def normalize(self, archive, logger):
        if archive is not None:
            super().normalize(archive, logger)

        if self.pvk_sample is None:
            logger.warning(f'{self.__class__.__name__}: no pvk_sample set.')
            return

        result = self._build_result(logger)
        if result is not None:
            self.pvk_sample.performed_measurements.register(result, logger)

    def _build_result(self, logger):
        """Override in subclass. Return the result object to register,
        or None to skip registration."""
        return None


m_package.__init_metainfo__()
