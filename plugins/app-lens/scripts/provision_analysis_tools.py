#!/usr/bin/env python3
"""Download and prepare the required AppLens analysis toolchain locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as element_tree
import zipfile
from pathlib import Path
from typing import Any

from analysis_toolchain import ToolchainError, require_full_toolchain, resolve_required_tools
from model_tools import utc_now, write_json


JADX_RELEASE_API = "https://api.github.com/repos/skylot/jadx/releases/latest"
AAPT2_METADATA_URL = "https://dl.google.com/android/maven2/com/android/tools/build/aapt2/maven-metadata.xml"
ADOPTIUM_JRE_API = "https://api.adoptium.net/v3/assets/latest/21/hotspot"
DOWNLOAD_TIMEOUT_SECONDS = 300


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AppLens-toolchain-bootstrap/1"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read()


def fetch_json(url: str) -> Any:
    return json.loads(fetch_bytes(url).decode("utf-8"))


def download(url: str, destination: Path, expected_sha256: str | None = None, expected_sha1: str | None = None) -> dict[str, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        actual_sha256 = sha256(destination)
        actual_sha1 = sha1(destination)
    else:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                request = urllib.request.Request(url, headers={"User-Agent": "AppLens-toolchain-bootstrap/1"})
                with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                    shutil.copyfileobj(response, target, length=1024 * 1024)
            temporary.replace(destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        actual_sha256 = sha256(destination)
        actual_sha1 = sha1(destination)
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        raise RuntimeError(f"SHA-256 verification failed for {destination.name}")
    if expected_sha1 and actual_sha1.lower() != expected_sha1.lower():
        raise RuntimeError(f"SHA-1 verification failed for {destination.name}")
    return {"sha256": actual_sha256, "sha1": actual_sha1}


def host_platform() -> tuple[str, str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin":
        return "osx", "mac", "aarch64" if machine in {"arm64", "aarch64"} else "x64"
    if system == "Linux":
        return "linux", "linux", "aarch64" if machine in {"arm64", "aarch64"} else "x64"
    raise RuntimeError(f"Automatic tool provisioning is not supported on {system} ({machine}).")


def safe_extract_zip(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            candidate = (destination / info.filename).resolve()
            try:
                candidate.relative_to(destination.resolve())
            except ValueError as error:
                raise RuntimeError(f"Unsafe archive path: {info.filename}") from error
            file_type = info.external_attr >> 16 & 0o170000
            if file_type == stat.S_IFLNK:
                raise RuntimeError(f"Refusing symbolic link in downloaded archive: {info.filename}")
        archive.extractall(destination)


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            candidate = (destination / member.name).resolve()
            try:
                candidate.relative_to(destination.resolve())
            except ValueError as error:
                raise RuntimeError(f"Unsafe archive path: {member.name}") from error
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError(f"Refusing link or device in downloaded archive: {member.name}")
        archive.extractall(destination)


def executable(root: Path, name: str) -> Path:
    candidates = sorted(path for path in root.rglob(name) if path.is_file())
    if not candidates:
        raise RuntimeError(f"Downloaded tool archive did not contain {name}.")
    path = candidates[0]
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def latest_aapt2(tool_root: Path, maven_os: str) -> tuple[Path, dict[str, Any]]:
    metadata = element_tree.fromstring(fetch_bytes(AAPT2_METADATA_URL))
    version = metadata.findtext("./versioning/release") or metadata.findtext("./versioning/latest")
    if not version or not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
        raise RuntimeError("Could not read a safe AAPT2 release version from Google's Maven metadata.")
    filename = f"aapt2-{version}-{maven_os}.jar"
    url = f"https://dl.google.com/android/maven2/com/android/tools/build/aapt2/{version}/{filename}"
    expected_sha1 = fetch_bytes(url + ".sha1").decode("utf-8").strip().split()[0]
    if not re.fullmatch(r"[a-fA-F0-9]{40}", expected_sha1):
        raise RuntimeError("Google Maven did not provide a valid AAPT2 SHA-1 checksum.")
    archive = tool_root / "downloads" / filename
    checksums = download(url, archive, expected_sha1=expected_sha1)
    destination = tool_root / "aapt2" / version / maven_os
    safe_extract_zip(archive, destination)
    return executable(destination, "aapt2"), {"version": version, "url": url, "checksums": checksums}


def select_jadx_asset(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
        raise RuntimeError("The JADX release API returned an unexpected response.")
    for asset in payload["assets"]:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if isinstance(name, str) and re.fullmatch(r"jadx-[0-9][0-9A-Za-z.\-]*\.zip", name):
            digest = asset.get("digest")
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                raise RuntimeError("The JADX release asset did not provide a SHA-256 digest.")
            return asset
    raise RuntimeError("The latest JADX release did not include a cross-platform CLI archive.")


def latest_jadx(tool_root: Path) -> tuple[Path, dict[str, Any]]:
    release = fetch_json(JADX_RELEASE_API)
    asset = select_jadx_asset(release)
    name = str(asset["name"])
    url = asset.get("browser_download_url")
    digest = str(asset["digest"]).removeprefix("sha256:")
    tag = release.get("tag_name") if isinstance(release, dict) else None
    if not isinstance(url, str) or not isinstance(tag, str):
        raise RuntimeError("The JADX release metadata was incomplete.")
    archive = tool_root / "downloads" / name
    checksums = download(url, archive, expected_sha256=digest)
    destination = tool_root / "jadx" / tag.removeprefix("v")
    safe_extract_zip(archive, destination)
    return executable(destination, "jadx"), {"version": tag, "url": url, "checksums": checksums}


def system_java_home() -> str | None:
    java_home = os.environ.get("JAVA_HOME")
    if java_home and (Path(java_home) / "bin" / "java").is_file():
        return java_home
    java = shutil.which("java")
    if java:
        # The wrapper only needs a Java executable already on PATH.
        return None
    return None


def select_jre_package(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("The Eclipse Temurin API returned no JRE release.")
    binaries = payload[0].get("binaries") if isinstance(payload[0], dict) else None
    package = binaries[0].get("package") if isinstance(binaries, list) and binaries and isinstance(binaries[0], dict) else None
    if not isinstance(package, dict):
        raise RuntimeError("The Eclipse Temurin API returned no JRE package.")
    link, checksum, name = package.get("link"), package.get("checksum"), package.get("name")
    if not isinstance(link, str) or not isinstance(checksum, str) or not isinstance(name, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
        raise RuntimeError("The Eclipse Temurin API returned incomplete JRE verification metadata.")
    return package


def latest_jre(tool_root: Path, adoptium_os: str, architecture: str) -> tuple[str, dict[str, Any]]:
    query = f"{ADOPTIUM_JRE_API}?architecture={architecture}&image_type=jre&os={adoptium_os}&vendor=eclipse"
    package = select_jre_package(fetch_json(query))
    archive = tool_root / "downloads" / str(package["name"])
    checksums = download(str(package["link"]), archive, expected_sha256=str(package["checksum"]))
    destination = tool_root / "jre" / str(package["name"]).removesuffix(".tar.gz")
    safe_extract_tar(archive, destination)
    java = executable(destination, "java")
    return str(java.parent.parent), {"url": package["link"], "checksums": checksums, "name": package["name"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Project-local analysis output directory")
    parser.add_argument("--approve-download", action="store_true", help="Required acknowledgement before downloading official tool distributions")
    arguments = parser.parse_args()
    if not arguments.approve_download:
        parser.error("--approve-download is required.")
    output_dir = arguments.output.expanduser().resolve()
    tool_root = output_dir / ".applens-toolchain"
    try:
        maven_os, adoptium_os, architecture = host_platform()
        tools = resolve_required_tools(output_dir=output_dir)
        downloads: dict[str, Any] = {}
        if not tools["aapt"]:
            tools["aapt"], downloads["aapt2"] = latest_aapt2(tool_root, maven_os)
        if not tools["jadx"]:
            tools["jadx"], downloads["jadx"] = latest_jadx(tool_root)
        java_home = system_java_home()
        if java_home is None and not shutil.which("java"):
            java_home, downloads["jre"] = latest_jre(tool_root, adoptium_os, architecture)
        receipt = {
            "schema_version": "1.0",
            "created_at": utc_now(),
            "policy": "required_full_analysis_toolchain",
            "download_authorization": "explicit_cli_acknowledgement",
            "tools": {name: path for name, path in tools.items() if isinstance(path, str)},
            "java_home": java_home,
            "downloads": downloads,
        }
        write_json(output_dir / "evidence" / "toolchain.json", receipt)
        require_full_toolchain(output_dir)
    except (OSError, ToolchainError, RuntimeError, ValueError, urllib.error.URLError, zipfile.BadZipFile, tarfile.TarError, element_tree.ParseError) as error:
        print(f"Tool provisioning failed: {error}", file=sys.stderr)
        return 2
    print(output_dir / "evidence" / "toolchain.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
