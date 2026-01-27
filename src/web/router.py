from typing import Callable, Dict, List, Tuple
from http.server import BaseHTTPRequestHandler
import json
import logging

logger = logging.getLogger(__name__)

class Router:
    def __init__(self):
        # paths: method -> path -> handler
        self.routes: Dict[str, Dict[str, Callable]] = {
            "GET": {},
            "POST": {}
        }

    def add_route(self, method: str, path: str, handler: Callable):
        method = method.upper()
        if method not in self.routes:
            self.routes[method] = {}
        self.routes[method][path] = handler

    def get(self, path: str):
        def decorator(func: Callable):
            self.add_route("GET", path, func)
            return func
        return decorator

    def post(self, path: str):
        def decorator(func: Callable):
            self.add_route("POST", path, func)
            return func
        return decorator

    def dispatch(self, handler: BaseHTTPRequestHandler):
        path = handler.path.split('?')[0]  # Simple path matching
        method = handler.command.upper()

        if method in self.routes and path in self.routes[method]:
            try:
                self.routes[method][path](handler)
            except Exception as e:
                logger.error(f"Error handling {method} {path}: {e}")
                self._send_error(handler, 500, str(e))
        else:
            self._send_error(handler, 404, "Not Found")

    def _send_error(self, handler: BaseHTTPRequestHandler, code: int, message: str):
        handler.send_response(code)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": message}).encode('utf-8'))

# Global router instance
_router = Router()

def get_router() -> Router:
    return _router
