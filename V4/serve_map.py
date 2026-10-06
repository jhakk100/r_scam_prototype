"""Serve the final standalone case map on loopback only."""
import argparse,json,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
HERE=Path(__file__).resolve().parent
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?',1)[0] not in ('/','/case-map-3d.html'):
            self.send_error(404);return
        data=(HERE/'map/case-map-3d.html').read_bytes()
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args();server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    info={'url':f'http://127.0.0.1:{server.server_port}/case-map-3d.html?revision=d03-final',
        'pid':os.getpid(),'html':str(HERE/'map/case-map-3d.html'),'loopback_only':True}
    (HERE/'map/server.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(info['url'],flush=True);server.serve_forever()
