---
name: app-lens
description: Analyze a user-authorized Android APK into evidence, an editable product model, an original Flutter reference prototype, and a Markdown PRD. Use when the user asks to analyze an Android competitor app, turn an APK into a product-function map, create a Flutter reference prototype from APK evidence, or generate a PRD after a reviewed product decision.
---

# AppLens

Use this Skill only for a user-provided APK the user is authorized to inspect. Treat the result as a product reference, never as a request to copy an application.

## Safety boundaries

- Keep all APKs, extracted files, screenshots, evidence, model files, prototypes, and PRDs in the user's current workspace unless the user explicitly requests another project-local path.
- Do not extract, display, reproduce, or use API URLs, authentication material, tokens, keys, credentials, private user data, or backend logic.
- Deliver only aggregate resource statistics, standard permission capability signals, and generic UI signals. Do not retain raw resource paths or raw Android-tool output in delivery evidence.
- Use the bundled CreditTone reverse-engineering wrapper only through `scripts/reverse_static_inventory.py`. It may locally decompile the supplied APK with `jadx --no-res` to derive UI structure; treat that workspace as opaque working data and never surface its source, API, authentication, network, signing, encryption, or native-code content.
- Do not reproduce competitor brands, logos, app names, icons, images, copy, or other recognizable proprietary assets. Use placeholder brands, original icons, original illustrations, and mock data.
- Treat login, registration, membership, subscription, payment, and paywall screens as skipped interception points. Do not include them in the product model, Flutter prototype, or PRD.
- Do not automatically upload, publish, share externally, send messages, place orders, delete data, pay, use real accounts, or provide personal data.
- Dynamic exploration is limited to an isolated resettable emulator. Grant a device permission only when it is essential to observe a permitted device capability such as camera preview. Never use a user’s real phone for dynamic exploration.
- If a behavior cannot be evidenced dynamically or statically, record it as `unconfirmed`; do not invent it.

## Required artifact layout

Use the selected output directory and keep this structure as the source of truth:

```text
project-model.json
evidence/
  run-brief.json          # one-time authorization and delivery plan, when configured
  toolchain.json          # tool versions, source URLs, and checksums when provisioned
  static-inventory.json
  reverse-static.json
  reverse-progress.json  # safe progress for a running or completed reverse-static pass
  screenshots/
  paths/
flutter_prototype/
docs/
  EVIDENCE_SUMMARY.md    # always-updated, human-readable evidence delivery
  PRD.md
  CHANGELOG.md
.applens/
  toolchain/             # local tool cache; not a delivery artifact
  jadx-home/             # local JADX configuration; not a delivery artifact
  work/
    reverse-decompiled/  # opaque working data; never used in generated deliverables
```

`project-model.json` is authoritative. HTML workspaces, the Flutter prototype, and the PRD are derived artifacts.

`docs/EVIDENCE_SUMMARY.md` is the human-readable entry point for every evidence delivery. It is derived only from safe aggregate evidence and states completed stages, confidence, blocked stages, and the location of non-delivery working data; JSON remains the verifiable source evidence.

AppLens is a strict-analysis workflow. `aapt`/`aapt2` and `jadx` are required before any evidence, model, prototype, or PRD is generated. Supplemental Manifest parsing and resource signals may enrich a completed toolchain result but never substitute for either required tool.

## Workflow

### 1. One-time preflight and run brief

Extract already explicit facts from the user's first request; do not ask again for an authorization the user has already stated. Unless the user explicitly requests otherwise, select `static_only` exploration and `evidence` delivery. These are the default first-pass workflow, so do not ask the user to choose either one or require them to repeat them in a confirmation template. Establish the following once per output directory:

- path to the user-provided `.apk` file;
- project-local output directory;
- explicit authorization to inspect the APK;
- permission to download required local tools into that output when they are missing;
- explicit alternate exploration or delivery only when the user requests one.

If the APK path, project-local output directory, explicit authorization, or required-tool download permission is missing, ask one compact, combined question rather than staging several approval questions. State the selected defaults in the question, but do not ask for them. Use this reply format:

```text
APK: <path>; output: <project-local directory>; authorized: yes; tool-downloads: yes | no
```

Report the default as `exploration: static_only; delivery: evidence`. Treat an explicitly requested `dynamic` plan as permission to use only a resettable isolated emulator. Never infer it from the presence of `adb` or an emulator. An explicitly requested `draft_prototype` authorizes an original, review-ready draft—not a final PRD.

From the plugin root, run the preflight command exactly as follows:

```text
scripts/preflight.sh
```

`preflight.sh` is an executable Shell script; do not infer a `.py` extension or invoke `preflight.py`. It fails when `aapt`/`aapt2` or `jadx` is missing. When the user's analysis request explicitly authorizes tool downloads, immediately prepare the missing tools in the selected project output, then rerun the check:

```text
scripts/provision_analysis_tools.py --output <output-dir> --approve-download
scripts/require_analysis_tools.py --output <output-dir>
```

The provisioner prefers the latest stable official AAPT2 release, plus the latest official JADX and—if no Java runtime is available—Eclipse Temurin JRE. It verifies publisher-provided checksums and writes its tool receipt to `evidence/toolchain.json`. It never installs system-wide software and it never creates a reduced-evidence artifact. If download authorization was not given, ask for it; do not downgrade.

Accept only a user-provided `.apk` file as input. Do not connect to a real device or retrieve installed application packages through ADB.

After the user's one-time confirmation, record it before collecting evidence. Pass `--confirm-isolated-emulator` only for an explicitly selected dynamic plan:

```text
scripts/configure_run.py --apk <apk-path> --output <output-dir> --workspace <workspace-dir> --confirm-user-authorized-apk --confirm-tool-downloads --exploration static_only --delivery evidence
```

Omit `--confirm-tool-downloads` if the user declined tool downloads; then report missing tools as a blocker rather than downgrade. For an explicitly authorized dynamic plan, replace the defaults with `--exploration dynamic --confirm-isolated-emulator`; for an explicitly requested model or prototype, replace `--delivery evidence` with the requested delivery. `evidence/run-brief.json` is the auditable record of the selected plan. Do not turn its flags into a substitute for a user statement.

### 2. Static inventory

Run these commands in order:

```text
scripts/static_inventory.py <apk-path> --output <output-dir>
scripts/reverse_static_inventory.py <apk-path> --output <output-dir> --timeout-seconds 3600 --threads 4
scripts/bootstrap_project.py --evidence <output-dir>/evidence/static-inventory.json --output <output-dir>
scripts/derive_candidates.py --output <output-dir>
```

Use the inventories only as evidence: package metadata, declared permissions, component counts, resource inventory, native ABI hints, Android-tool output, and restricted reverse-static UI structure. Do not infer a user-facing feature solely from an ambiguous technical artifact. The reverse-static layer must contribute only its generic UI component counts and product signals; never read or include raw decompiled source.

The reverse-static command allows JADX up to 60 minutes by default and reports safe progress to `evidence/reverse-progress.json` every few seconds. When the user explicitly requests a longer or shorter local analysis window, pass `--timeout-seconds <positive-seconds>`; pass `--threads <positive-integer>` only when the user's machine budget permits it. A running pass can be safely cancelled with `scripts/cancel_reverse_analysis.py --output <output-dir>`. JADX has no verified resume mode, so cancellation or timeout produces failed evidence and the next pass starts again. Do not generate a model from incomplete UI evidence.

Working data remains in `.applens/work/` for 24 hours by default. Do not delete it automatically. Use `scripts/cleanup_working_data.py --output <output-dir>` to list expired data and add `--confirm-delete` only after the user explicitly approves deletion.

If either static command fails, stop. Do not bootstrap a model, open the workbench, generate a prototype, or claim a completed analysis. A completed toolchain result can still contain `unconfirmed` behaviors, but no tool-missing fallback is allowed.

### 3. Evidence collection

When a compatible isolated emulator is available, explore only non-destructive, non-authenticated paths:

```text
tabs → lists → details → search/filter → reversible state changes → device-capability previews
```

For every observed page or proposed function, attach:

- a screenshot path when dynamically verified;
- its navigation path;
- relevant visible controls and static resource/component evidence;
- confidence: `dynamically_verified`, `static_inference`, or `unconfirmed`.

If the application cannot run because of architecture, emulator detection, special hardware, or another limitation, stop the requested dynamic delivery and report the limitation. Do not bypass the restriction or substitute a static-only result for a dynamic request.

Run dynamic commands only when `evidence/run-brief.json` records the dynamic plan. Install the input package with `scripts/install_to_emulator.py`, then invoke `scripts/safe_explore.py --serial <emulator-serial> --output <output-dir> --confirm-isolated-emulator`. The explorer obtains the package name from the parsed static inventory; use `--package <package>` only when that safe metadata is unavailable. It refuses non-emulator targets, captures only non-interception screenshots, and skips high-risk or unnamed controls. Run `scripts/ingest_dynamic_evidence.py --output <output-dir>` afterward.

For a static-only plan, omit dynamic exploration because it was deliberately not requested. For a dynamic plan, no static fallback is permitted.

### 4. Product decision model

Populate `functions[]` in `project-model.json`. Each entry must use:

```text
name
entry
flow
pages
page_states
interaction_rules
competitor_evidence
confidence
product_decision: keep | modify | delete | add
modification_notes
acceptance_criteria
```

Present the function tree and let the product owner modify it. Product decisions, not raw evidence, control generation. Preserve the original observations read-only inside `observations`.

Start the local three-column editor with `scripts/serve_workbench.py --output <output-dir>`. It is bound to `127.0.0.1`, serves one project only, and writes back through schema validation. A product owner may also edit the JSON directly, then must run `scripts/validate_model.py <output-dir>/project-model.json`.

When the run brief requests `draft_prototype`, continue to generation in the same turn after all requested evidence is incorporated; do not stop merely to ask for an intermediate model decision.

### 5. Original Flutter reference prototype

If the run brief requests `draft_prototype`, generate a review-ready draft after evidence is incorporated: `scripts/generate_flutter.py --output <output-dir>`. Otherwise generate it after the product model is reviewed. A model that is not formally confirmed produces a draft and must be labelled as such. Create an original visual system based on abstracted properties such as hierarchy, density, spacing, typography scale, color tendency, corners, shadows, navigation, cards, buttons, and list patterns.

The prototype must use original branding and mock content. Include confirmed navigation and local, demonstrable states such as empty, loading, success, and failure where applicable. Exclude authentication, membership, subscriptions, payment, real backends, competitor APIs, and external side effects.

Run `scripts/verify_flutter.py --output <output-dir> --run` when Flutter is installed. Verify routes, core flows, local state synchronization, and that excluded flows were not generated. If Flutter is unavailable, record that validation was not run rather than claiming success.

### 6. One final confirmation and PRD

Never generate the final PRD until the user explicitly confirms the actual final product-model version. This is the only post-evidence confirmation needed when the user selected `draft_prototype` at preflight. Record the approval with `scripts/approve_model.py --output <output-dir> --version <version>`, then run `scripts/generate_prd.py --output <output-dir>`. This creates `docs/PRD.md` in Markdown with:

1. document information and change log;
2. scope and non-goals;
3. information architecture and functional flows;
4. functional specifications;
5. page specifications;
6. device capabilities and page states;
7. acceptance criteria.

Do not add feature-purpose boilerplate, authentication/payment flows, competitor backend details, or unsupported claims.

## Response format

At each stage, report:

1. completed artifacts;
2. evidence and confidence level;
3. skipped or blocked paths and why;
4. the next action only when it blocks a deliverable the user asked for.
