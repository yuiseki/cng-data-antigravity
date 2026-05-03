from __future__ import annotations

import argparse
from pathlib import Path

from cng_data_antigravity.config import load_config, resolve_config_path
from cng_data_antigravity.runner import run_escape


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cng-data-antigravity")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("config", nargs="?", help="Path to escape.yaml")
    run_parser.add_argument("--force", "-f", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        config_path = resolve_config_path(args.config, Path.cwd())
        config = load_config(config_path)
        run_escape(config, config_path=config_path, force=args.force)
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
