from nomad_perovskite_solar_cell_sample_plains.schema_packages.sample import SubstrateSample


class DummyArea:
    def __init__(self):
        self.called = False

    def normalize(self, archive, logger):
        self.called = True


def test_cell_areas_iteration_calls_normalize():
    s = SubstrateSample()
    a1 = None
    a2 = DummyArea()
    a3 = DummyArea()
    s.cell_areas = [a1, a2, a3]

    # Provide a minimal fake archive object required by base normalize
    from types import SimpleNamespace

    fake_archive = SimpleNamespace()
    fake_archive.results = SimpleNamespace()
    fake_archive.results.eln = SimpleNamespace(lab_ids=[], names=[], descriptions=[], sections=[], tags=[])
    fake_archive.metadata = SimpleNamespace(entry_name='test_entry', entry_id='test')

    # Should not raise and should call normalize on non-None areas
    s.normalize(archive=fake_archive, logger=None)

    assert a2.called is True
    assert a3.called is True
