"""adversary: coverage-driven discovery and repair of foundation-model failure regions.

Domain-agnostic by construction. The vocabulary of any particular domain lives in
``domains/`` behind the contract in :mod:`adversary.domain`; ``tests/test_boundaries.py``
fails if it leaks in here.
"""

__version__ = "0.1.0"
