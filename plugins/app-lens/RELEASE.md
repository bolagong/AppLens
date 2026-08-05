# Release guide

## Publish layout

The repository already contains this publish layout; keep it intact when pushing:

```text
.agents/plugins/marketplace.json
plugins/app-lens/
```

`.agents/plugins/marketplace.json` is the release manifest. `marketplace.json.template` is included for forks or a separately created Marketplace repository. The Marketplace source path is relative to the release repository root.

## Release checks

From the repository root, run:

```text
plugins/app-lens/scripts/validate_release.py
plugins/app-lens/scripts/preflight.sh
```

For a representative authorized APK, run the full static-to-PRD workflow and verify the generated Flutter prototype with `verify_flutter.py --run`.

## Consumer installation

After the release repository is available, a Codex user installs it with:

```text
codex plugin marketplace add <owner>/<repository> --ref <release-tag-or-branch>
codex plugin add app-lens@app-lens
```

The user should start a new Codex thread after installing or upgrading the plugin.

## Before every public release

1. Update `.codex-plugin/plugin.json` version and user-facing description.
2. Run the release checks and record their output in the release notes.
3. Confirm that the Skill accepts only user-provided `.apk` files and still excludes real-device connections, credentials, API discovery, authentication, commercial flows, external actions, competitor assets, and real backend generation.
4. Test on a resettable emulator only. Do not include a competitor APK, decompiled code, screenshots with personal data, or generated analysis artifacts in the public repository.
