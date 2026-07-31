import tvqa


def test_package_importable():
    assert hasattr(tvqa, "__version__")
