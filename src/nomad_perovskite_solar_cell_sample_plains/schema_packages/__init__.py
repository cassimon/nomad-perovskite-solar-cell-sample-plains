"""Package entry point for the schema package.

This module tries to register a proper `SchemaPackageEntryPoint` when the
NOMAD environment (and `pydantic`) is available. In test or minimal
environments those dependencies may be absent; in that case we provide a
lightweight fallback that exposes a `load()` returning the in-repo
`m_package` to keep tests and simple imports working.
"""

try:
    from nomad.config.models.plugins import SchemaPackageEntryPoint
    from pydantic import Field
except Exception:
    SchemaPackageEntryPoint = None
    Field = None


if SchemaPackageEntryPoint is not None and Field is not None:
    class PlainsEntryPoint(SchemaPackageEntryPoint):
        parameter: int = Field(0, description='Custom configuration parameter')

        def load(self):
            from nomad_perovskite_solar_cell_sample_plains.schema_packages.schema_package import m_package

            return m_package

    schema_package_entry_point = PlainsEntryPoint(
        name='Plains',
        description='Entry Point for Plains: Perovskite Solar Cell Schema Package',
    )
else:
    # Lightweight fallback for tests / minimal environments.
    class _FallbackEntryPoint:
        name = 'Plains'
        description = 'Fallback entry point for tests'

        def __init__(self, parameter: int = 0):
            self.parameter = parameter

        def load(self):
            # import lazily to avoid import-time side effects
            from nomad_perovskite_solar_cell_sample_plains.schema_packages.schema_package import m_package

            return m_package

    schema_package_entry_point = _FallbackEntryPoint()
