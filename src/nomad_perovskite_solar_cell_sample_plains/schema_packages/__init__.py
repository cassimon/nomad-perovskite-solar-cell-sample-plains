from nomad.config.models.plugins import SchemaPackageEntryPoint
from pydantic import Field

class PlainsEntryPoint(SchemaPackageEntryPoint):
    parameter: int = Field(0, description='Custom configuration parameter')

    def load(self):
        from nomad_perovskite_solar_cell_sample_plains.schema_packages.schema_package import m_package

        return m_package


schema_package_entry_point = PlainsEntryPoint(
    name='Plains',
    description='Entry Point for Plains: Perovskite Solar Cell Schema Package',
)
