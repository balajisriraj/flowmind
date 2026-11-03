"""Command line: ``flowmind serve | build "<description>" | eval``."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import get_settings


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("flowmind.api:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)


def _build(args: argparse.Namespace) -> None:
    from .service import Service

    async def run() -> None:
        service = Service.from_settings(get_settings())
        await service.start()
        try:
            wid = service.create(args.description)
            async for e in service.events(wid):
                if e["type"] == "analysis":
                    print(f"\n{e['analysis']['process']}: {e['analysis']['goal']}")
                elif e["type"] == "validation":
                    print("  ✓ valid" if not e["problems"] else "  ✗ " + "\n  ✗ ".join(e["problems"]))
                elif e["type"] == "dry_step":
                    s = e["step"]
                    print(f"    {s['status']:>8}  {s['id']}  {s.get('error', '')}")
                elif e["type"] == "done":
                    print(f"\n{e['status']} after {e['fixes']} fix(es). Workflow id {wid}")
                elif e["type"] == "error":
                    print(e["message"], file=sys.stderr)
        finally:
            await service.stop()

    asyncio.run(run())


def _eval(args: argparse.Namespace) -> None:
    from .evals import run

    sys.exit(0 if asyncio.run(run(verbose=args.verbose)) else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="flowmind", description="Describe the process, get the automation.")
    commands = parser.add_subparsers(required=True)
    serve = commands.add_parser("serve", help="run the HTTP API and the runner")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(run=_serve)
    build = commands.add_parser("build", help="design and dry-run a workflow from a description")
    build.add_argument("description")
    build.set_defaults(run=_build)
    evals = commands.add_parser("eval", help="build, deploy and exercise the example processes")
    evals.add_argument("--verbose", action="store_true")
    evals.set_defaults(run=_eval)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
