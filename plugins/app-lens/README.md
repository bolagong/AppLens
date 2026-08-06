# AppLens

`app-lens` is a local-first Codex plugin for turning a user-provided, permitted Android APK into an evidence-backed, editable product reference. It produces an original Flutter prototype and a Markdown PRD only from the product decisions a user confirms.

## What it does

1. Requires Android Build-Tools (`aapt` or `aapt2`) and `jadx`, then inventories a user-provided APK with package metadata and restricted UI structure evidence—without discovering API endpoints, tokens, credentials, or backend implementation.
2. Guides safe static and emulator-based evidence collection.
3. Stores findings in `project-model.json`, separate from generated HTML, Flutter, and PRD artifacts.
4. Lets the product owner adopt all evidence-derived capabilities in one safe bulk action, using original implementation constraints.
5. Generates an original Flutter reference prototype, then a Markdown PRD after confirmation.

## Local prerequisites

Run `scripts/preflight.sh` from the plugin directory. Full analysis requires Python 3, Android SDK Build-Tools (`aapt` or `aapt2`), and `jadx`; the command fails otherwise. When the user explicitly authorizes it, `scripts/provision_analysis_tools.py --output <output-dir> --approve-download` downloads the required official tools into that project output, verifies publisher-provided checksums, and then continues. Dynamic exploration additionally requires an Android emulator and `adb`; prototype verification requires Flutter. The plugin never silently substitutes a reduced-evidence result for the required toolchain.

The included `scripts/static_inventory.py` accepts a local `.apk` file and writes a conservative inventory using the required Android metadata tool. It retains aggregate resource statistics and generic capability signals, never raw resource paths or raw Android-tool output. `scripts/reverse_static_inventory.py` then runs the bundled CreditTone decompilation wrapper with the required `jadx --no-res`, keeping only UI-role counts and generic product signals in `evidence/reverse-static.json`. Decompiled source stays in `.applens/work/` as local opaque working data and is never copied into the product model, Flutter prototype, PRD, or Markdown evidence summary. The workflow does not install dependencies automatically.

Vetted release tooling may be supplied through `APPLENS_AAPT` and `APPLENS_JADX`; the latter can be an absolute executable path and is passed only to the restricted local wrapper. Both tools remain mandatory.

## Use in Codex

Install the plugin from its Marketplace, open a new Codex thread in an empty output workspace, and ask Codex to analyze an APK you are authorized to inspect. AppLens defaults to a static-only analysis and an evidence bundle; it does not ask the user to choose those defaults. It records the authorization, required-toolchain policy, and selected defaults once in `evidence/run-brief.json`, and always maintains a human-readable `docs/EVIDENCE_SUMMARY.md`.

```text
one-time run brief → evidence → bulk adoption of abstract features → final confirmation → optional prototype/PRD
```

For the default first pass, users can send one message:

```text
I am authorized to inspect <APK path>. Output to <project-local directory>. I approve downloading the required official AppLens analysis tools into that output if they are missing.
```

This runs `static_only` exploration and delivers `evidence` by default. A user can explicitly request `dynamic`, `model`, or `draft_prototype` when needed. Only the final PRD requires a second, explicit confirmation because the user must be able to see and approve the actual product decisions. Authentication, payment, membership, and destructive/external-action flows are explicitly out of scope.

## Quick local workflow

```text
scripts/preflight.sh
scripts/configure_run.py --apk /path/to/app.apk --output ./analysis-output --workspace . --confirm-user-authorized-apk --confirm-tool-downloads --exploration static_only --delivery evidence
scripts/provision_analysis_tools.py --output ./analysis-output --approve-download
scripts/require_analysis_tools.py --output ./analysis-output
scripts/static_inventory.py /path/to/app.apk --output ./analysis-output
scripts/reverse_static_inventory.py /path/to/app.apk --output ./analysis-output --timeout-seconds 3600 --threads 4
scripts/generate_evidence_summary.py --output ./analysis-output
scripts/bootstrap_project.py --evidence ./analysis-output/evidence/static-inventory.json --output ./analysis-output
scripts/derive_candidates.py --output ./analysis-output
scripts/serve_workbench.py --output ./analysis-output
scripts/generate_flutter.py --output ./analysis-output
scripts/verify_flutter.py --output ./analysis-output --run
scripts/approve_model.py --output ./analysis-output --version v1.0
scripts/generate_prd.py --output ./analysis-output
```

The restricted JADX pass allows 60 minutes by default for large APKs. It writes safe progress to `evidence/reverse-progress.json`; use `scripts/cancel_reverse_analysis.py --output ./analysis-output` to request safe cancellation. To choose a different local limit or processing parallelism for one run, add `--timeout-seconds <positive-seconds>` or `--threads <positive-integer>` to `reverse_static_inventory.py`. JADX has no verified resume mode: a timeout or cancellation remains a failed analysis and does not produce a model or prototype.

Tools are stored under `.applens/toolchain/`, JADX configuration under `.applens/jadx-home/`, and opaque transient data under `.applens/work/`; none is a delivery artifact. Working data is retained for 24 hours. Run `scripts/cleanup_working_data.py --output ./analysis-output` to list expired working data, then add `--confirm-delete` only after explicitly approving deletion.

For dynamic evidence, first install the user-provided APK only onto a resettable emulator with `install_to_emulator.py`, then use `safe_explore.py` and `ingest_dynamic_evidence.py`. The plugin never connects to a real phone or retrieves installed applications.

## Included scripts

- `scripts/preflight.sh` / `scripts/require_analysis_tools.py` — enforce the required full-analysis toolchain.
- `scripts/provision_analysis_tools.py` — with explicit download approval, fetches checksum-verified official tools into the selected project output.
- `scripts/static_inventory.py` — writes safe static package/resource evidence to `evidence/static-inventory.json`.
- `scripts/reverse_static_inventory.py` — invokes the restricted bundled decompiler and writes API-safe UI structure evidence to `evidence/reverse-static.json`.
- `scripts/generate_evidence_summary.py` — regenerates `docs/EVIDENCE_SUMMARY.md`, the human-readable evidence entry point.
- `scripts/cancel_reverse_analysis.py` / `scripts/cleanup_working_data.py` — safely request reverse-analysis cancellation and explicitly clean expired working data.
- `scripts/bootstrap_project.py` — creates the editable `project-model.json` and output directory structure.
- `scripts/derive_candidates.py` — creates review-only function candidates from safe evidence.
- `scripts/install_to_emulator.py` / `safe_explore.py` — installation and conservative exploration on an isolated emulator only.
- `scripts/ingest_dynamic_evidence.py` — attaches screenshot and path evidence to the model.
- `scripts/serve_workbench.py` — starts the local workbench at `127.0.0.1`; its bulk-adoption action accepts all abstract evidence-derived features while keeping evidence read-only and implementation original.
- `scripts/generate_flutter.py` / `verify_flutter.py` — generate and validate the original Flutter reference prototype.
- `scripts/approve_model.py` / `generate_prd.py` — record confirmation and produce Markdown PRD plus changelog.
- `scripts/validate_release.py` — runs dependency-free structural checks before publishing.

## Publishing

See [RELEASE.md](RELEASE.md). The repository must publish the plugin under `plugins/app-lens/` and a Marketplace manifest under `.agents/plugins/marketplace.json`.

The scripts intentionally do not install software, connect to a real device, retrieve apps from a device, upload files, log in, or perform external actions. The bundled upstream wrapper is used only for offline UI-structure analysis; API, credential, backend, traffic, Frida, signature, bypass, and native-analysis workflows remain excluded.

## Third-party component

The APK decompilation wrapper in `third_party/android-reverse-engineering-skill/` is sourced from [CreditTone/android-reverse-engineering-skill](https://github.com/CreditTone/android-reverse-engineering-skill) and is covered by its included Apache-2.0 license and [notice](third_party/android-reverse-engineering-skill/NOTICE.md).
