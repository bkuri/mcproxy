"""Main entry point for MCProxy.

Initializes logging, loads configuration, starts server manager,
and runs the FastAPI application with hot-reload support.
"""

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import uvicorn

from config_reloader import ConfigReloader, HotReloadServerManager
from config_watcher import ConfigError, load_config
from logging_config import get_logger, setup_logging
from server import app, set_server_manager

logger = get_logger(__name__)

# Global references for graceful shutdown
config_reloader: Optional[ConfigReloader] = None
hot_reload_manager: Optional[HotReloadServerManager] = None


async def main() -> None:
    """Main application entry point."""
    global config_reloader, hot_reload_manager

    # Load environment variables from .env file
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    if key and not os.environ.get(key):
                        os.environ[key] = value

    parser = argparse.ArgumentParser(
        description="MCProxy - MCP Gateway Aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --log                    # Run with stdout logging
  python main.py --port 8080              # Run on custom port
  python main.py --config servers.json    # Use custom config file
  python main.py --no-reload              # Disable hot-reload
        """,
    )

    parser.add_argument(
        "--log", action="store_true", help="Log to stdout (default: syslog)"
    )

    parser.add_argument(
        "--port", type=int, default=12009, help="Port to listen on (default: 12009)"
    )

    parser.add_argument(
        "--config",
        default="mcp-servers.json",
        help="Path to configuration file (default: mcp-servers.json)",
    )

    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--no-reload", action="store_true", help="Disable hot-reload of configuration"
    )

    parser.add_argument(
        "--reload-interval",
        type=float,
        default=1.0,
        help="Config file check interval in seconds (default: 1.0)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(use_stdout=args.log)

    logger.info("=" * 50)
    logger.info("MCProxy Starting")
    logger.info("=" * 50)

    # Load configuration
    try:
        config = load_config(args.config)
        logger.info(
            f"Loaded configuration with {len(config.get('servers', []))} servers"
        )
    except ConfigError as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Initialize hot-reload capable server manager
    hot_reload_manager = HotReloadServerManager(config)
    set_server_manager(hot_reload_manager)

    # Spawn servers
    await hot_reload_manager.spawn_servers()

    # Give servers time to start
    await asyncio.sleep(2)

    # Log status
    tools = hot_reload_manager.get_all_tools()
    total_tools = sum(len(t) for t in tools.values())
    logger.info(f"Servers ready: {len(tools)} running with {total_tools} tools")

    # Setup config reloader (hot-reload)
    if not args.no_reload:
        config_reloader = ConfigReloader(
            config_path=args.config,
            reload_callback=hot_reload_manager.reload_config,
            check_interval=args.reload_interval,
        )
        await config_reloader.start()
    else:
        logger.info("Hot-reload disabled")

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig: int, frame) -> None:
        logger.info("Received shutdown signal")
        asyncio.create_task(shutdown())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Run uvicorn
    uvicorn_config = uvicorn.Config(
        app, host=args.host, port=args.port, log_level="warning"
    )
    server = uvicorn.Server(uvicorn_config)

    logger.info(f"Starting HTTP server on {args.host}:{args.port}")
    logger.info(f"SSE endpoint: http://{args.host}:{args.port}/sse")
    if not args.no_reload:
        logger.info(f"Hot-reload enabled (checking every {args.reload_interval}s)")

    try:
        await server.serve()
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        await shutdown()


async def shutdown() -> None:
    """Gracefully shutdown all servers and watchers."""
    logger.info("Shutting down...")

    # Stop config reloader
    if config_reloader:
        await config_reloader.stop()

    # Stop all servers
    if hot_reload_manager:
        await hot_reload_manager.stop_all()

    logger.info("Shutdown complete")
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
