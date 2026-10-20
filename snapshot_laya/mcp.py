import json
import threading
from urllib.request import Request,urlopen
from urllib.parse import urlsplit


def decode_rpc(text):
    text=text.strip()
    if text.startswith('{'): return json.loads(text)
    messages=[]
    for block in text.replace('\r\n','\n').split('\n\n'):
        data='\n'.join(line[5:].strip() for line in block.splitlines() if line.startswith('data:'))
        if data: messages.append(json.loads(data))
    replies=[m for m in messages if 'result' in m or 'error' in m]
    if not replies: raise RuntimeError('HardFire no devolvió una respuesta MCP válida.')
    return replies[-1]


class MCP:
    def __init__(self,url='http://127.0.0.1:8765/mcp'):
        parts=urlsplit(url)
        if parts.scheme!='http' or parts.hostname not in ('127.0.0.1','localhost'):
            raise ValueError('El servidor HardFire debe estar en loopback local.')
        self.url=url
        self.session=None
        self.counter=0
        self.lock=threading.RLock()
        self.initialized=False

    def rpc(self,method,params):
        self.counter+=1
        headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2024-11-05'}
        if self.session: headers['Mcp-Session-Id']=self.session
        request=Request(self.url,data=json.dumps({'jsonrpc':'2.0','id':self.counter,'method':method,'params':params}).encode(),headers=headers)
        with urlopen(request,timeout=90) as response:
            self.session=response.headers.get('Mcp-Session-Id',self.session)
            result=decode_rpc(response.read().decode())
        if result.get('error'): raise RuntimeError(str(result['error']))
        return result.get('result',{})

    def call(self,name,arguments):
        with self.lock:
            if not self.initialized:
                self.rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'Snapshot-Laya','version':'0.1.0'}})
                self.initialized=True
            result=self.rpc('tools/call',{'name':name,'arguments':arguments})
            texts=[c['text'] for c in result.get('content',[]) if c.get('type')=='text']
            if result.get('isError'): raise RuntimeError('\n'.join(texts))
            for text in texts:
                try: return json.loads(text)
                except ValueError: continue
            if result.get('structuredContent'): return result['structuredContent']
            raise RuntimeError('Respuesta sin datos estructurados de '+name)
