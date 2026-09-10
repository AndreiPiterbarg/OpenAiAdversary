"""Command-line entry points for the pure parts of the system.

Everything here runs without a model: list domain plugins and drive the pre-registration
protocol.

"""

import argparse
import json
import sys
from collections.abc import Sequence

from adversary.domain.registry import DOMAINS
from adversary.protocol import (
    PreregistrationError,
    amend,
    decide,
    register,
    seal_results,
    verify,
)


def _domains(args: argparse.Namespace) -> None:
    DOMAINS.discover(args.package)
    for name in DOMAINS.names():
        print(name)


def _register(args: argparse.Namespace) -> None:
    registration = register(args.directory)
    print(registration.model_dump_json(indent=2))


def _verify(args: argparse.Namespace) -> None:
    problems = verify(args.directory)
    if problems:
        for p in problems:
            print(f"VIOLATION: {p}")
        sys.exit(1)
    print("intact")


def _amend(args: argparse.Namespace) -> None:
    amendment = amend(args.directory, args.reason)
    print(amendment.model_dump_json(indent=2))


def _seal(args: argparse.Namespace) -> None:
    manifest = seal_results(args.directory)
    print(f"sealed {len(manifest.files)} files, digest {manifest.digest()[:16]}")


def _decide(args: argparse.Namespace) -> None:
    verdict = decide(args.directory, args.metrics)
    print(json.dumps(verdict.model_dump(mode="json"), indent=2))


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point; ``argv`` defaults to the process arguments."""
    parser = argparse.ArgumentParser(
        prog="adversary", description="Coverage-driven adversary: model-free commands"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("domains", help="List registered domain plugins")
    p.add_argument("--package", default="domains")
    p.set_defaults(func=_domains)

    for name, func, help_text in (
        ("register", _register, "Lock an experiment's pre-registration"),
        ("verify", _verify, "Check an experiment's hash chain"),
        ("seal", _seal, "Seal an experiment's results directory"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("directory")
        p.set_defaults(func=func)

    p = sub.add_parser("amend", help="Record a pre-registration change with a reason (append-only)")
    p.add_argument("directory")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=_amend)

    p = sub.add_parser("decide", help="Compute the verdict against pre-declared kill rules")
    p.add_argument("directory")
    p.add_argument("--metrics", default="metrics.json")
    p.set_defaults(func=_decide)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except PreregistrationError as exc:
        sys.exit(f"{args.command}: {exc}")


if __name__ == "__main__":
    main()
