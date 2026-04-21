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
    jv        = SubSection(section_def=SolarCellJV, repeats=True)
    eqe       = SubSection(section_def=SolarCellEQE, repeats=True)
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
        super().normalize(archive, logger)


# pvk_sample_schema/schema.py  — only PVKMeasurementBase changes

class PVKMeasurementBase(EntryData):
    m_def = Section(abstract=True)

    pvk_sample = Quantity(
        type=Reference(PerovskiteSolarCellSample.m_def),
        description='Direct reference to the sample entry (set by NOMAD from '
                    'the archive sidecar, or resolved from pvk_sample_id).',
        a_eln=ELNAnnotation(component='ReferenceEditQuantity'),
    )

    pvk_sample_id = Quantity(
        type=str,
        description='Human-readable sample ID (lab_id of the target sample). '
                    'If set, normalize() resolves this to pvk_sample automatically. '
                    'pvk_sample takes precedence if both are set.',
        a_eln=ELNAnnotation(component='StringEditQuantity'),
    )

    def _resolve_sample(self, archive, logger):
        """
        If pvk_sample is already set, do nothing.
        If pvk_sample_id is set, search the upload context for a
        PerovskiteSolarCellSample whose lab_id matches and set pvk_sample.
        """
        if self.pvk_sample is not None:
            return  # Mode A — direct reference already set

        if not self.pvk_sample_id:
            return  # neither set — warning handled downstream

        if archive is None or archive.m_context is None:
            logger.warning(
                f'{self.__class__.__name__}: pvk_sample_id={self.pvk_sample_id!r} '
                'cannot be resolved without an archive context.'
            )
            return

        # Search all entries in this upload for matching lab_id
        try:


            results = search(
                owner='visible',
                query={'lab_id': self.pvk_sample_id,
                       'section_defs.definition_qualified_name':
                           'pvk_sample_schema.schema.PerovskiteSolarCellSample'},
                pagination=MetadataPagination(page_size=1),
                user_id=archive.metadata.main_author.user_id
                        if archive.metadata else None,
            )
            if results.pagination.total == 0:
                logger.warning(
                    f'{self.__class__.__name__}: no sample found with '
                    f'lab_id={self.pvk_sample_id!r}.'
                )
                return

            entry_id = results.data[0].entry_id
            # Build a proper NOMAD reference from the entry_id
            self.pvk_sample = archive.m_context.resolve_section_reference(
                archive, f'../entries/{entry_id}/archive#/data'
            )
            logger.info(
                f'Resolved pvk_sample_id={self.pvk_sample_id!r} '
                f'to entry_id={entry_id}'
            )
        except Exception as e:
            logger.warning(
                f'{self.__class__.__name__}: failed to resolve '
                f'pvk_sample_id={self.pvk_sample_id!r}: {e}'
            )

    def normalize(self, archive, logger):
        if archive is not None:
            super().normalize(archive, logger)

        self._resolve_sample(archive, logger)   # ← new pre-resolution step

        if self.pvk_sample is None:
            logger.warning(
                f'{self.__class__.__name__}: no pvk_sample set '
                f'(pvk_sample_id={self.pvk_sample_id!r}), '
                'skipping self-registration.'
            )
            return

        if self.pvk_sample.performed_measurements is None:
            self.pvk_sample.performed_measurements = PerformedMeasurements()

        result = self._build_result(logger)
        if result is not None:
            self.pvk_sample.performed_measurements.register(result, logger)

    def _build_result(self, logger):
        return None


m_package.__init_metainfo__()
