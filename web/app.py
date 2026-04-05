"""LLM-KB Web App — FastAPI 入口"""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

app = FastAPI(title="LLM Knowledge Base", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
from web.api import config, ingest, compile, wiki, query

app.include_router(config.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(compile.router, prefix="/api")
app.include_router(wiki.router, prefix="/api")
app.include_router(query.router, prefix="/api")

# 静态文件
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/{path:path}")
async def spa_fallback(path: str):
    """SPA fallback — 所有非 API 路由返回 index.html"""
    if path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(404)
    return FileResponse(str(STATIC_DIR / "index.html"))
