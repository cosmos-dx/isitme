from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from brain_core.brain import Brain
from brain_core.config import Settings


def make_settings(tmp_path) -> Settings:
    """Fully local, zero-network settings rooted at a temp dir."""
    return Settings(
        data_dir=str(tmp_path / "brain"),
        mode="local",
    )


@pytest_asyncio.fixture
async def brain(tmp_path) -> AsyncIterator[Brain]:
    b = Brain(make_settings(tmp_path))
    await b.startup()
    try:
        yield b
    finally:
        await b.shutdown()
