import asyncio
import uuid

from PipeDSL.lexer import CallFunction, ResultFunction
from PipeDSL.models import HttpRequest, TaskPayloadTypes
from PipeDSL.services.task_scheduler import DslFunctionUuid, DslFunctionConcat, HttpRequestExecutor, PipelineExecutor


def test_compile_http_request():
    tmpl_request = HttpRequest(url="!{{1}}", headers={"!{{2}}": "!{{3}}"}, method="post", body="!{{4}}")
    compiled_request = HttpRequestExecutor.compile_http_request_template(tmpl_request, [f"test{i}" for i in range(1, 5)])
    assert compiled_request == HttpRequest(url="test1", headers={"test2": "test3"}, method="post", body="test4")


def test_compile_http_request_empty():
    tmpl_request = HttpRequest(url="", headers={}, method="get")
    compiled_request = HttpRequestExecutor.compile_http_request_template(tmpl_request, [f"test{i}" for i in range(1, 5)])
    assert compiled_request == HttpRequest(url="", headers={}, method="get")


def test_compile_http_request_int():
    tmpl_request = HttpRequest(url="!{{1}}", headers={"!{{2}}": "!{{3}}"}, method="post", body="!{{4}}")
    compiled_request = HttpRequestExecutor.compile_http_request_template(tmpl_request, [str(i) for i in range(1, 5)])
    assert compiled_request == HttpRequest(url="1", headers={"2": "3"}, method="post", body="4")


def test_compile_http_request_one_param():
    tmpl_request = HttpRequest(url="!{{1}}", headers={}, method="post", body="")
    compiled_request = HttpRequestExecutor.compile_http_request_template(tmpl_request, [f"test1"])
    assert compiled_request == HttpRequest(url="test1", headers={}, method="post", body="")


def test_uuid_function():
    r = DslFunctionUuid()
    result = asyncio.run(r())
    assert type(result) == str
    assert len(result) > 32


def test_concat_function():
    r = DslFunctionConcat()
    result = asyncio.run(r("a", "b", "c"))
    assert result == "abc"
    result = asyncio.run(r("a"))
    assert result == "a"


def test_execute_function():
    f = CallFunction(name="uuid", arguments=[])
    result = asyncio.run(PipelineExecutor.execute_function({}, {}, f))
    assert result is not None
    assert len(result) == len(str(uuid.uuid4()))


def test_execute_function_2():
    f = CallFunction(name="concat", arguments=[CallFunction(name="uuid", arguments=[])])
    result = asyncio.run(PipelineExecutor.execute_function({}, {}, f))
    assert result is not None
    assert len(result) == len(str(uuid.uuid4()))


def test_execute_function_3():
    f = CallFunction(name="concat", arguments=[ResultFunction(name="a", property="_a"), ResultFunction(name="b", property="_b")])
    result = asyncio.run(PipelineExecutor.execute_function({"a": {"_a": "1"}, "b": {"_b": "2"}}, {"a": {"_a": "1"}, "b": {"_b": "2"}}, f))
    assert result is not None
    assert result == "12"


def test_resolve_payload_types():
    assert TaskPayloadTypes.HTTP_JSON == "http_json"
    assert TaskPayloadTypes.HTTP_TEXT == "http_text"
    assert TaskPayloadTypes.PIPELINE == "pipeline"
    assert TaskPayloadTypes.EMPTY == "empty"
