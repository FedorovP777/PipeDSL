import asyncio
import copy
import datetime
import decimal
import itertools
import json
import uuid
from collections.abc import Callable, AsyncGenerator, Awaitable, Iterable
from functools import partial, singledispatch, singledispatchmethod
from typing import Any, Protocol, TypeVar, cast, Never

import aiohttp

from PipeDSL import models
from PipeDSL.lexer import Job, CallFunction, ResultFunction, Product, PositionalArg
from PipeDSL.models import HttpRequest, Pipeline, Task, TaskResult, JsonResponse, TextResponse, PipelineJobResult, PipelineResult, \
    TaskPayloadTypesAssocInv, EmptyResponse
from PipeDSL.utils import http_client
from PipeDSL.utils.logger import logger
from PipeDSL.utils.utils import json_extend_extractor, timeit


class DslFunction(Protocol):
    name: str

    async def __call__(self) -> Any: ...


class DslFunctionUuid:
    name: str = "uuid"

    async def __call__(self) -> str:
        return str(uuid.uuid4())


class DslFunctionConcat:
    name: str = "concat"

    async def __call__(self, *args: Any, **kwargs: Any) -> str:
        return "".join(str(arg) for arg in args)


class DslFunctionDiv:
    name: str = "div"

    async def __call__(self, *args: Any, **kwargs: Any) -> float:
        if isinstance(args[0], list):
            return float(args[0][0]) / float(args[1])

        return float(args[0]) / float(args[1])


class DslFunctionRange:
    name: "range"

    async def __call__(self, *args: Any, **kwargs: Any) -> list[int]:
        if len(args) == 3:
            start, stop, step = args
            if isinstance(start, list):
                start = start[0]
            if isinstance(stop, list):
                stop = stop[0]
            if isinstance(step, list):
                step = step[0]
            return list(range(int(start), int(stop), int(step)))
        return []


SYSTEM_FUNCTION_REGISTRY: dict[str, Callable[..., Awaitable[Any]]] = {
    "uuid": cast(Callable[..., Awaitable[Any]], DslFunctionUuid()),
    "concat": DslFunctionConcat(),
    "div": DslFunctionDiv(),
    "range": DslFunctionRange(),
}

GetTaskById = TypeVar("GetTaskById", bound=Task[Any])


def get_task_by_id(tasks: Iterable[GetTaskById], _id: str) -> GetTaskById:
    for task in tasks:
        if task.id == _id:
            return task
    raise Exception


ClientType = http_client.AsyncHttpClient[
    http_client.JsonResponse | http_client.TextResponse,  # now from models
    Never,
    Never
]


class HttpRequestExecutor:

    @singledispatchmethod
    @staticmethod
    def make_request(
            response: Any,
            execution_time: decimal.Decimal,
    ) -> models.JsonResponse | models.TextResponse:
        raise NotImplementedError(f"Cannot handle a {type(response)}")

    @make_request.register(http_client.JsonResponse)
    @staticmethod
    def _(response: http_client.JsonResponse, execution_time: decimal.Decimal) -> models.JsonResponse:
        return JsonResponse(
            headers=response.headers,
            body=json.dumps(response.body),
            status_code=response.status_code,
            execution_time=execution_time,
        )

    @make_request.register(http_client.TextResponse)
    @staticmethod
    def _(response: http_client.TextResponse, execution_time: decimal.Decimal) -> models.TextResponse:
        return TextResponse(
            headers=response.headers,
            body=json.dumps(response.body),
            status_code=response.status_code,
            execution_time=execution_time,
        )

    @staticmethod
    async def execute_with_lock(http_request: HttpRequest, lock: asyncio.Semaphore) -> models.JsonResponse | models.TextResponse:
        logger.debug(f"Start execute http request: {http_request.url}")

        async with lock:
            async with aiohttp.ClientSession() as session:
                client: ClientType = http_client.AsyncHttpClient(
                    http_client.AioHttpRequestExecution(session),
                    http_client.response_handler,
                    None
                )
                with timeit() as get_execution_time:
                    response = await client.execute_request(http_request)
                    return HttpRequestExecutor.make_request(response, get_execution_time())

    @staticmethod
    async def execute(http_request: HttpRequest) -> JsonResponse | TextResponse:
        logger.debug(f"Start execute http request: {http_request.url}")
        async with aiohttp.ClientSession() as session:
            client: ClientType = http_client.AsyncHttpClient(
                http_client.AioHttpRequestExecution(session),
                http_client.response_handler,
                None
            )
            with timeit() as get_execution_time:
                response = await client.execute_request(http_request)
                return HttpRequestExecutor.make_request(response, get_execution_time())

    @staticmethod
    def compile_http_request_template(job: HttpRequest, args: Iterable[str]) -> HttpRequest:
        job = copy.deepcopy(job)
        for idx, arg in enumerate(args, 1):

            if not isinstance(arg, str):
                logger.warning(f"Expected str, got {type(arg)} {arg}")

            arg = str(arg)
            tmpl = "!{{%s}}" % idx
            job.url = job.url.replace(tmpl, arg)

            if job.body:
                job.body = job.body.replace(tmpl, arg)

            job.headers = {k.replace(tmpl, arg): v.replace(tmpl, arg) for k, v in job.headers.items()}
        return job


class PipelineExecutor:

    @staticmethod
    async def execute(task: Task[Pipeline], tasks: list[Task[Pipeline] | Task[HttpRequest]]) -> list[PipelineJobResult]:
        pipeline_context: dict[str, Any] = {
            "tasks": tasks,
        }
        if task.payload.http_rps_limit:
            pipeline_context["http_rps_limiter"] = asyncio.Semaphore(task.payload.http_rps_limit)
            pipeline_context["strategy"] = "parallel"

        results: list[PipelineJobResult] = []
        assert task.payload.ast
        _, jobs = task.payload.ast

        execution_context: dict[str, dict[str, Any]] = {"pipeline_context": task.payload.pipeline_context}

        for job in jobs:
            results.extend(await PipelineExecutor.execute_pipeline_job(job, pipeline_context, execution_context))

        return results

    @singledispatchmethod
    @staticmethod
    async def execute_pipeline_job(
            job: Job[Product],
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            group_args_in: tuple[Any] | None = None
    ) -> list[PipelineJobResult]:

        raise NotImplementedError(f"Cannot handle a {type(job)}")

    @execute_pipeline_job.register
    @staticmethod
    async def _(
            job: Job[Product],
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            group_args_in: tuple[Any] | None = None
    ) -> list[PipelineJobResult]:

        product_args = [
            await PipelineExecutor.handle_argument_function(
                op.payload,
                pipeline_context,
                execution_context,
                group_args_in
            )
            for op in job.payload.cartesian_operands
        ]
        result: list[PipelineJobResult] = []
        parallels_strategy = "strategy" in pipeline_context and pipeline_context["strategy"] == "parallel"

        async def execute_jobs(jobs: list[Job[Product] | Job[CallFunction]], params: Any) -> list[PipelineJobResult]:
            nonlocal execution_context
            _result: list[PipelineJobResult] = []
            e = copy.deepcopy(execution_context)
            for _job in jobs:
                _result.extend(await PipelineExecutor.execute_pipeline_job(_job, pipeline_context, e, params))
            return _result

        if parallels_strategy:
            tasks = [execute_jobs(job.payload.pipeline, pipeline_positional_args) for pipeline_positional_args in
                     itertools.product(*product_args)]
            for i in await asyncio.gather(*tasks):
                result.extend(i)
        else:
            for pipeline_positional_args in itertools.product(*product_args):
                for sub_job in job.payload.pipeline:
                    result.extend(
                        await PipelineExecutor.execute_pipeline_job(sub_job, pipeline_context, execution_context, pipeline_positional_args))

        return result

    @execute_pipeline_job.register
    @staticmethod
    async def _(
            job: Job[CallFunction] | Job[CallFunction],
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            group_args: tuple[Any] | None = None
    ) -> list[PipelineJobResult]:
        args = []
        sub_task = get_task_by_id(pipeline_context["tasks"], job.payload.name)

        if not sub_task:
            raise SyntaxError(f"Undefined function: {job.payload.name}")

        tasks = []
        parallels_execution = "http_rps_limiter" in pipeline_context and pipeline_context["http_rps_limiter"]

        if parallels_execution:
            for i in job.payload.arguments:
                tasks.append(PipelineExecutor.handle_argument_function(i, pipeline_context, copy.deepcopy(execution_context), group_args))

            result = await asyncio.gather(*tasks)

            for i in result:
                if isinstance(i, list):
                    args.append(i[0])
                else:
                    args.append(i)
        else:
            for i in job.payload.arguments:
                result = await PipelineExecutor.handle_argument_function(i, pipeline_context, execution_context, group_args)

                if isinstance(result, list):
                    result = result[0]

                args.append(result)

        logger.debug(f"Execute job: {job.payload.name}, props: {args}")
        compiled_job = HttpRequestExecutor.compile_http_request_template(sub_task.payload, args)
        logger.debug(f"Request compiled: {job}")

        if parallels_execution:
            consumed_task = await HttpRequestExecutor.execute_with_lock(compiled_job, pipeline_context["http_rps_limiter"])
        else:
            consumed_task = await HttpRequestExecutor.execute(compiled_job)

        task_result = PipelineJobResult(
            id=str(uuid.uuid4()),
            created_at=str(datetime.datetime.now().isoformat()),
            task_id=sub_task.id,
            request=compiled_job,
            result=consumed_task,
            args=[str(i) for i in args],
        )
        execution_context[job.payload.name] = {}
        if isinstance(consumed_task, JsonResponse):
            for k, v in sub_task.payload.json_extractor_props.items():
                execution_context[job.payload.name][k] = json_extend_extractor(v, consumed_task.body)

        return [task_result]

    @staticmethod
    async def execute_function(
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            fn: CallFunction,
            group_args: tuple[Any] | None = None
    ) -> Any:
        args = []

        for i in fn.arguments:
            args.append(await PipelineExecutor.handle_argument_function(i, pipeline_context, execution_context, group_args))
        _fn = SYSTEM_FUNCTION_REGISTRY[fn.name]
        return await _fn(*args)

    @singledispatch
    @staticmethod
    async def handle_argument_function(
            arg: ResultFunction | CallFunction | PositionalArg,
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            product_args: tuple[Any] | None
    ) -> Any:
        raise NotImplementedError(f"Cannot handle argument type {type(arg)}")

    @handle_argument_function.register
    @staticmethod
    async def _(
            arg: ResultFunction,
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            product_args: tuple[Any] | None
    ) -> Any:
        return execution_context[arg.name][arg.property]

    @handle_argument_function.register
    @staticmethod
    async def _(
            arg: CallFunction,
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            product_args: tuple[Any] | None
    ) -> Any:
        return await PipelineExecutor.execute_function(pipeline_context, execution_context, arg, product_args)

    @handle_argument_function.register
    @staticmethod
    async def _(
            arg: PositionalArg,
            pipeline_context: dict[str, Any],
            execution_context: dict[str, dict[str, Any]],
            product_args: tuple[Any] | None
    ) -> Any:

        if product_args:
            return [product_args[arg.idx - 1]]

        raise Exception("Invalid positional argument")


PayloadTypes = (
        EmptyResponse |
        PipelineResult |
        JsonResponse |
        TextResponse
)

ConcreteTaskResult = (
        TaskResult[EmptyResponse] |
        TaskResult[PipelineResult] |
        TaskResult[JsonResponse] |
        TaskResult[TextResponse]
)

ExecuteTaskResult = AsyncGenerator[tuple[Task[Pipeline] | Task[HttpRequest], ConcreteTaskResult]]
ExecuteHttpTaskResult = tuple[Task[HttpRequest], TaskResult[EmptyResponse] |
                                                 TaskResult[JsonResponse] |
                                                 TaskResult[TextResponse]]


@singledispatch
def get_task_result_type(payload: PayloadTypes) -> type[ConcreteTaskResult]:
    raise NotImplementedError(f"Cannot handle type {type(payload)}")


@get_task_result_type.register
def _(_: JsonResponse) -> type[TaskResult[JsonResponse]]:
    return TaskResult[JsonResponse]


@get_task_result_type.register
def _(_: TextResponse) -> type[TaskResult[TextResponse]]:
    return TaskResult[TextResponse]


@get_task_result_type.register
def _(_: PipelineResult) -> type[TaskResult[PipelineResult]]:
    return TaskResult[PipelineResult]


@get_task_result_type.register
def _(_: EmptyResponse) -> type[TaskResult[EmptyResponse]]:
    return TaskResult[EmptyResponse]


def make_task_result(
        *,
        task_id: str,
        payload: PayloadTypes,
        request: HttpRequest | None = None,
        args: list[str] | None = None,
        is_throw: bool = False,
        error_description: str = "",
        status: str = "done",
) -> ConcreteTaskResult:
    payload_type = TaskPayloadTypesAssocInv.get(type(payload))

    if payload_type is None:
        raise ValueError(f"Unsupported payload type: {type(payload)}")

    cls = get_task_result_type(payload)

    return cls(
        id=str(uuid.uuid4()),
        created_at=str(datetime.datetime.now().isoformat()),
        task_id=task_id,
        payload=payload,
        payload_type=payload_type,
        request=request,
        args=args or [],
        is_throw=is_throw,
        error_description=error_description,
        status=status,
    )


class TaskScheduler:

    @staticmethod
    async def schedule(tasks: list[Task[Pipeline] | Task[HttpRequest]]) -> ExecuteTaskResult:
        _get_task_by_id = partial(get_task_by_id, tasks)

        for task in filter(lambda x: x.is_singleton, tasks):

            if isinstance(task.payload, Pipeline):
                async for x in TaskScheduler._execute_pipeline_task(task, tasks):
                    yield x
            elif isinstance(task.payload, HttpRequest):
                result = await TaskScheduler._execute_http_request_task(task)
                yield result
            else:
                raise NotImplementedError(...)

        logger.info(f"Execute tasks done, count tasks {len(tasks)}")

    @staticmethod
    async def _execute_pipeline_task(task: Task[Pipeline], tasks: list[Task[Pipeline] | Task[HttpRequest]]) -> ExecuteTaskResult:
        _get_task_by_id = partial(get_task_by_id, tasks)
        job_result_ids = []

        try:
            jobs = await PipelineExecutor.execute(task, tasks)
        except TimeoutError as e:
            yield task, make_task_result(
                task_id=task.id,
                payload=PipelineResult(task_id=task.id, status="fail"),
                is_throw=True,
                error_description="TimeoutError",
                status="fail"
            )
            return

        for job in jobs:
            sub_task = _get_task_by_id(job.task_id)
            result_id = str(uuid.uuid4())
            job_result_ids.append(result_id)
            yield sub_task, make_task_result(
                task_id=task.id,
                payload=job.result,
                request=job.request,
                args=job.args,
            )

        yield task, make_task_result(
            task_id=task.id,
            payload=PipelineResult(task_id=task.id, status="done", job_results=job_result_ids),
            status="done"
        )

    @staticmethod
    async def _execute_http_request_task(task: Task[HttpRequest]) -> tuple[Task[HttpRequest], ConcreteTaskResult]:
        is_throw = False
        error_description = ""
        payload: PayloadTypes = EmptyResponse()

        try:
            payload = await HttpRequestExecutor.execute(task.payload)
            logger.debug(f"Done execute http request")

        except TimeoutError as e:
            error_description = "TimeoutError"
            is_throw = True

        return task, make_task_result(
            task_id=task.id,
            payload=payload,
            request=task.payload,
            is_throw=is_throw,
            error_description=error_description,
            args=[],
            status="done"
        )
