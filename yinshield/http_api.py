"""Local HTTP bridge for YinShield."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from typing import Any, Dict, Optional, Tuple

from . import __version__
from .core import Shield, ShieldSession
from .openai import mask_messages

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 27811


def generate_auth_token() -> str:
    return secrets.token_urlsafe(24)


@dataclass(frozen=True)
class SessionConfig:
    mode: str
    strategy: str
    auth_token: Optional[str]


class ServiceState:
    def __init__(
        self,
        mode: str = "placeholder",
        strategy: str = "balanced",
        session_file: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        self.mode = mode
        self.strategy = strategy
        self.session_file = session_file
        self.auth_token = auth_token
        self._lock = threading.RLock()
        self._sessions: Dict[str, ShieldSession] = {}
        if session_file:
            self._load_sessions(session_file)

    def health_payload(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "service": "yinshield",
                "version": __version__,
                "mode": self.mode,
                "strategy": self.strategy,
                "auth_enabled": bool(self.auth_token),
                "stateless_by_default": True,
                "session_count": len(self._sessions),
            }

    def mask_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = payload.get("text")
        if not isinstance(text, str):
            raise ValueError("text_must_be_string")
        shield, session, should_persist = self._resolve_context(payload)

        mapping = payload.get("mapping")
        if mapping is not None and not isinstance(mapping, dict):
            raise ValueError("mapping_must_be_object")

        if mapping is not None:
            active_session = ShieldSession.from_dict({"replacements_to_originals": mapping})
            masked_text, masked_mapping = shield.mask(text, session=active_session)
        else:
            masked_text, masked_mapping = shield.mask(text, session=session)
            if should_persist:
                self._persist_sessions()

        result: Dict[str, Any] = {"text": masked_text, "mapping": masked_mapping}
        session_id = payload.get("session_id")
        if isinstance(session_id, str):
            result["session_id"] = session_id
        return result

    def mask_messages(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("messages_must_be_array")
        shield, session, should_persist = self._resolve_context(payload)

        mapping = payload.get("mapping")
        if mapping is not None and not isinstance(mapping, dict):
            raise ValueError("mapping_must_be_object")

        if mapping is not None:
            active_session = ShieldSession.from_dict({"replacements_to_originals": mapping})
            masked_messages, masked_mapping = mask_messages(messages, shield, session=active_session)
        else:
            masked_messages, masked_mapping = mask_messages(messages, shield, session=session)
            if should_persist:
                self._persist_sessions()

        result: Dict[str, Any] = {"messages": masked_messages, "mapping": masked_mapping}
        session_id = payload.get("session_id")
        if isinstance(session_id, str):
            result["session_id"] = session_id
        return result

    def unmask_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = payload.get("text")
        mapping = payload.get("mapping")
        if not isinstance(text, str):
            raise ValueError("text_must_be_string")
        if not isinstance(mapping, dict):
            raise ValueError("mapping_must_be_object")
        return {"text": Shield(mode=self.mode, strategy=self.strategy).unmask(text, mapping)}

    def validate_auth(self, headers: Any) -> None:
        if not self.auth_token:
            return

        bearer = headers.get("Authorization", "")
        if bearer.startswith("Bearer "):
            presented = bearer[len("Bearer ") :]
        else:
            presented = headers.get("X-YinShield-Token", "")
        if presented != self.auth_token:
            raise PermissionError("invalid_auth_token")

    def _resolve_context(self, payload: Dict[str, Any]) -> Tuple[Shield, Optional[ShieldSession], bool]:
        mode = payload.get("mode", self.mode)
        strategy = payload.get("strategy", self.strategy)
        shield = Shield(mode=mode, strategy=strategy)
        session_id = payload.get("session_id")

        if payload.get("mapping") is not None:
            return shield, None, False
        if session_id is None:
            return shield, None, False
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id_must_be_non_empty_string")

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = ShieldSession()
                self._sessions[session_id] = session
        return shield, session, True

    def _load_sessions(self, path: str) -> None:
        target = Path(path)
        if not target.exists():
            return
        payload = json.loads(target.read_text(encoding="utf-8"))
        sessions = payload.get("sessions", {})
        if not isinstance(sessions, dict):
            return
        with self._lock:
            for session_id, session_payload in sessions.items():
                if not isinstance(session_id, str) or not isinstance(session_payload, dict):
                    continue
                self._sessions[session_id] = ShieldSession.from_dict(session_payload)

    def _persist_sessions(self) -> None:
        if not self.session_file:
            return
        target = Path(self.session_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "config": {
                    "mode": self.mode,
                    "strategy": self.strategy,
                    "auth_enabled": bool(self.auth_token),
                },
                "sessions": {session_id: session.to_dict() for session_id, session in self._sessions.items()},
            }
            temp_path = target.with_suffix(f".{secrets.token_hex(4)}.tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(target)


class YinShieldHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        mode: str = "placeholder",
        strategy: str = "balanced",
        session_file: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        super().__init__(server_address, YinShieldHandler)
        self.state = ServiceState(mode=mode, strategy=strategy, session_file=session_file, auth_token=auth_token)


class YinShieldHandler(BaseHTTPRequestHandler):
    server: YinShieldHTTPServer

    def do_POST(self) -> None:  # noqa: N802
        try:
            self.server.state.validate_auth(self.headers)
            payload = self._read_json()
            if self.path == "/health":
                self._write_json(HTTPStatus.OK, self.server.state.health_payload())
                return
            if self.path == "/mask":
                self._write_json(HTTPStatus.OK, self.server.state.mask_text(payload))
                return
            if self.path == "/unmask":
                self._write_json(HTTPStatus.OK, self.server.state.unmask_text(payload))
                return
            if self.path == "/messages/mask":
                self._write_json(HTTPStatus.OK, self.server.state.mask_messages(payload))
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except PermissionError as exc:
            self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(parsed, dict):
            raise ValueError("json_body_must_be_object")
        return parsed

    def _write_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_health_payload(state_or_shield: Any) -> Dict[str, Any]:
    if isinstance(state_or_shield, ServiceState):
        return state_or_shield.health_payload()
    if isinstance(state_or_shield, Shield):
        return {
            "ok": True,
            "service": "yinshield",
            "version": __version__,
            "mode": state_or_shield.mode,
            "strategy": state_or_shield.strategy,
            "auth_enabled": False,
            "stateless_by_default": True,
            "session_count": 0,
        }
    raise TypeError("expected ServiceState or Shield")


def mask_payload(payload: Dict[str, Any], state_or_shield: Any) -> Dict[str, Any]:
    if isinstance(state_or_shield, ServiceState):
        return state_or_shield.mask_text(payload)
    if isinstance(state_or_shield, Shield):
        state = ServiceState(mode=state_or_shield.mode, strategy=state_or_shield.strategy)
        return state.mask_text(payload)
    raise TypeError("expected ServiceState or Shield")


def unmask_payload(payload: Dict[str, Any], state_or_shield: Any) -> Dict[str, Any]:
    if isinstance(state_or_shield, ServiceState):
        return state_or_shield.unmask_text(payload)
    if isinstance(state_or_shield, Shield):
        state = ServiceState(mode=state_or_shield.mode, strategy=state_or_shield.strategy)
        return state.unmask_text(payload)
    raise TypeError("expected ServiceState or Shield")


def mask_messages_payload(payload: Dict[str, Any], state_or_shield: Any) -> Dict[str, Any]:
    if isinstance(state_or_shield, ServiceState):
        return state_or_shield.mask_messages(payload)
    if isinstance(state_or_shield, Shield):
        state = ServiceState(mode=state_or_shield.mode, strategy=state_or_shield.strategy)
        return state.mask_messages(payload)
    raise TypeError("expected ServiceState or Shield")


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    mode: str = "placeholder",
    strategy: str = "balanced",
    session_file: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> int:
    effective_auth_token = auth_token or generate_auth_token()
    server = YinShieldHTTPServer(
        (host, port),
        mode=mode,
        strategy=strategy,
        session_file=session_file,
        auth_token=effective_auth_token,
    )
    try:
        print(f"YinShield listening on http://{host}:{port}")
        print(f"YinShield auth token: {effective_auth_token}")
        if not auth_token:
            print("YinShield generated a temporary auth token for this run.")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
