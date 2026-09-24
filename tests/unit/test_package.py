from importlib.metadata import version

import dbdelta


def test_version_comes_from_distribution_metadata() -> None:
    assert dbdelta.__version__ == version("dbdelta")
