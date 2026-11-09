"""Local read-only JSON API. No query execution, mutations, secrets or Docker access."""
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit, parse_qs
from config import Settings
from pipeline.analytics import records
from pipeline.cities import CITIES
from pipeline.operations import health


def handler(settings):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                url = urlsplit(self.path)
                args = parse_qs(url.query)
                city = args.get('city', ['Bengaluru'])[0]
                if city not in CITIES:
                    raise ValueError('Unsupported city')
                if url.path == '/health':
                    result = health(settings, city)
                elif url.path == '/v1/weather':
                    start = date.fromisoformat(args.get('start', [date.today().isoformat()])[0])
                    end = date.fromisoformat(args.get('end', [start.isoformat()])[0])
                    frame = records(settings, city, start, end, limit=1000)
                    result = {'city': city, 'limit': 1000, 'time_basis': 'UTC timestamps; date filters use city local dates', 'rows': json.loads(frame.to_json(orient='records', date_format='iso'))}
                else:
                    self.send_error(404)
                    return
                body = json.dumps(result, default=str, allow_nan=False).encode()
                self.send_response(200)
            except (ValueError, KeyError) as error:
                body = json.dumps({'error': str(error)}).encode()
                self.send_response(400)
            except Exception:
                body = b'{"error":"Warehouse unavailable or busy; retry later"}'
                self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    settings = Settings.from_env()
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(settings)).serve_forever()
