import asyncio
import contextlib
import decimal
import itertools
import json
import time
from collections.abc import Iterator, Generator, Callable, Awaitable
from functools import wraps
from typing import TypeVar, List, Iterable, Generic, Any, ParamSpec, Tuple, Dict

from jsonpath_ng import parse
from jsonpath_ng.ext import parse as parse_ext

T = TypeVar('T')


def to_2d_array(items: List[Any]) -> Generator[List[T]]:
    for item in items:
        if isinstance(item, list):
            if isinstance(item[0], list):
                yield from to_2d_array(item)
            else:
                yield item


P = TypeVar('P')


def check_duplicate(items: Iterable[P]) -> P | None:
    exist_items = set()
    for item in items:
        if item not in exist_items:
            exist_items.add(item)
            continue
        return item

    return None


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file:
        return str(file.read())


def json_extractor(path: str, serialized_json: str) -> str:
    jsonpath_expr = parse(path)
    for match in jsonpath_expr.find(json.loads(serialized_json)):
        return str(match.value)

    return ""


def json_extend_extractor(path: str, serialized_json: str) -> list[str]:
    jsonpath_expr = parse_ext(path)
    result = []
    for match in jsonpath_expr.find(json.loads(serialized_json)):
        result.append(str(match.value))

    return result


TBufferedWriterItem = TypeVar("TBufferedWriterItem")


class BufferedWriter(Generic[TBufferedWriterItem]):
    def __init__(
            self,
            read_fn: Callable[[], Awaitable[list[TBufferedWriterItem]]],
            write_fn: Callable[[list[TBufferedWriterItem]], Awaitable[None]],
            buff_size: int = 10
    ):
        self.read_fn: Callable[[], Awaitable[list[TBufferedWriterItem]]] = read_fn
        self.write_fn: Callable[[list[TBufferedWriterItem]], Awaitable[None]] = write_fn
        self.saved_items: list[TBufferedWriterItem] = []
        self.tmp: list[TBufferedWriterItem] = []
        self.buff_size: int = buff_size
        self.lock = asyncio.Lock()
        self.init = False

    async def read(self) -> Iterator[TBufferedWriterItem]:
        if not self.init:
            self.saved_items = await self.read_fn()
            self.init = True

        return itertools.chain(self.saved_items, self.tmp)

    async def write(self, item: TBufferedWriterItem) -> None:
        async with self.lock:
            self.tmp.append(item)

            if len(self.tmp) >= self.buff_size:
                await self.write_fn(self.tmp)
                self.saved_items.extend(self.tmp)
                self.tmp = []

    async def flush(self) -> None:
        await self.write_fn(self.tmp)


Q = ParamSpec('Q')
R = TypeVar('R')


def async_cache(async_fn: Callable[Q, Awaitable[R]]) -> Callable[Q, Awaitable[R]]:
    """Async version of functools.lru_cache (unbounded, per-function cache)."""
    cache: Dict[Tuple[Any, ...], R] = {}
    lock = asyncio.Lock()

    @wraps(async_fn)
    async def inner(*args: Q.args, **kwargs: Q.kwargs) -> R:
        # Sort kwargs for consistent cache key
        cache_key = (args, tuple(sorted(kwargs.items())))
        if cache_key in cache:
            return cache[cache_key]

        async with lock:
            if cache_key not in cache:
                cache[cache_key] = await async_fn(*args, **kwargs)
        return cache[cache_key]

    return inner


@contextlib.contextmanager
def timeit() -> Generator[Callable[[], decimal.Decimal], None, None]:
    perf_start: float = time.perf_counter()

    def result() -> decimal.Decimal:
        elapsed_time = time.perf_counter() - perf_start
        return decimal.Decimal(elapsed_time).quantize(decimal.Decimal('.001'), rounding=decimal.ROUND_DOWN)

    yield result
