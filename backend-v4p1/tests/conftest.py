import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="ai-influencer-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT}/test.db"
os.environ["MEDIA_DIR"] = str(TEST_ROOT / "media")
os.environ["DATASET_DIR"] = str(TEST_ROOT / "dataset")
os.environ["DATASET_IMPORT_DIR"] = str(TEST_ROOT / "imports")
os.environ["LORA_DIR"] = str(TEST_ROOT / "loras")
os.environ["API_KEY"] = "test-key"
os.environ["TEXT_PROVIDER"] = "mock"
os.environ["IMAGE_PROVIDER"] = "mock"
os.environ["SCHEDULER_ENABLED"] = "false"

import pytest
from sqlalchemy import event

from app.db import Base, engine


@event.listens_for(engine, "connect")
def sqlite_foreign_keys(connection, record):
    connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
