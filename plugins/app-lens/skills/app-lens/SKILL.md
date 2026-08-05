---
name: app-lens
description: Analyze a user-authorized Android APK into evidence, an editable product model, an original Flutter reference prototype, and a Markdown PRD. Use when the user asks to analyze an Android competitor app, turn an APK into a product-function map, create a Flutter reference prototype from APK evidence, or generate a PRD after a reviewed product decision.
---

# AppLens

Use this Skill only for a user-provided APK the user is authorized to inspect. Treat the result as a product reference, never as a request to copy an application.

## Safety boundaries

- Keep all APKs, extracted files, screenshots, evidence, model files, prototypes, and PRDs in the user's current workspace unless the user explicitly requests another project-local path.
- Do not extract, display, reproduce, or use API URLs, authentication material, tokens, keys, credentials, private user data, or backend logic.
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
  static-inventory.json
  reverse-static.json
  reverse-decompiled/  # local opaque working data; never used in generated deliverables
  screenshots/
  paths/
flutter_prototype/
docs/
  PRD.md
  CHANGELOG.md
```

`project-model.json` is authoritative. HTML workspaces, the Flutter prototype, and the PRD are derived artifacts.

## Workflow

### 1. One-time preflight and run brief

Extract already explicit facts from the user's first request; do not ask again for an authorization or emulator choice the user has already stated. Establish the following once per output directory:

- path to the user-provided `.apk` file;
- project-local output directory;
- explicit authorization to inspect the APK;
- exploration plan: `static_only` or `dynamic`; for dynamic, whether static fallback is permitted;
- requested delivery: `evidence`, `model`, or `draft_prototype`.

If any required fact is missing, ask one compact, combined question rather than staging several approval questions. Use this reply format:

```text
APK: <path>; output: <project-local directory>; authorized: yes;
exploration: static_only | dynamic; fallback: yes | no; delivery: evidence | model | draft_prototype
```

Treat `dynamic` as permission to use only a resettable isolated emulator. Never infer it from the presence of `adb` or an emulator. `draft_prototype` authorizes an original, review-ready draft—not a final PRD.

From the plugin root, run the preflight command exactly as follows:

```text
scripts/preflight.sh
```

`preflight.sh` is an executable Shell script; do not infer a `.py` extension or invoke `preflight.py`. Report missing optional tools without installing anything unless the user separately asks to install them.

Accept only a user-provided `.apk` file as input. Do not connect to a real device or retrieve installed application packages through ADB.

After the user's one-time confirmation, record it before collecting evidence. Pass `--confirm-isolated-emulator` only for an explicitly selected dynamic plan:

```text
scripts/configure_run.py --apk <apk-path> --output <output-dir> --workspace <workspace-dir> --confirm-user-authorized-apk --exploration static_only --delivery <evidence|model|draft_prototype>
```

For an authorized dynamic plan, use `--exploration dynamic --confirm-isolated-emulator`; add `--allow-static-fallback` only when the user selected fallback. `evidence/run-brief.json` is the auditable record of the selected plan. Do not turn its flags into a substitute for a user statement.

### 2. Static inventory

Run these commands in order:

```text
scripts/static_inventory.py <apk-path> --output <output-dir>
scripts/reverse_static_inventory.py <apk-path> --output <output-dir>
scripts/bootstrap_project.py --evidence <output-dir>/evidence/static-inventory.json --output <output-dir>
scripts/derive_candidates.py --output <output-dir>
```

Use the inventories only as evidence: package metadata, declared permissions, component names, resource inventory, native ABI hints, Android-tool output, and restricted reverse-static UI structure where available. Do not infer a user-facing feature solely from an ambiguous technical artifact. The reverse-static layer must contribute only its generic UI component counts and product signals; never read or include raw decompiled source.

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

If the application cannot run because of architecture, emulator detection, special hardware, or another limitation, retain static findings and label dynamic evidence unavailable. Do not bypass the restriction.

Run dynamic commands only when `evidence/run-brief.json` records the dynamic plan. Install the input package with `scripts/install_to_emulator.py`, then invoke `scripts/safe_explore.py --serial <emulator-serial> --package <package> --output <output-dir> --confirm-isolated-emulator`. The explorer refuses non-emulator targets, captures only non-interception screenshots, and skips high-risk or unnamed controls. Run `scripts/ingest_dynamic_evidence.py --output <output-dir>` afterward.

When dynamic exploration is unavailable and the brief permits static fallback, continue automatically with static evidence, mark dynamic evidence unavailable, and deliver the selected static-mode result. When fallback was not permitted, stop before dynamic installation and report the limitation.

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
