import asyncio
import sys
import argparse
from typing import Dict, Any, List

from src.utils.logger import logger
from src.service.analysis_service import AnalysisService
from src.web.server import WebServer
from src.web.api import get_router # We'll implement this next

def entry_point():
    parser = argparse.ArgumentParser(description="Project Sentinel V2")
    parser.add_argument('--mode', type=str, default='midday', choices=['midday', 'close'], help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Run without calling expensive APIs or sending notifications')
    parser.add_argument('--replay', action='store_true', help='Replay analysis using last saved data')
    parser.add_argument('--webui', action='store_true', help='Start WebUI server')
    
    args = parser.parse_args()
    
    service = AnalysisService()

    if args.webui:
        # Start WebUI
        # Ensure API routes are registered
        from src.web.api import init_routes
        init_routes(service)
        
        # We can also run analysis immediately if args.mode is specified?
        # But usually --webui implies persistent server. 
        # If user wants both, they might run one then the other or concurrently.
        # For simplicity, if --webui, we starts server and block.
        
        server = WebServer(port=8000)
        server.run()
        
    else:
        # CLI Run
        asyncio.run(service.run_analysis(mode=args.mode, dry_run=args.dry_run, replay=args.replay))

if __name__ == "__main__":
    entry_point()
