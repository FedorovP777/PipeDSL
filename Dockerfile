# Только если тебе действительно нужен Docker для сборки пакета
FROM python:3.13-alpine

WORKDIR /PipeDSL

COPY pyproject.toml README.md ./

COPY PipeDSL/ ./PipeDSL/

RUN python -m pip install --upgrade pip setuptools hatchling build twine
