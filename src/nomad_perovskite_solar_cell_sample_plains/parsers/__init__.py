from nomad.config.models.plugins import ParserEntryPoint


class PlainsSampleParserEntryPoint(ParserEntryPoint):
    def load(self):
        from nomad_perovskite_solar_cell_sample_plains.parsers.parsers import (
            PlainsSampleParser,
        )

        return PlainsSampleParser(**self.model_dump())


sample_parser_entry_point = PlainsSampleParserEntryPoint(
    name='PlainsSampleParser',
    description=(
        'Processes the sample archives the Plains app uploads. Identical to the '
        'built-in archive parser except for its level, which defers the sample '
        'until its measurements have been processed and indexed.'
    ),
    # `PerovskiteSolarCellSampleArea.normalize` finds its measurements with an
    # Elasticsearch query, so they must be *indexed* before it runs. NOMAD
    # processes parser levels one after another and waits for each to finish
    # (`Upload.parse_next_level`), so a level above the archive parser's -1 -- the
    # level the measurement archives are processed at -- is what makes that
    # ordering a guarantee instead of a race.
    level=2,
    mainfile_name_re=r'.*\.archive\.(json|yaml|yml)$',
    # Only *our* device sample archives. The measurement and deposition archives
    # stay with the built-in parser at level -1; substrates go one level later
    # still, see below.
    mainfile_contents_re=(
        r'nomad_perovskite_solar_cell_sample_plains\.schema_packages\.sample\.'
        r'PerovskiteSolarCellSampleArea'
    ),
    mainfile_mime_re=r'.*',
)


material_parser_entry_point = PlainsSampleParserEntryPoint(
    name='PlainsMaterialParser',
    description=(
        'Processes the material entities the Plains app uploads. Runs on an early '
        'level so a material is present before the solutions and steps that '
        'reference it are normalized.'
    ),
    # Materials carry no cross-references, so they can normalize first. Level 1 keeps
    # them ahead of solutions (2) and samples (2), which may point at them.
    level=1,
    mainfile_name_re=r'.*\.archive\.(json|yaml|yml)$',
    mainfile_contents_re=(
        r'nomad_perovskite_solar_cell_sample_plains\.schema_packages\.chemicals\.'
        r'PlainsMaterial'
    ),
    mainfile_mime_re=r'.*',
)


solution_parser_entry_point = PlainsSampleParserEntryPoint(
    name='PlainsSolutionParser',
    description=(
        'Processes the solution entities the Plains app uploads. Runs after the '
        'materials it references. Solutions may reference one another (a solution '
        'built from stock solutions); those references resolve lazily, so ordering '
        'within this level is not load-bearing.'
    ),
    level=2,
    mainfile_name_re=r'.*\.archive\.(json|yaml|yml)$',
    mainfile_contents_re=(
        r'nomad_perovskite_solar_cell_sample_plains\.schema_packages\.chemicals\.'
        r'PlainsSolution'
    ),
    mainfile_mime_re=r'.*',
)


substrate_parser_entry_point = PlainsSampleParserEntryPoint(
    name='PlainsSubstrateParser',
    description=(
        'Processes the substrate archives the Plains app uploads. Identical to the '
        'built-in archive parser except for its level, which defers the substrate '
        'until the devices whose figures it mirrors have been processed.'
    ),
    # `SubstrateSample.normalize` copies the overview figures of every device on the
    # substrate, and those figures only exist once the *device* has normalized. The
    # devices are level 2, so the substrate has to come after them.
    level=3,
    mainfile_name_re=r'.*\.archive\.(json|yaml|yml)$',
    mainfile_contents_re=(
        r'nomad_perovskite_solar_cell_sample_plains\.schema_packages\.sample\.'
        r'SubstrateSample'
    ),
    mainfile_mime_re=r'.*',
)
