# AGENTS.md

## Project
Small FastAPI service for the panorama / point-cloud processing pipeline. It hands out work
(`status == 0`) and accepts status updates, backed by PostgreSQL/PostGIS. Entry point is
`main.py`; `server.py` is the uvicorn launcher. There is no README, test suite, linter,
typecheck config, or CI.

## Read this first: the checkout is incomplete
- `services/__init__.py` imports `dao` (`query_session`, `action_session`, and models such as
  `PanoramaGroup`, `TaskPnt`, `PointCloud`, `Panorama`). **No `dao/` package exists in this
  checkout**, and it is not in `requirements.txt` or the checked-in `.venv`. `import main`
  fails with `ModuleNotFoundError: No module named 'dao'` until it is restored or provided.
  Do not paper over this by deleting the imports or inventing models.
- `services/__init__.py` also imports `services.pointclouds` and `services.panoramas`; only
  `.pyc` files remain under `services/__pycache__/`. Any change to those areas requires
  recovering the source first.
- `utils/file_util.py` does `from utils import log`, but `utils/__init__.py` is empty. Fix the
  import if you use that module.
- `sql/init.sql` is not the ORM source of truth: it creates only `task_pnt` with a PK on
  `loc`, while `PntTaskService` queries `TaskPnt.id`. The real models live in `dao`.

## Setup and run
- Intended runtime is Python 3.12 with pydantic **v1**. Do not reuse the committed `.venv`:
  it was built on Linux (`/home/xmap/...`), its `bin/python` is not executable on macOS, and
  it contains packages that are not in `requirements.txt`.
- Start fresh from the repo root:
  ```sh
  python3.12 -m venv .venv
  . .venv/bin/activate
  pip install -r requirements.txt
  python server.py
  ```
- The server binds `0.0.0.0:8080` with `reload=True`. Check it with
  `curl localhost:8080/healthcheck`; Swagger is at `/task/docs`, OpenAPI at
  `/task/openapi.json`.
- Without the launcher: `uvicorn main:app --host 0.0.0.0 --port 8080 --reload`.
- No automated verification exists. After edits, at minimum start the app and hit the affected
  endpoint; `python -m compileall` only proves syntax.

## Architecture
- `main.py` holds every route and a catch-all exception handler that turns any exception into
  a 500 `{"error_code": 500, "message": ...}`. Endpoint summaries/comments are Chinese.
- `config.py` uses pydantic v1 `BaseSettings`, so settings come from env vars named exactly
  `POSTGIS_DATABASE_URL`, `POSTGIS_DATABASE_POOL_SIZE`, `POSTGIS_DATABASE_POOL_RECYCLE`,
  `POSTGIS_DATABASE_PRINT_SQL`. The default DSN is `postgresql://hkd:hkd@192.168.1.66:5432/hkd`.
  `configs()` is `lru_cache`d — restart the process after changing env. Migrating to pydantic
  v2 requires switching to `pydantic-settings` (`BaseSettings` moved).
- `services/__init__.py` defines `BaseService`/`Pagination`, then creates import-time
  singletons (`task_service`, `pnt_task_service`, ...). The modules at the bottom import
  `BaseService`, so keep new service imports at the bottom to avoid the circular-import break.
- Service methods open their own `with query_session()` / `with action_session()` context.
  Keep that pattern; do not share a session across calls.
- `/img/*` routes actually operate on `PanoramaGroup` (panorama groups), not individual
  `Panorama` rows. `/pnt/*` routes operate on `TaskPnt`. Responses are ORM objects or
  `{"val": ...}` wrappers; there are no response schemas.
- `get_todo()` is a first-match query with no ordering or locking, so concurrent claimers can
  receive the same row. Do not treat claiming as atomic without changing it.
- `utils/` is a grab-bag of helpers (Word, zip/shapefile, coordinates, logging); only
  `utils.log_util` is used by the code that is present. Some modules import `numpy`,
  `shapely`, `pyproj`, `pyshp`, and `python-docx`, none of which are in `requirements.txt` —
  install them only if you touch those modules.

## API routing gotcha
Routes match in declaration order. `GET /pnt/{batch}/{loc}` is declared before
`GET /pnt/{ctype}/head`, so the latter is unreachable for two-segment `/pnt/...` paths. When
adding `/pnt` routes, put literal/specific paths before parameterized ones.

## Docker
- `Dockerfile-rt` builds the Ubuntu 22.04 runtime and installs `requirements.txt` from the
  Aliyun mirror. `Dockerfile` starts from the private base
  `192.168.1.11:8085/tasks-rt:latest`, copies the source, runs
  `python -m compileall -b /opt/`, and executes `python server.pyc` on port 8080. Rebuild
  `tasks-rt` only when requirements change; rebuild `tasks` for source changes.
- There is no `.dockerignore`, so a local build sends `.venv`, `.idea`, and `__pycache__` as
  build context.
