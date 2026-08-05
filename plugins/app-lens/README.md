# AppLens

`app-lens` is a local-first Codex plugin for turning a permitted Android APK or XAPK into an evidence-backed, editable product reference. It produces an original Flutter prototype and a Markdown PRD only from the product decisions a user confirms.

## What it does

1. Inventories an APK/XAPK without attempting to discover API endpoints, tokens, credentials, or backend implementation.
2. Guides safe static and emulator-based evidence collection.
3. Stores findings in `project-model.json`, separate from generated HTML, Flutter, and PRD artifacts.
4. Helps the product owner keep, modify, delete, or add proposed capabilities.
5. Generates an original Flutter reference prototype, then a Markdown PRD after confirmation.

## Local prerequisites

Run `scripts/preflight.sh` from the plugin directory. The workflow can begin with Python 3 alone. Static Android metadata is richer with Android SDK build tools (`aapt` or `aapt2`), dynamic exploration requires an Android emulator and `adb`, and prototype verification requires Flutter.

The included `scripts/static_inventory.py` works on `.apk` and `.xapk` files and writes a conservative inventory. It never decompiles code or sends an APK anywhere. The workflow does not install dependencies automatically.

## Use in Codex

Install the plugin from its Marketplace, open a new Codex thread in an empty output workspace, and ask Codex to analyze an APK you are authorized to inspect. The Skill will ask for the input path and use the following staged workflow:

```text
inventory → evidence review → editable product model → Flutter prototype → confirmation → PRD
```

Only run the PRD stage after the product model is explicitly confirmed. Authentication, payment, membership, and destructive/external-action flows are explicitly out of scope.

## Quick local workflow

```text
scripts/preflight.sh
scripts/static_inventory.py /path/to/app.apk --output ./analysis-output
scripts/bootstrap_project.py --evidence ./analysis-output/evidence/static-inventory.json --output ./analysis-output
scripts/derive_candidates.py --output ./analysis-output
scripts/serve_workbench.py --output ./analysis-output
scripts/generate_flutter.py --output ./analysis-output
scripts/verify_flutter.py --output ./analysis-output --run
scripts/approve_model.py --output ./analysis-output --version v1.0
scripts/generate_prd.py --output ./analysis-output
```

For dynamic evidence, first install only onto a resettable emulator with `install_to_emulator.py`, then use `safe_explore.py` and `ingest_dynamic_evidence.py`. ADB extraction from a real phone is restricted to a user-selected package and is acquisition-only.

## Included scripts

- `scripts/preflight.sh` — reports availability of optional local dependencies.
- `scripts/static_inventory.py` — writes safe static package/resource evidence to `evidence/static-inventory.json`.
- `scripts/bootstrap_project.py` — creates the editable `project-model.json` and output directory structure.
- `scripts/derive_candidates.py` — creates review-only function candidates from safe evidence.
- `scripts/adb_acquire.py` — lists or pulls only a user-confirmed installed package and split APKs.
- `scripts/install_to_emulator.py` / `safe_explore.py` — installation and conservative exploration on an isolated emulator only.
- `scripts/ingest_dynamic_evidence.py` — attaches screenshot and path evidence to the model.
- `scripts/serve_workbench.py` — starts the local product-decision editor at `127.0.0.1`.
- `scripts/generate_flutter.py` / `verify_flutter.py` — generate and validate the original Flutter reference prototype.
- `scripts/approve_model.py` / `generate_prd.py` — record confirmation and produce Markdown PRD plus changelog.
- `scripts/validate_release.py` — runs dependency-free structural checks before publishing.

## Publishing

See [RELEASE.md](RELEASE.md). The repository must publish the plugin under `plugins/app-lens/` and a Marketplace manifest under `.agents/plugins/marketplace.json`.

The scripts intentionally do not install software, run a real device, upload files, log in, or perform external actions.
