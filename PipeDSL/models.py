from decimal import Decimal
from enum import StrEnum, auto
from types import NoneType
from typing import TypeVar, Generic

from pydantic import BaseModel, ConfigDict

from PipeDSL.lexer import Context, Job

T = TypeVar("T")


class Pipeline(BaseModel):
    task_id: str
    pipeline: str
    fetch_strategy: str | None = None
    http_rps_limit: int | None = None
    pipeline_context: dict[str, str | list[str]]
    ast: tuple[Context, list[Job]] | None = None


class HttpRequest(BaseModel):
    url: str
    headers: dict
    method: str
    timeout: float = 300
    body: str | None = None
    json_extractor_props: dict[str, str] = dict


class HttpResponse(BaseModel):
    headers: dict
    status_code: int
    execution_time: Decimal


class TextResponse(HttpResponse):
    body: str | None


class EmptyResponse(BaseModel):
    ...


class JsonResponse(HttpResponse):
    body: str | None


TaskPayloadType = HttpRequest | Pipeline

TaskType = TypeVar('TaskType')


class Task(BaseModel, Generic[TaskType]):
    id: str
    name: str
    type: str
    single: bool = True
    payload: TaskType

    model_config = ConfigDict(
        frozen=True,
    )


class PipelineJobResult(BaseModel):
    id: str
    created_at: str
    task_id: str
    props: dict[str, list[str]] = dict()
    args: list[str] = list()
    request: HttpRequest | None = None
    result: TextResponse | JsonResponse

    model_config = ConfigDict(
        frozen=True,
    )


class PipelineResult(BaseModel):
    task_id: str
    status: str
    job_results: 'list[str]' = []

    model_config = ConfigDict(
        frozen=True,
    )


TaskResultPayload = TypeVar('TaskResultPayload')


class TaskResult(BaseModel, Generic[TaskResultPayload]):
    id: str
    created_at: str
    task_id: str
    payload_type: str
    error_description: str = ""
    is_throw: bool = False
    # payload: TextResponse | JsonResponse | PipelineResult | None
    payload: TaskResultPayload | None = None
    request: HttpRequest | None = None
    args: list[str] = list()

    model_config = ConfigDict(
        frozen=True,
    )


class TaskPayloadTypes(StrEnum):
    HTTP_TEXT = auto()
    HTTP_JSON = auto()
    PIPELINE = auto()
    EMPTY = auto()


TaskPayloadTypesAssoc = {
    TaskPayloadTypes.HTTP_TEXT: TextResponse,
    TaskPayloadTypes.HTTP_JSON: JsonResponse,
    TaskPayloadTypes.PIPELINE: PipelineResult,
    TaskPayloadTypes.EMPTY: NoneType
}

TaskPayloadTypesAssocInv = {v: k for k, v in TaskPayloadTypesAssoc.items()}


class TaskListsSerializer(BaseModel):
    id: str
    name: str
    type: str
    single: bool = True

    model_config = ConfigDict(
        frozen=True,
    )


class TaskListItemResult(BaseModel):
    id: str
    type: str
    created_at: str
    task_name: str
    task_id: str
    path: str
    args: list[str] = list()
    diff_ratio: int | float | None = 0
    previous_status_code: int | float | None = 0
    status_code: int | float | None = 0

    model_config = ConfigDict(
        frozen=True,
    )


class DashboardItemResult(TaskListItemResult):
    previous_result_id: str | None = None
