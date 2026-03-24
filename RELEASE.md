# Release Guide

This project has two release artifacts:
- PyPI package: `yinshield`
- npm package: `@serein-213/openclaw-yinshield`

## Pre-release checklist

Run the local verification suite:

```bash
python -m unittest discover -s tests -v
python benchmarks/run_benchmark.py --mode placeholder --strategy strict --output benchmarks/sample_results.placeholder.json
python benchmarks/run_benchmark.py --mode alias --strategy strict --output benchmarks/sample_results.alias.json
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode placeholder --strategy strict --output benchmarks/mini_realistic_results.placeholder.json
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode alias --strategy strict --output benchmarks/mini_realistic_results.alias.json
node --check openclaw-plugin/src/index.js
python scripts/check_version_consistency.py
python -m build
cd openclaw-plugin && npm pack --dry-run
```

## Versioning

Keep Python and npm versions aligned.

To bump both package versions together:

```bash
python scripts/sync_release_version.py 0.1.0
python scripts/check_version_consistency.py
```

This updates:
- `yinshield/__init__.py`
- `openclaw-plugin/package.json`

## Python release

Build distribution artifacts:

```bash
python -m build
```

Optional validation:

```bash
python -m twine check dist/*
```

Publish:

```bash
python -m twine upload dist/*
```

## npm release

Build a dry-run tarball:

```bash
cd openclaw-plugin
npm pack --dry-run
```

Publish:

```bash
npm publish --access public
```

## Post-release

- Tag the Git commit with the release version.
- Update release notes with benchmark deltas and notable limitations.
- Verify installation from PyPI and npm in a clean environment.

Current draft release notes:
- `docs/release-notes/0.1.0-alpha.md`
