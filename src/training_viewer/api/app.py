"""FastAPI 应用装配：路由、安全边界与本机静态前端。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import APP_DISPLAY_NAME, __version__
from ..application_paths import ApplicationPaths
from ..export.metric_exporters import build_builtin_metric_exporter_registry
from ..service import TrainingViewerService
from . import routes_artifacts, routes_catalog, routes_metrics, routes_stream

LOGGER = logging.getLogger("training_viewer.api")

_ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "::1", "testserver"}

_MISSING_FRONTEND_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Training Viewer 前端资源未构建</title>
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:60px auto;padding:0 20px;line-height:1.7;color:#1f2937}
code{background:#f3f4f6;padding:2px 6px;border-radius:4px}</style></head><body>
<h1>前端资源尚未构建</h1>
<p>后端 API 已经运行，但安装包中缺少 Web 前端静态文件。</p>
<p>在源码目录执行：</p>
<pre><code>cd frontend
npm install
npm run build</code></pre>
<p>然后重启 <code>training-viewer</code>。构建产物应位于 <code>src/training_viewer/web/</code>。</p>
<p>仍然可以访问 API 文档：<a href="/docs">/docs</a></p>
</body></html>"""


def create_application(
    paths: ApplicationPaths,
    service: TrainingViewerService | None = None,
    start_background_sync: bool = True,
) -> FastAPI:
    service = service or TrainingViewerService(paths)
    exporter_registry = build_builtin_metric_exporter_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_background_sync:
            service.start_background_sync()
        yield
        if start_background_sync:
            service.stop_background_sync()

    app = FastAPI(
        title=APP_DISPLAY_NAME,
        version=__version__,
        description="本机训练实验查看器 API；只读取用户添加的日志目录。",
        lifespan=lifespan,
    )
    app.state.service = service
    app.state.exporter_registry = exporter_registry
    app.state.paths = paths

    @app.middleware("http")
    async def restrict_to_local_access(request: Request, call_next):
        host = request.headers.get("host", "")
        hostname = host.rsplit(":", 1)[0] if ":" in host and not host.endswith("]") else host
        hostname = hostname.strip("[]").lower()
        if hostname and hostname not in _ALLOWED_HOSTNAMES:
            return JSONResponse(
                status_code=403,
                content={"detail": "Training Viewer 只接受本机访问；请通过 127.0.0.1 或 localhost 打开。"},
            )
        origin = request.headers.get("origin")
        if origin:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme not in ("http", "https")
                or parsed_origin.hostname not in _ALLOWED_HOSTNAMES
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "拒绝来自其它网站的跨域请求。"},
                )
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    app.include_router(routes_catalog.router)
    app.include_router(routes_metrics.router)
    app.include_router(routes_artifacts.router)
    app.include_router(routes_stream.router)

    web_dir = paths.web_dir
    assets_dir = web_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_index() -> Response:
        index_file = web_dir / "index.html"
        if index_file.is_file():
            return FileResponse(index_file, media_type="text/html")
        return HTMLResponse(_MISSING_FRONTEND_HTML, status_code=503)

    @app.get("/{unmatched_path:path}", include_in_schema=False)
    def serve_single_page_application(unmatched_path: str) -> FileResponse:
        if unmatched_path.startswith("api/") or unmatched_path.startswith("docs") or unmatched_path.startswith("openapi"):
            raise HTTPException(status_code=404, detail="接口不存在。")
        index_file = web_dir / "index.html"
        if index_file.is_file():
            return FileResponse(index_file, media_type="text/html")
        raise HTTPException(status_code=503, detail="前端资源尚未构建。")

    LOGGER.info("Training Viewer 应用已装配，数据目录：%s", paths.data_dir)
    return app
