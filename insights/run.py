"""Linux entrypoint adapting deployment addresses only; upstream business code unchanged."""
import os
import ipaddress
from pathlib import Path
import signal
import threading
from http.server import ThreadingHTTPServer
import server as service


def main():
    key = Path(os.environ['MANAGEMENT_KEY_FILE']).read_text(encoding='utf-8').strip()
    if len(key) < 32 or any(c.isspace() for c in key):
        raise ValueError('Invalid management key file; value is never printed')
    origins = os.environ.get('INSIGHTS_ALLOWED_ORIGINS','').split(',')
    for origin in filter(None, origins):
        parsed = service.urllib.parse.urlsplit(origin)
        try:
            loopback = ipaddress.ip_address(parsed.hostname or '').is_loopback
        except ValueError:
            loopback = parsed.hostname=='localhost'
        if not (parsed.scheme=='https' or (parsed.scheme=='http' and loopback)) or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
            raise ValueError('Only explicit HTTPS or loopback HTTP origins are accepted')
        _ = parsed.port  # Reject malformed ports while loading configuration.
        service.SAFE_ORIGINS.add(origin)
    keeper = service.Keeper(service.Store(Path(os.environ.get('INSIGHTS_DB','/data/usage.sqlite'))),
                            key, os.environ.get('CPA_URL','http://127.0.0.1:8317').rstrip('/'))
    server = ThreadingHTTPServer((os.environ.get('INSIGHTS_BIND','127.0.0.1'),int(os.environ.get('INSIGHTS_PORT','8320'))),
                                service.make_handler(keeper,Path(os.environ.get('MANAGEMENT_HTML','/opt/cpa/static/management.html'))))
    stopped = threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stopped.set())
    worker = threading.Thread(target=keeper.run,daemon=True)
    http = threading.Thread(target=server.serve_forever,daemon=True)
    worker.start(); http.start()
    print('CPA Personal statistics ready',flush=True)
    stopped.wait()
    keeper.stop.set(); server.shutdown(); server.server_close(); worker.join(timeout=15)


if __name__=='__main__':
    main()
