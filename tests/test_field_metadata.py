from ommi.field_metadata import AggregateMetadata, create_metadata_flag, create_metadata_type, MetadataFlag

FlagA = create_metadata_flag("FlagA")
FlagB = create_metadata_flag("FlagB")
MetadataA = create_metadata_type("MetadataA")
MetadataB = create_metadata_type("MetadataB")


def test_flag_metadata_types():
    assert isinstance(FlagA, MetadataFlag)


def test_aggregate_metadata_types():
    assert isinstance(FlagA | MetadataA(), AggregateMetadata)


def test_aggregate_matches_flags():
    aggregate = MetadataA() | FlagA
    assert aggregate.matches(FlagA)
    assert not aggregate.matches(FlagB)


def test_aggregate_matches_metadata_type():
    aggregate = MetadataA() | FlagA
    assert aggregate.matches(MetadataA)
    assert not aggregate.matches(MetadataB)


def test_metadata_matches():
    assert MetadataA().matches(MetadataA)
    assert not MetadataA().matches(MetadataB)
