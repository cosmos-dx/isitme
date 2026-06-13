"""``web-api`` entrypoint: run the Web API / BFF with uvicorn on port 5050."""

from __future__ import annotations

import argparse


def main() -> None:
    import uvicorn

    from web_api.config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(prog="web-api", description="isitme Web API / BFF")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "web_api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
