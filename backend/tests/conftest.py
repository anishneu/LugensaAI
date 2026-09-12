import pytest

from app.models.location import Location


@pytest.fixture
def harvard_square() -> Location:
    return Location(
        name="Harvard Square",
        city="Cambridge",
        region="MA",
        country="US",
        slug="harvard-square-cambridge-ma",
        latitude=42.3736,
        longitude=-71.119,
        raw_query="Harvard Square, Cambridge, MA",
    )
