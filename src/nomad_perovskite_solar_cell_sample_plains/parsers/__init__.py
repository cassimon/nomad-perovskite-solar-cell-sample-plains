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
    # Only *our* sample archives; the measurement, substrate and deposition
    # archives must stay with the built-in parser at level -1.
    mainfile_contents_re=(
        r'nomad_perovskite_solar_cell_sample_plains\.schema_packages\.sample\.'
        r'PerovskiteSolarCellSampleArea'
    ),
    mainfile_mime_re=r'.*',
)
