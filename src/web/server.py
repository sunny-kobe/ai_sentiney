import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from src.web.router import get_router

logger = logging.getLogger(__name__)

class WebRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        get_router().dispatch(self)

    def do_POST(self):
        get_router().dispatch(self)

    def log_message(self, fmt, *args):
        # Silence default access logs or route to our logger
        pass

class WebServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def run(self):
        """Blocking run."""
        self.server = ThreadingHTTPServer((self.host, self.port), WebRequestHandler)
        logger.info(f"WebUI started at http://{self.host}:{self.port}")
        print(f"WebUI started at http://{self.host}:{self.port}")
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def start_background(self):
        """Non-blocking run in a separate thread."""
        self.server = ThreadingHTTPServer((self.host, self.port), WebRequestHandler)
        
        def serve():
            logger.info(f"WebUI background started at http://{self.host}:{self.port}")
            try:
                self.server.serve_forever()
            except Exception as e:
                logger.error(f"WebUI server error: {e}")

        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
