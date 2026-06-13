"""``brain`` CLI: run the API server, the sync worker, or print stats.

    brain serve          # run the Core Brain HTTP API (uvicorn)
    brain sync           # run the standalone outbox sync worker
    brain stats          # print store counters and exit
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from brain_core.config import load_settings


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    settings = load_settings(args.config)
    uvicorn.run(
        "brain_core.api.app:create_app",
        factory=True,
        host=args.host or settings.server.host,
        port=args.port or settings.server.port,
        reload=args.reload,
    )


def _sync(args: argparse.Namespace) -> None:
    from brain_core.sync.worker import build_worker

    logging.basicConfig(level=logging.INFO)
    settings = load_settings(args.config)

    async def run() -> None:
        worker = build_worker(settings)
        await worker._outbox.init()
        await worker.run()

    asyncio.run(run())


def _stats(args: argparse.Namespace) -> None:
    import json

    from brain_core.brain import Brain

    settings = load_settings(args.config)

    async def run() -> None:
        brain = Brain(settings)
        await brain.startup()
        try:
            print(json.dumps(await brain.stats(), indent=2))
        finally:
            await brain.shutdown()

    asyncio.run(run())


def main() -> None:
    parser = argparse.ArgumentParser(prog="brain", description="isitme Core Brain")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Run the Core Brain HTTP API")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_serve)

    p_sync = sub.add_parser("sync", help="Run the outbox sync worker")
    p_sync.set_defaults(func=_sync)

    p_stats = sub.add_parser("stats", help="Print store counters")
    p_stats.set_defaults(func=_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
