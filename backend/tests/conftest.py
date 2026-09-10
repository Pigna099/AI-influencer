import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="ai-influencer-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT}/test.db"
os.environ["MEDIA_DIR"] = str(TEST_ROOT / "media")
os.environ["API_KEY"] = "test-key"
os.environ["TEXT_PROVIDER"] = "mock"
os.environ["IMAGE_PROVIDER"] = "mock"

import pytest

from app.db import Base, engine


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
