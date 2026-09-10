"""Validate a completed P-RUN receipt without scheduling work or calling a model."""

import argparse
import json
from collections import Counter
from pathlib import Path

from domains.swe_agents.environment.generator import TaskPool


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('manifest_sha256', help='Digest received from the trusted run producer')
    parser.add_argument('--corpus', default='discovery_149')
    args = parser.parse_args()
    pool = TaskPool.from_prun_receipt(args.receipt, args.manifest_sha256, args.corpus)
    print(json.dumps({'corpus': args.corpus, 'verified_pins': len(pool.pins),
                      'ledger': dict(Counter(pool.admission_ledger.values())),
                      'manifest_sha256': args.manifest_sha256, 'model_calls': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
