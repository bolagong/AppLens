# AppLens

`app-lens` is a local-first Codex plugin for turning a user-provided, permitted Android APK into an evidence-backed, editable product reference. It produces an original Flutter prototype and a Markdown PRD only from the product decisions a user confirms.

## What it does

1. Requires Android Build-Tools (`aapt` or `aapt2`) and `jadx`, then inventories a user-provided APK with package metadata and restricted UI structure evidence—without discovering API endpoints, tokens, credentials, or backend implementation.
2. Guides safe static and emulator-based evidence collection.
3. Stores findings in `project-model.json`, separate from generated HTML, Flutter, and PRD artifacts.
4. Helps the product owner keep, modify, delete, or add proposed capabilities.
5. Generates an original Flutter reference prototype, then a Markdown PRD after confirmation.

## Local prerequisites

Run `scripts/preflight.sh` from the plugin directory. Full analysis requires Python 3, Android SDK Build-Tools (`aapt` or `aapt2`), and `jadx`; the command fails otherwise. When the user explicitly authorizes it, `scripts/provision_analysis_tools.py --output <output-dir> --approve-download` downloads the required official tools into that project output, verifies publisher-provided checksums, and then continues. Dynamic exploration additionally requires an Android emulator and `adb`; prototype verification requires Flutter. The plugin never silently substitutes a reduced-evidence result for the required toolchain.

The included `scripts/static_inventory.py` accepts a local `.apk` file and writes a conservative inventory using the required Android metadata tool. `scripts/reverse_static_inventory.py` then runs the bundled CreditTone decompilation wrapper with the required `jadx --no-res`, keeping only UI-role counts and generic product signals in `evidence/reverse-static.json`. Decompiled source stays as local opaque working data and is never copied into the product model, Flutter prototype, or PRD. The workflow does not install dependencies automatically.

Vetted release tooling may be supplied through `APPLENS_AAPT` and `APPLENS_JADX`; the latter can be an absolute executable path and is passed only to the restricted local wrapper. Both tools remain mandatory.

## Use in Codex

Install the plugin from its Marketplace, open a new Codex thread in an empty output workspace, and ask Codex to analyze an APK you are authorized to inspect. AppLens records the authorization, exploration plan, required toolchain policy, and delivery goal once in `evidence/run-brief.json`; it does not repeat those questions at every step.

```text
one-time run brief → evidence → editable model → optional draft prototype → final confirmation → PRD
```

For a typical end-to-end first pass, users can send one message:

```text
I am authorized to inspect <APK path>. Output to <project-local directory>.
Use a resettable isolated emulator for non-login, non-destructive exploration; if unavailable, continue with static evidence. Deliver an editable model and an original draft Flutter prototype. I will approve the actual model before the final PRD.
```

Use `static_only` instead of an emulator plan when dynamic validation is not wanted. Only the final PRD requires a second, explicit confirmation because the user must be able to see and approve the actual product decisions. Authentication, payment, membership, and destructive/external-action flows are explicitly out of scope.

## Quick local workflow

```text
scripts/preflight.sh
scripts/configure_run.py --apk /path/to/app.apk --output ./analysis-output --workspace . --confirm-user-authorized-apk --confirm-tool-downloads --exploration static_only --delivery draft_prototype
scripts/provision_analysis_tools.py --output ./analysis-output --approve-download
scripts/require_analysis_tools.py --output ./analysis-output
scripts/static_inventory.py /path/to/app.apk --output ./analysis-output
scripts/reverse_static_inventory.py /path/to/app.apk --output ./analysis-output
scripts/bootstrap_project.py --evidence ./analysis-output/evidence/static-inventory.json --output ./analysis-output
scripts/derive_candidates.py --output ./analysis-output
scripts/serve_workbench.py --output ./analysis-output
scripts/generate_flutter.py --output ./analysis-output
scripts/verify_flutter.py --output ./analysis-output --run
scripts/approve_model.py --output ./analysis-output --version v1.0
scripts/generate_prd.py --output ./analysis-output
```

For dynamic evidence, first install the user-provided APK only onto a resettable emulator with `install_to_emulator.py`, then use `safe_explore.py` and `ingest_dynamic_evidence.py`. The plugin never connects to a real phone or retrieves installed applications.

## Included scripts

- `scripts/preflight.sh` / `scripts/require_analysis_tools.py` — enforce the required full-analysis toolchain.
- `scripts/provision_analysis_tools.py` — with explicit download approval, fetches checksum-verified official tools into the selected project output.
- `scripts/static_inventory.py` — writes safe static package/resource evidence to `evidence/static-inventory.json`.
- `scripts/reverse_static_inventory.py` — invokes the restricted bundled decompiler and writes API-safe UI structure evidence to `evidence/reverse-static.json`.
- `scripts/bootstrap_project.py` — creates the editable `project-model.json` and output directory structure.
- `scripts/derive_candidates.py` — creates review-only function candidates from safe evidence.
- `scripts/install_to_emulator.py` / `safe_explore.py` — installation and conservative exploration on an isolated emulator only.
- `scripts/ingest_dynamic_evidence.py` — attaches screenshot and path evidence to the model.
- `scripts/serve_workbench.py` — starts the local product-decision editor at `127.0.0.1`.
- `scripts/generate_flutter.py` / `verify_flutter.py` — generate and validate the original Flutter reference prototype.
- `scripts/approve_model.py` / `generate_prd.py` — record confirmation and produce Markdown PRD plus changelog.
- `scripts/validate_release.py` — runs dependency-free structural checks before publishing.

## Publishing

See [RELEASE.md](RELEASE.md). The repository must publish the plugin under `plugins/app-lens/` and a Marketplace manifest under `.agents/plugins/marketplace.json`.

The scripts intentionally do not install software, connect to a real device, retrieve apps from a device, upload files, log in, or perform external actions. The bundled upstream wrapper is used only for offline UI-structure analysis; API, credential, backend, traffic, Frida, signature, bypass, and native-analysis workflows remain excluded.

## Third-party component

The APK decompilation wrapper in `third_party/android-reverse-engineering-skill/` is sourced from [CreditTone/android-reverse-engineering-skill](https://github.com/CreditTone/android-reverse-engineering-skill) and is covered by its included Apache-2.0 license and [notice](third_party/android-reverse-engineering-skill/NOTICE.md).
