import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

port=int(os.environ.get('SNAPSHOT_LAYA_PORT','18766'))
url=f'http://127.0.0.1:{port}'
def ready():
    try:
        with urlopen(url+'/api/health',timeout=1) as response:
            return json.load(response).get('app')=='Snapshot-Laya'
    except Exception: return False

if ready():
    webbrowser.open(url)
    raise SystemExit(0)
process=subprocess.Popen([sys.executable,'-m','snapshot_laya'],cwd=Path(__file__).parent,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
try:
    for _ in range(100):
        if process.poll() is not None: raise SystemExit('No se pudo iniciar Snapshot-Laya.')
        if ready():
            webbrowser.open(url)
            break
        time.sleep(.2)
    process.wait()
except KeyboardInterrupt:
    if process.poll() is None:
        # Uvicorn handles SIGBREAK on Windows and runs lifespan cleanup.
        # TerminateProcess would bypass evidence saving and owned-tab cleanup.
        process.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGINT)
        process.wait()
