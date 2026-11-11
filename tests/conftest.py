from datetime import date

import pytest

from sborline import db
from sborline.seed import seed_demo

TODAY = date(2026, 11, 11)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    seed_demo(c, TODAY)
    yield c
    c.close()
