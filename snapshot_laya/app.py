from contextlib import asynccontextmanager
import os
from pathlib import Path
import threading
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from .live import Live
from .explorer import Explorer

manager=Live()
explorer=Explorer(manager)
busy=False
task_lock=threading.Lock()
stop=threading.Event()
PORT=int(os.environ.get('SNAPSHOT_LAYA_PORT','18766'))
server=None


def submit(fn):
    global busy
    with task_lock:
        if busy: raise HTTPException(409,'Hay una operación en curso; esperá a que termine.')
        busy=True
    def run():
        global busy
        try:
            manager.error=None
            fn()
        except Exception as exc:
            manager.error=str(exc)[:700]
        finally:
            busy=False
    threading.Thread(target=run,daemon=True).start()
    return {'accepted':True}


def watch():
    while not stop.wait(3):
        if busy or not (manager.session or explorer.running): continue
        if not manager.lock.acquire(blocking=False): continue
        try:
            if not busy:
                manager.observe()
                explorer.tick()
        except Exception as exc:
            manager.error=str(exc)[:700]
            if explorer.running: explorer.fail(manager.error)
        finally:
            manager.lock.release()


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=watch,daemon=True).start()
    yield
    stop.set()
    explorer.pause()
    if manager.session:
        try: manager.finish(True,advance=False)
        except Exception: pass  # evidence is saved before an upstream close is attempted


app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None)


@app.middleware('http')
async def local(request:Request,call_next):
    origin=request.headers.get('origin')
    if request.headers.get('host','').split(':')[0] not in ('127.0.0.1','localhost','testserver') or origin and origin not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):
        return JSONResponse({'detail':'Solo se aceptan solicitudes locales.'},status_code=403)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'"
    return response


@app.get('/',response_class=HTMLResponse)
def index(): return Path(__file__).with_name('index.html').read_text(encoding='utf-8')


@app.get('/api/health')
def health(): return {'app':'Snapshot-Laya','version':'0.3.1','model_loaded':manager.model.agent is not None}


@app.post('/api/shutdown')
def shutdown():
    if server is None: raise HTTPException(503,'Servidor no administrado.')
    explorer.pause()
    server.should_exit=True
    return {'stopping':True}


@app.get('/api/state')
def state(): return {**manager.state(),'busy':busy,'explorer':explorer.state()}


class Queue(BaseModel):
    urls:list[str]=Field(min_length=1,max_length=20)
    auto_close:bool=False


class Act(BaseModel):
    snapshot_id:str
    control_id:str
    visual_reviewed:bool=False
    role:str|None=None


class Dismiss(BaseModel): ref:str
class Finish(BaseModel): incomplete:bool=False


@app.post('/api/queue')
def queue(body:Queue):
    if explorer.running: raise HTTPException(409,'Pausá el recorrido antes de abrir una cola manual.')
    return submit(lambda: manager.enqueue(body.urls,body.auto_close))


class Explore(BaseModel):
    url:str
    ante_rounds:int=Field(default=2,ge=1,le=5)


@app.post('/api/explore/start')
def explore_start(body:Explore): return submit(lambda: explorer.start(body.url,body.ante_rounds))


@app.post('/api/explore/pause')
def explore_pause(): return submit(explorer.pause)


@app.post('/api/explore/resume')
def explore_resume(): return submit(explorer.resume)


@app.get('/api/explore/report')
def explore_report():
    if not explorer.tree.data: raise HTTPException(404,'No hay recorrido guardado.')
    return JSONResponse(explorer.state(),headers={'Content-Disposition':'attachment; filename="snapshot-ramas.json"'})


@app.post('/api/refresh')
def refresh(): return submit(manager.observe)


@app.post('/api/act')
def act(body:Act):
    if explorer.running: raise HTTPException(409,'Pausá el recorrido antes de una acción manual.')
    return submit(lambda: manager.act(body.snapshot_id,body.control_id,body.visual_reviewed,body.role))


@app.post('/api/dismiss')
def dismiss(body:Dismiss): return submit(lambda: manager.dismiss(body.ref))


@app.post('/api/finish')
def finish(body:Finish):
    explorer.pause()
    return submit(lambda: manager.finish(body.incomplete))


@app.get('/api/images/{key}')
def image(key:str):
    path=manager.images.get(key)
    if path is None: raise HTTPException(404,'Captura no disponible.')
    return FileResponse(path,media_type='image/jpeg')


@app.get('/api/reports/{identifier}')
def report(identifier:str):
    report=next((r for r in manager.reports if r['id']==identifier),None)
    if report is None: raise HTTPException(404,'Informe no disponible.')
    return JSONResponse(report,headers={'Content-Disposition':'attachment; filename="snapshot-laya-report.json"'})


@app.get('/api/reports/{identifier}/har')
def raw_har(identifier:str):
    report=next((r for r in manager.reports if r['id']==identifier),None)
    name=(report or {}).get('har',{}).get('cleanup',{}).get('har')
    if not name: raise HTTPException(404,'HAR no disponible.')
    path=Path(name).resolve()
    if not path.is_relative_to((Path.home()/'.hardfire'/'fuzzer').resolve()) or not path.is_file():
        raise HTTPException(404,'HAR no disponible.')
    return FileResponse(path,media_type='application/json',filename='snapshot-'+identifier+'.har')


def main():
    global server
    import uvicorn
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=PORT,log_level='warning'))
    server.run()
