from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import get_conn, init_db, row_to_dict, rows_to_dicts
from .schemas import DocumentCreate, EvalCaseBatchCreate, EvalCaseCreate, ProjectCreate, RunCreate
