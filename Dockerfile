# dbdelta as a container: docker run --rm -v "$PWD:/work" dbdelta diff current.sql desired.sql
FROM python:3.13-slim-bookworm AS build
RUN pip install --no-cache-dir uv==0.8.17
# Bytecode is compiled once here instead of at every start of the final image.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies change less often than the code, so they get their own layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --extra postgres
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --extra postgres

FROM python:3.13-slim-bookworm
COPY --from=build /app/.venv /app/.venv
RUN useradd --create-home --uid 1000 dbdelta
USER dbdelta
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /work
ENTRYPOINT ["dbdelta"]
CMD ["--help"]
