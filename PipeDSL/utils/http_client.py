from abc import abstractmethod
from decimal import Decimal
from typing import Callable, Awaitable, Any, Protocol

import aiohttp
from aiohttp import ClientSession, ClientResponse
from multidict import istr
from pydantic import BaseModel

from PipeDSL.models import HttpRequest


class HttpResponse(BaseModel):
    headers: dict[str, str]
    status_code: int
    execution_time: Decimal | None = None


class TextResponse(HttpResponse):
    body: str | None


class JsonResponse(HttpResponse):
    body: Any


class RequestExecutor(Protocol):
    @abstractmethod
    async def execute_request(self, request: HttpRequest) -> Any: ...


class AioHttpRequestExecution:
    def __init__(self, session: ClientSession):
        self.session = session

    async def execute_request(self, request: HttpRequest) -> ClientResponse:
        match request.method.lower():
            case "get":
                return await self._get(request, self.session)
            case "post":
                return await self._post(request, self.session)
            case "put":
                return await self._put(request, self.session)
            case "delete":
                return await self._delete(request, self.session)
        raise NotImplementedError

    async def _get(self, request: HttpRequest, session: ClientSession) -> ClientResponse:
        return await session.get(request.url, headers=request.headers, timeout=aiohttp.ClientTimeout(request.timeout))

    async def _post(self, request: HttpRequest, session: ClientSession) -> ClientResponse:
        return await session.post(request.url, data=request.body, headers=request.headers, timeout=aiohttp.ClientTimeout(request.timeout))

    async def _delete(self, request: HttpRequest, session: ClientSession) -> ClientResponse:
        return await session.delete(request.url, data=request.body, headers=request.headers, timeout=aiohttp.ClientTimeout(request.timeout))

    async def _put(self, request: HttpRequest, session: ClientSession) -> ClientResponse:
        return await session.put(request.url, data=request.body, headers=request.headers, timeout=aiohttp.ClientTimeout(request.timeout))


class AsyncHttpClient[ResponseHandlerRetType, RequestExecutorType, CredentialProviderRetType]:
    def __init__(
            self,
            request_executor: RequestExecutor,
            response_handler: Callable[[ClientResponse], Awaitable[ResponseHandlerRetType]],
            credential_provider: Callable[[HttpRequest], CredentialProviderRetType] | None = None,
    ):
        self.request_executor = request_executor
        self.credential_provider = credential_provider
        self.response_handler = response_handler

    async def execute_request(self, request: HttpRequest) -> ResponseHandlerRetType:
        response: ClientResponse = await self.request_executor.execute_request(request)
        return await self.response_handler(response)


def none_credential_provider(http_request: HttpRequest) -> None:
    return None


async def response_handler(client_response: ClientResponse) -> TextResponse | JsonResponse:
    if "application/json" in client_response.headers.get(istr("content-type"), "").lower():
        response = await client_response.json()
        client_response.close()
        return JsonResponse(headers=dict(client_response.headers), status_code=client_response.status, body=response)

    response = await client_response.text()
    client_response.close()
    return TextResponse(headers=dict(client_response.headers), status_code=client_response.status, body=response)
