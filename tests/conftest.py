from pathlib import Path

import pytest

from video_ops.adapters.mock_platform import MockPlatformAdapter
from video_ops.adapters.script_producers import default_script_producers
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.application.seed import seed_demo
from video_ops.application.service import VideoOperationsService

APP_ROOT = Path(__file__).parents[1]
SEED_PATH = APP_ROOT / "data" / "sample" / "workspace-seed.json"


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "workspace.db")
    seed_demo(repo, SEED_PATH)
    return repo


@pytest.fixture
def service(repository: SQLiteRepository) -> VideoOperationsService:
    return VideoOperationsService(
        repository,
        platform_adapters={"mock-social": MockPlatformAdapter()},
        script_producer_factories=default_script_producers(),
    )
