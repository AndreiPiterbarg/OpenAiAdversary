# Verification receipts

These standard-library utilities record file sizes and SHA-256 digests for an evaluation
directory and check its exact file membership. `write_manifest` refuses to overwrite an
existing manifest. Verification reports missing, changed and unlisted files; malformed
manifests and symbolic links are rejected.

```python
from prototype.run.receipts import identification_bounds, verify_manifest, write_manifest

write_manifest("results/example")
assert verify_manifest("results/example") == []
bounds = identification_bounds(verified=2, known_invalid=3, unknown=5)
assert bounds == (0.2, 0.7)
```

Create the result directory and finish writing its files before recording a manifest.
Keep the receipt unchanged afterward. A hash manifest detects content changes; it does
not authenticate the producer or establish that an experiment was executed correctly.

The bounds are `[k/N, (k+u)/N]`, where `N` includes verified, known-invalid and unknown
outcomes. They describe uncertainty from missing labels, not a confidence interval.
An empty selection returns `None`.

Run the tests from the repository root with Python 3.10 or newer:

```sh
python -m unittest discover -s prototype/run/tests -v
```
