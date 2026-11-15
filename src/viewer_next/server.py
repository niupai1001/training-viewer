import json
import secrets
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .store import Store


def create_app(directory, token=None):
    store = Store(directory)
    token = token or secrets.token_urlsafe(32)
    jobs = {}

    @asynccontextmanager
    async def lifespan(app):
        store.start()
        yield
        store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.token = token

    @app.middleware('http')
    async def guard(request: Request, call_next):
        host = request.headers.get('host','')
        if host.split(':')[0] != '127.0.0.1':
            return JSONResponse({'detail':'Host forbidden'},403)
        origin = request.headers.get('origin')
        if origin and origin != f'http://{host}':
            return JSONResponse({'detail':'Origin forbidden'},403)
        if request.url.path.startswith('/api/') and request.headers.get('x-viewer-token') != token:
            return JSONResponse({'detail':'Token required'},403)
        try:
            response = await call_next(request)
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response
        except (ValueError, OSError, KeyError) as error:
            return JSONResponse({'detail':str(error)},400)

    @app.get('/api/v2/health')
    def health():
        with store.lock:
            issues = [dict(r) for r in store.db.execute('SELECT * FROM issues LIMIT 100')]
        return dict(application='training-viewer-next',progress=store.progress,issues=issues,
                    active_root=store.active_root())

    @app.get('/api/v2/roots')
    def roots():
        return store.roots()

    @app.post('/api/v2/previews')
    def preview(body: dict):
        path = Path(body['path']).resolve()
        if not path.is_dir():
            raise HTTPException(400,'目录不存在或不是目录')
        job_id = secrets.token_hex(8)
        job = dict(done=False,items=[],issues=[])
        jobs[job_id] = job
        def scan():
            from .protocol import validate
            try:
                for file in path.rglob('run.json'):
                    try:
                        meta = validate(json.loads(file.read_text(encoding='utf-8')))
                        job['items'].append(dict(path=str(file),experiment=meta['experiment']['name'],variant=meta['variant']['name']))
                    except Exception as error:
                        job['issues'].append(dict(path=str(file),message=str(error)[:300]))
            except Exception as error:
                job['issues'].append(dict(path=str(path),message=str(error)))
            job['done'] = True
        threading.Thread(target=scan,daemon=True).start()
        return dict(id=job_id)

    @app.get('/api/v2/previews/{job_id}')
    def preview_status(job_id: str):
        if job_id not in jobs:
            raise HTTPException(404,'预览已失效')
        return jobs[job_id]

    @app.post('/api/v2/roots')
    def add(body: dict):
        return dict(path=store.add(body['path']))

    @app.put('/api/v2/roots/active')
    def select_root(body: dict):
        store.select_root(body['path'])
        return dict(path=body['path'])

    @app.delete('/api/v2/roots')
    def remove(body: dict):
        store.remove(body['path'])
        return dict(ok=True)

    @app.get('/api/v2/runs')
    def runs(limit: int=50, offset: int=0):
        return store.runs(max(1,min(100,limit)),max(0,offset),current_folder=True)

    @app.get('/api/v2/runs/{rid}')
    def detail(rid: str):
        try:
            return {**store.detail(rid), 'training_seconds': store.training_seconds(rid)}
        except KeyError:
            raise HTTPException(404,'训练记录不存在')

    @app.get('/api/v2/runs/{rid}/summary')
    def summary(rid: str):
        return store.summary(rid)

    @app.get('/api/v2/runs/{rid}/curve')
    def curve(rid: str,key: str,session: str|None=None,axis: str='step',low: float|None=None,high: float|None=None,budget: int=2000):
        return store.curve(rid,key,session,axis,low,high,budget)

    @app.get('/api/v2/settings/{key:path}')
    def setting(key: str):
        return store.setting(key)

    @app.put('/api/v2/settings/{key:path}')
    def save_setting(key: str, body: dict):
        return store.setting(key,body['value'],True)

    @app.get('/api/v2/writer')
    def writer():
        return FileResponse(Path(__file__).with_name('writer.py'),filename='tvlp_writer.py')

    web = Path(__file__).with_name('web')
    if (web/'assets').is_dir():
        app.mount('/assets',StaticFiles(directory=web/'assets'),name='assets')

    @app.get('/')
    def index():
        return HTMLResponse((web/'index.html').read_text(encoding='utf-8'))
    return app
