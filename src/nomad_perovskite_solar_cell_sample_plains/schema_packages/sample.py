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
from baseclasses.solar_energy.eqemeasurement import EQEMeasurement
from baseclasses.solar_energy.mpp_tracking import MPPTracking

m_package = SchemaPackage()


class PerovskiteSolarCellSample(PerovskiteSolarCell, Entity, EntryData):
    m_def = Section(
        label='Perovskite Solar Cell Sample',
        a_eln=dict(
            properties=dict(
                order=['name', 'lab_id', 'datetime']
            )
        ),
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)
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