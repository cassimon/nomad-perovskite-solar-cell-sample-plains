from nomad.parsing.parser import ArchiveParser, MatchingParser


class PlainsSampleParser(ArchiveParser):
    """The built-in archive parser, moved to a later processing level.

    The parsing itself is exactly the built-in one -- a sample archive is a plain
    NOMAD archive YAML and needs no special reading. What differs is *when* it
    runs.

    `PerovskiteSolarCellSampleArea.normalize` collects the JV / EQE / stability
    entries that reference the sample by searching Elasticsearch. The built-in
    archive parser runs at level -1, so without this the sample and the
    measurements it depends on are processed in the same level, concurrently, and
    the measurements may not be indexed yet when the sample looks for them --
    which silently yields a sample with no JV data. Levels are processed strictly
    in order, so a higher level makes the dependency explicit.
    """

    def __init__(self, **kwargs):
        # ArchiveParser.__init__ takes no arguments and hard-codes level=-1, so go
        # straight to MatchingParser with the entry point's configuration.
        MatchingParser.__init__(self, **kwargs)
        self.domain = None
