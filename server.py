

#!/usr/bin/env python3
"""
宫崎骏风格图片转换器 — 本地代理服务器
解决浏览器 CORS 跨域限制，代理转发 API 请求到中国 AI 大模型平台

用法：
    python server.py

然后浏览器打开 http://localhost:8765
"""

import http.server
import urllib.request
import urllib.error
import json
import ssl

PORT = 8765

# 后端 API 地址映射
BACKENDS = {
    'dashscope':   'https://dashscope.aliyuncs.com',
    'siliconflow': 'https://api.siliconflow.cn',
    'zhipu':       'https://open.bigmodel.cn',
}

FORBIDDEN_HEADERS = {
    'host', 'connection', 'transfer-encoding', 'proxy-connection',
    'proxy-authenticate', 'proxy-authorization', 'te', 'trailer',
    'upgrade', 'keep-alive',
}

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    """Serve static files + proxy /api/proxy/<backend>/<path> to remote APIs."""

    def do_GET(self):
        if self.path.startswith('/api/proxy/'):
            self.proxy_request('GET')
        elif self.path.startswith('/api/'):
            # Legacy path: /api/<backend>/<path> → redirect to /api/proxy/<backend>/<path>
            self.proxy_request('GET', legacy=True)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/proxy/') or self.path.startswith('/api/'):
            self.proxy_request('POST', legacy=self.path.startswith('/api/') and not self.path.startswith('/api/proxy/'))
        else:
            self.send_error(405)

    def do_OPTIONS(self):
        """Preflight CORS request."""
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def proxy_request(self, method, legacy=False):
        # Parse path:
        #   Standard: /api/proxy/dashscope/path/to/endpoint
        #   Legacy:   /api/dashscope/path/to/endpoint
        if legacy:
            # /api/<backend>/<path>  →  split 3 times
            parts = self.path.split('/', 3)
        else:
            # /api/proxy/<backend>/<path>  →  split 4 times
            parts = self.path.split('/', 4)

        min_len = 4 if legacy else 5
        if len(parts) < min_len:
            self.send_error(400, f'Invalid proxy path. Use /api/proxy/<backend>/<path>')
            return

        backend = parts[2] if legacy else parts[3]
        remote_path = '/' + (parts[3] if legacy else parts[4])

        if backend not in BACKENDS:
            self.send_error(400, f'Unknown backend: {backend}. Options: {list(BACKENDS.keys())}')
            return

        # Preserve query string
        query = ''
        if '?' in remote_path:
            remote_path, query = remote_path.split('?', 1)

        target_url = BACKENDS[backend] + remote_path
        if query:
            target_url += '?' + query

        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Forward headers (strip forbidden ones)
        forward_headers = {}
        for key, value in self.headers.items():
            if key.lower() not in FORBIDDEN_HEADERS:
                forward_headers[key] = value

        # Ensure host header matches target
        forward_headers['Host'] = urllib.parse.urlparse(target_url).netloc

        # Make the request
        try:
            req = urllib.request.Request(
                target_url,
                data=body,
                headers=forward_headers,
                method=method,
            )
            # Allow HTTPS
            ctx = ssl.create_default_context()
            resp = urllib.request.urlopen(req, context=ctx, timeout=120)
        except urllib.error.HTTPError as e:
            # Forward the error response
            self.send_response(e.code)
            self._send_cors()
            self.end_headers()
            try:
                self.wfile.write(e.read())
            except Exception:
                pass
            return
        except Exception as e:
            self.send_error(502, f'Proxy error: {e}')
            return

        # Send response
        self.send_response(resp.status)
        self._send_cors()
        # Forward response headers
        for key, value in resp.headers.items():
            if key.lower() not in FORBIDDEN_HEADERS:
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(resp.read())

    def _send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Max-Age', '86400')

    def log_message(self, format, *args):
        # Keep logs clean — only show proxied requests
        if '/api/' in (args[0] if args else ''):
            print(f'  → {args[0]}')


if __name__ == '__main__':
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    handler = ProxyHandler
    with http.server.HTTPServer(('0.0.0.0', PORT), handler) as httpd:
        print()
        print('  🏰  宫崎骏风格图片转换器 — 代理服务器已启动')
        print()
        print(f'  🌐  浏览器打开 →  http://localhost:{PORT}')
        print()
        print('  📡  代理转发规则：')
        for name, url in BACKENDS.items():
            print(f'      /api/proxy/{name}/*  →  {url}/*')
        print()
        print('  ⚠️  按 Ctrl+C 停止服务器')
        print()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n  👋 服务器已停止\n')
