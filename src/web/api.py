import json
import asyncio
from http.server import BaseHTTPRequestHandler
from src.web.router import get_router
from src.web.templates import DASHBOARD_HTML
from src.service.analysis_service import AnalysisService
from src.utils.logger import logger

def init_routes(service: AnalysisService):
    router = get_router()

    @router.get("/")
    def index(handler: BaseHTTPRequestHandler):
        config = service.config
        stock_list = config.get('portfolio', [])
        # Simple formatting for the textarea
        stock_codes = [s['code'] for s in stock_list]
        stock_codes_str = ", ".join(stock_codes)
        
        html = DASHBOARD_HTML.format(stock_list=stock_codes_str)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.end_headers()
        handler.wfile.write(html.encode('utf-8'))

    @router.get("/api/status")
    def status(handler: BaseHTTPRequestHandler):
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({"status": "running", "service": "AnalysisService"}).encode('utf-8'))

    @router.post("/api/analyze")
    def analyze(handler: BaseHTTPRequestHandler):
        content_len = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_len).decode('utf-8')
        params = {}
        if body:
            try:
                params = json.loads(body)
            except:
                pass
        
        mode = params.get('mode', 'midday')
        dry_run = params.get('dry_run', False)

        try:
            logger.info(f"WebUI: Triggering Analysis (mode={mode}, dry_run={dry_run})...")
            result = asyncio.run(service.run_analysis(mode=mode, dry_run=dry_run))
            
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            logger.error(f"Web API Error: {e}")
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    @router.post("/api/config")
    def update_config(handler: BaseHTTPRequestHandler):
        content_len = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_len).decode('utf-8')
        try:
            data = json.loads(body)
            stock_list_str = data.get('stock_list', '')
            codes = [c.strip() for c in stock_list_str.split(',') if c.strip()]
            
            # Update config (In memory for now, ideally save to yaml)
            # This is a robust simplification. Implementation Plan said "Save Config".
            # Implementing robust yaml saving might be complex. 
            # Let's just update memory + try to save to file if possible or just log it.
            # For this task, updating memory is a good start.
            
            # Construct new portfolio list preserving old structure if possible or just simple code defaults
            new_portfolio = [{"code": code, "market": "CN"} for code in codes] # Defaulting to CN
            service.config['portfolio'] = new_portfolio
            
            # Write back to config.yaml?
            # We don't have a ConfigSaver yet. config_loader is read-only usually.
            # I will skip saving to file for now unless I implemented it.
            # Let's implement a naive save?
            import yaml
            with open("config.yaml", 'r') as f:
                raw_config = yaml.safe_load(f)
            
            raw_config['portfolio'] = new_portfolio
            
            with open("config.yaml", 'w') as f:
                yaml.dump(raw_config, f, allow_unicode=True)

            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "ok", "portfolio": new_portfolio}).encode('utf-8'))
            
        except Exception as e:
            handler.send_response(500)
            handler.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
