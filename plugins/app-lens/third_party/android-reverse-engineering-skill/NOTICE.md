# Third-party notice

`decompile.sh` is a modified copy of the JADX decompilation wrapper from
[CreditTone/android-reverse-engineering-skill](https://github.com/CreditTone/android-reverse-engineering-skill),
retrieved from the `master` branch on 2026-08-05.

It is included under the upstream Apache License 2.0; see [LICENSE](LICENSE).
The AppLens copy accepts only a user-provided `.apk` through the `jadx` engine;
it rejects XAPK, JAR, AAR, deobfuscation, Fernflower, and multi-engine modes.
AppLens invokes it only through `scripts/reverse_static_inventory.py` with
`--no-res`. AppLens does not use the upstream API-extraction, credential,
Frida, traffic-capture, signature, or bypass workflows.
