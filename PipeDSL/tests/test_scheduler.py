import asyncio
from types import NoneType

import pytest
from typing_extensions import TypeVar

from PipeDSL.models import Task, HttpRequest
from PipeDSL.services.task_scheduler import TaskScheduler


def test_execute_task():
    task_params = {"id": "aa", "name": "bb", "type": "http"}
    NotImplementType = TypeVar("NotImplementType")
    task = Task[NotImplementType](**task_params, payload=None)

    async def main(t):
        async for task, result_task in TaskScheduler.schedule(t):
            pass

    with pytest.raises(NotImplementedError):
        result = asyncio.run(main([task]))
