#!/usr/bin/env python3
"""
state_server.py — Serve /tmp/pipeline_state.json over HTTP on port 8765.
Run once on VPS: nohup python3 state_server.py &
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

STATE_FILE = Path('/tmp/pipeline_state.json')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/pipeline_state.json':
            self.send_response(404); self.end_headers(); return
        data = STATE_FILE.read_bytes() if STATE_FILE.exists() else b'{}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a): pass  # silence access logs

if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 8766), Handler).serve_forever()
