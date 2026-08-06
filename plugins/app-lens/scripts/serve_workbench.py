#!/usr/bin/env python3
"""Serve the local product-decision workbench for one analysis output directory."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from model_tools import adopt_all_abstract_features, approval_fingerprint, append_audit, load_model, model_path, utc_now, validation_errors, write_json


MAX_BODY_BYTES = 5 * 1024 * 1024


class WorkbenchServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], output_dir: Path, web_root: Path) -> None:
        super().__init__(address, handler)
        self.output_dir = output_dir
        self.web_root = web_root


class Handler(BaseHTTPRequestHandler):
    server: WorkbenchServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[workbench] {self.address_string()} {format % args}")

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def read_body(self) -> dict[str, Any]:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ValueError("Content-Length is required.")
        length = int(content_length)
        if length < 1 or length > MAX_BODY_BYTES:
            raise ValueError("Request body size is invalid.")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Request payload must be an object.")
        return payload

    @staticmethod
    def safe_file(root: Path, relative_path: str) -> Path | None:
        candidate = (root / relative_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def serve_file(self, path: Path) -> None:
        content_type, _ = mimetypes.guess_type(path.name)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        request_path = unquote(urlparse(self.path).path)
        if request_path == "/api/model":
            try:
                self.send_json(HTTPStatus.OK, {"model": load_model(self.server.output_dir)})
            except (OSError, ValueError) as error:
                self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
            return
        if request_path == "/api/status":
            self.send_json(HTTPStatus.OK, {"output_dir": str(self.server.output_dir), "served_at": utc_now()})
            return
        if request_path.startswith("/output/"):
            file_path = self.safe_file(self.server.output_dir, request_path.removeprefix("/output/"))
        else:
            relative = "index.html" if request_path in {"/", ""} else request_path.removeprefix("/")
            file_path = self.safe_file(self.server.web_root, relative)
        if file_path is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.serve_file(file_path)

    def do_PUT(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/model":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self.read_body()
            model = payload.get("model")
            if not isinstance(model, dict):
                raise ValueError("model must be an object.")
            adopt_all_abstract_features(model)
            errors = validation_errors(model)
            if errors:
                self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"errors": errors})
                return
            existing = load_model(self.server.output_dir)
            existing_generation = existing.get("generation", {}) if isinstance(existing.get("generation"), dict) else {}
            if existing_generation.get("approved_model_version") and existing_generation.get("approved_model_fingerprint") != approval_fingerprint(model):
                model["project"]["status"] = "model_review"
                generation = model.setdefault("generation", {})
                generation["approved_model_version"] = None
                generation["approved_at"] = None
                generation["approved_model_fingerprint"] = None
                generation["prd_status"] = "blocked_pending_confirmation"
                append_audit(model, "confirmation_invalidated", {"reason": "editable product decisions changed"})
            append_audit(model, "workbench_saved", {"source": "local_workbench"})
            write_json(model_path(self.server.output_dir), model)
            self.send_json(HTTPStatus.OK, {"model": model})
        except (ValueError, json.JSONDecodeError, OSError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        request_path = urlparse(self.path).path
        if request_path == "/api/adopt-all":
            try:
                model = load_model(self.server.output_dir)
                errors = validation_errors(model)
                if errors:
                    self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"errors": errors})
                    return
                adopted_count, _changed = adopt_all_abstract_features(model)
                append_audit(model, "bulk_adoption_requested", {"count": adopted_count, "mode": "original_abstract_features"})
                write_json(model_path(self.server.output_dir), model)
                self.send_json(HTTPStatus.OK, {"model": model, "adopted_count": adopted_count})
            except (ValueError, json.JSONDecodeError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if request_path != "/api/confirm":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self.read_body()
            version = payload.get("version")
            if not isinstance(version, str) or not version.strip():
                raise ValueError("A final version is required.")
            model = load_model(self.server.output_dir)
            adopt_all_abstract_features(model)
            errors = validation_errors(model)
            if errors:
                self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"errors": errors})
                return
            project = model["project"]
            project["version"] = version.strip()
            project["status"] = "confirmed"
            generation = model.setdefault("generation", {})
            generation["approved_model_version"] = version.strip()
            generation["approved_at"] = utc_now()
            generation["approved_model_fingerprint"] = approval_fingerprint(model)
            generation["prd_status"] = "ready_to_generate"
            append_audit(model, "model_confirmed", {"version": version.strip(), "source": "local_workbench"})
            write_json(model_path(self.server.output_dir), model)
            self.send_json(HTTPStatus.OK, {"model": model})
        except (ValueError, json.JSONDecodeError, OSError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory containing project-model.json")
    parser.add_argument("--port", type=int, default=8765)
    arguments = parser.parse_args()
    output_dir = arguments.output.expanduser().resolve()
    if not (output_dir / "project-model.json").is_file():
        print("project-model.json is required. Run bootstrap_project.py first.", file=sys.stderr)
        return 2
    web_root = Path(__file__).resolve().parent.parent / "workbench"
    if not (web_root / "index.html").is_file():
        print("Workbench assets are missing from the plugin.", file=sys.stderr)
        return 2
    server = WorkbenchServer(("127.0.0.1", arguments.port), Handler, output_dir, web_root)
    print(f"Open http://127.0.0.1:{arguments.port} in a browser. Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWorkbench stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
