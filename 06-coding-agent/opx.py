#!/usr/bin/env python3
import os
import re
import sys
import time
import json
import shlex
import socket
import fnmatch
import textwrap
import platform
import ipaddress
import subprocess
import unicodedata
import http.client
import urllib.error
import urllib.request
import concurrent.futures
from html.parser import HTMLParser

def _system_prompt():
    os_name = platform.platform() or platform.system() or "Unknown OS"
    sys_prompt = (
        f"You are running on {os_name}. You are a mighty Linux system operator. Use tools as many times as you require to solve the given task. "
        "Make short answers. Never ask the user any questions, always try to use tools to answer them yourself. "
        "Never try something that you tried before without success."
    )
    # print(sys_prompt) # debug
    return sys_prompt

SYSTEM_PROMPT = _system_prompt()

OPENAI_BASE_URL = os.environ["OPENAI_BASE_URL"].rstrip("/")
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.environ["OPENAI_MODEL"]
OPENAI_TEMPERATURE = float(os.environ["OPENAI_TEMPERATURE"])
OPENAI_REASONING_EFFORT = os.environ["OPENAI_REASONING_EFFORT"]
DEFAULT_TOOL_TIMEOUT_SEC = int((os.environ.get("OPX_TOOL_TIMEOUT_SEC") or "300").strip() or "300")
DEFAULT_MAX_TURNS = int((os.environ.get("OPX_MAX_TURNS") or "24").strip() or "24")

def _http_request(method, path, body=None, read_body=True, leave_open=False):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{OPENAI_BASE_URL}{path}",
        data=body.encode("utf-8") if isinstance(body, str) else body,
        headers=headers,
        method=method,
    )
    try:
        resp = urllib.request.urlopen(request, timeout=600)
        if not read_body:
            return resp, None
        return resp, resp.read()
    except (OSError, urllib.error.URLError):
        return None, None
    finally:
        if not leave_open and "resp" in locals():
            resp.close()

def classifier(classes_description, classes, proposition, compute_confidence=True, binary=True):
    schema = {
        "title": "Classifier",
        "type": "object",
        "properties": {"classification": {"type": "literal", "enum": classes}},
        "required": ["classification"],
    }
    if compute_confidence:
        schema["properties"]["confidence"] = {"type": "number", "minimum": 0, "maximum": 100}
        schema["required"].append("confidence")
    messages = [
        {"role": "system", "content": classes_description},
        {"role": "user", "content": proposition},
    ]
    data = {
        "model": OPENAI_MODEL,
        "temperature": OPENAI_TEMPERATURE,
        "reasoning_effort": OPENAI_REASONING_EFFORT,
        "max_tokens": 2048,
        "messages": messages,
        "stream": False,
        "response_format": {"type": "json_schema", "json_schema": {"strict": True, "schema": schema}},
    }
    resp, raw = _http_request("POST", "/v1/chat/completions", json.dumps(data))
    if not resp or not raw: return "", 0.0
    try:
        response = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return "", 0.0
    content_text = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    try:
        content = json.loads(content_text)
    except json.JSONDecodeError:
        content = {}
    classification = content.get("classification", "")
    if classification.startswith("'"): classification = classification[1:]
    if classification.endswith("'"): classification = classification[:-1]
    confidence = content.get("confidence", 0.5) if compute_confidence else 1.0
    if confidence > 1: confidence = confidence / 100
    return classification, confidence

def truth_test(classes_description, proposition, compute_confidence=True):
    classification, confidence = classifier(classes_description, ["true", "false"], proposition, compute_confidence=compute_confidence, binary=True)
    return classification == "true", confidence

def _format_conversation(messages):
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        if role == "assistant" and "tool_calls" in msg:
            parts.append(f"assistant tool_calls: {json.dumps(msg.get('tool_calls'))}")
            continue
        content = msg.get("content")
        if content is not None: parts.append(f"{role}: {content}")
    return "\n\n".join(parts)

def _build_follow_up_prompt(conversation, initial_prompt):
    system_prompt = (
        "You create follow-up prompts for a model to complete the original request."
        " Return only the follow-up prompt, no extra text."
    )
    user_prompt = (
        "Initial request:\n"
        f"{initial_prompt}\n\n"
        "Conversation so far:\n"
        f"{conversation}\n\n"
        "Review the answer and construct a prompt that uses the activities and their effect "
        "so far to define a new prompt which shall work toward a solution of the initial prompt. "
        "Don't try anything that you already tried before without success. Do something new."
    )
    data = {
        "model": OPENAI_MODEL,
        "temperature": OPENAI_TEMPERATURE,
        "reasoning_effort": OPENAI_REASONING_EFFORT,
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    resp, raw = _http_request("POST", "/v1/chat/completions", json.dumps(data))
    if not resp or not raw:
        return ""
    try:
        response = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return ""
    content_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content_text.strip()

approval_always_read = True
approval_always_write = False

def request_tool_approval(subject, write_request):
    global approval_always_read, approval_always_write
    auto_approve = (os.environ.get("OPX_AUTO_APPROVE") or "").strip().lower()
    if auto_approve in ("1", "true", "yes", "all"):
        return True
    if auto_approve == "read" and not write_request:
        return True
    if auto_approve == "write" and write_request:
        return True
    if auto_approve in ("0", "false", "no", "none"):
        return False
    if write_request and approval_always_write:
        return True
    if not write_request and approval_always_read:
        return True
    default_prompt = "[y/N]" if write_request else "[Y/n]"
    subject_line = " ".join(str(subject).split())
    if len(subject_line) > 120: subject_line = subject_line[:117] + "..."
    termprint("paragraph", f"Approve '{subject_line}', {default_prompt} (a=always):")
    resp = sys.stdin.readline().strip().lower()
    if resp == "a":
        if write_request:
            approval_always_write = True
        else:
            approval_always_read = True
        return True
    if (not resp): return not write_request # default value from request options
    return resp in ["Y", "y", "yes"]

def _load_tool_args(arguments):
    if not arguments:
        return None
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return None

def tool_description(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
            "strict": True,
        },
    }

def _path_tool_description(name, description):
    return tool_description(
        name,
        description,
        {
            "path": {
                "type": "string",
                "description": "Path to target.",
            }
        },
        ["path"],
    )

class BaseTool:
    name = ""

    def describe(self):
        raise NotImplementedError

    def max_calls_per_turn(self):
        raise NotImplementedError

    def argument_spec(self):
        return {}

    def parse_arguments(self, arguments):
        args = _load_tool_args(arguments)
        if not isinstance(args, dict):
            return None
        spec = self.argument_spec()
        if not spec:
            return {}
        parsed = {}
        for key, expected_type in spec.items():
            if key not in args:
                continue
            value = args.get(key)
            if value is None:
                # Treat explicit null like an omitted optional field.
                continue
            if expected_type is str:
                if not isinstance(value, str):
                    return None
            elif not isinstance(value, expected_type):
                return None
            parsed[key] = value
        return parsed

    def handle(self, **kwargs):
        raise NotImplementedError

    def handle_request(self, tool_request):
        return self.handle(**tool_request)

class BashTool(BaseTool):
    name = "bash"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"command": str}

    def describe(self):
        return tool_description(
            "bash",
            "Run a shell command via /bin/bash and return stdout/stderr.",
            {
                "command": {
                    "type": "string",
                    "description": "Shell command to run.",
                }
            },
            ["command"],
        )

    def handle(self, command=None, **_):
        if not command:
            return {"tool": "bash", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Empty command", "data": {}, "message": "Empty command"}
        if re.search(r"^\s*find\s+/\b", command) and "-maxdepth" not in command:
            reject_msg = "Rejected: broad 'find /' without -maxdepth is too expensive; narrow the path."
            return {"tool": "bash", "ok": False, "exit_code": 1, "stdout": "", "stderr": reject_msg, "data": {"command": command}, "message": reject_msg}
        if not request_tool_approval(f"bash: {command}", write_request=True):
            reject_msg = "Rejected by user, try a different approach"
            return {"tool": "bash", "ok": False, "exit_code": 1, "stdout": "", "stderr": reject_msg, "data": {}, "message": reject_msg}
        start_exec = time.monotonic()
        try:
            completed = subprocess.run(
                ["/bin/bash", "-lc", command],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_exec = time.monotonic() - start_exec
            partial_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            partial_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            timeout_msg = "Timed out after 10s"
            combined_stderr = f"{timeout_msg}\n{partial_stderr}".strip() if partial_stderr else timeout_msg
            return {
                "tool": "bash",
                "ok": False,
                "exit_code": 124,
                "stdout": partial_stdout,
                "stderr": combined_stderr,
                "data": {"command": command, "elapsed_exec_sec": elapsed_exec},
                "message": "Tool timeout",
            }
        except OSError as exc:
            return {"tool": "bash", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        elapsed_exec = time.monotonic() - start_exec
        return {
            "tool": "bash",
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "data": {"command": command, "elapsed_exec_sec": elapsed_exec},
        }

class GitTool(BaseTool):
    name = "git"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"args": list}

    def describe(self):
        return tool_description(
            "git",
            "Run a safe, read-only git command and return stdout/stderr.",
            {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Git arguments, e.g. [\"status\", \"-sb\"].",
                }
            },
            ["args"],
        )

    def handle(self, args=None, **_):
        if not isinstance(args, list) or not args:
            return {"tool": "git", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing args", "data": {}, "message": "Missing args"}
        subcommand = args[0]
        allowed = {"status", "diff", "show", "log", "branch", "rev-parse", "ls-files"}
        if subcommand not in allowed:
            reject_msg = f"Rejected: unsafe git subcommand '{subcommand}'"
            return {"tool": "git", "ok": False, "exit_code": 1, "stdout": "", "stderr": reject_msg, "data": {}, "message": reject_msg}
        if not request_tool_approval(f"git {shlex.join(args)}", write_request=False):
            reject_msg = "Rejected by user, try a different approach"
            return {"tool": "git", "ok": False, "exit_code": 1, "stdout": "", "stderr": reject_msg, "data": {}, "message": reject_msg}
        try:
            completed = subprocess.run(["git", *args], capture_output=True, text=True)
        except OSError as exc:
            return {"tool": "git", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        return {"tool": "git", "ok": completed.returncode == 0, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "data": {"args": args}}

class GrepTool(BaseTool):
    name = "grep"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"pattern": str, "path": str, "case_sensitive": bool}

    def describe(self):
        return tool_description(
            "grep",
            "Search files with ripgrep and return matching lines.",
            {
                "pattern": {"type": "string", "description": "Search pattern (regex)."},
                "path": {"type": "string", "description": "File or directory to search."},
                "case_sensitive": {"type": "boolean", "description": "Case-sensitive search (default true)."},
            },
            ["pattern", "path"],
        )

    def handle(self, pattern=None, path=None, case_sensitive=True, **_):
        if not pattern or not path:
            return {"tool": "grep", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing pattern or path", "data": {}, "message": "Missing pattern or path"}
        if not request_tool_approval(f"grep {pattern} in {path}", write_request=False):
            reject_msg = "Rejected by user, try a different approach"
            return {"tool": "grep", "ok": False, "exit_code": 1, "stdout": "", "stderr": reject_msg, "data": {}, "message": reject_msg}
        args = ["rg", "-n"]
        if not case_sensitive:
            args.append("-i")
        args.extend([pattern, path])
        try:
            completed = subprocess.run(args, capture_output=True, text=True)
        except OSError as exc:
            return {"tool": "grep", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        ok = completed.returncode in (0, 1)
        return {"tool": "grep", "ok": ok, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "data": {"args": args}}

class EditTool(BaseTool):
    name = "edit"

    def max_calls_per_turn(self):
        return 5

    def argument_spec(self):
        return {"diff": str}

    def describe(self):
        return tool_description(
            "edit",
            "Apply a unified diff to edit or patch files.",
            {
                "diff": {
                    "type": "string",
                    "description": "Unified diff of the file edits to apply.",
                }
            },
            ["diff"],
        )

    def _count_files_changed(self, diff_body):
        files = set()
        for line in diff_body.splitlines():
            if line.startswith("+++ "):
                path = line[4:].strip()
                if path and path != "/dev/null":
                    files.add(path)
        return len(files)

    def handle(self, diff=None, **_):
        if not diff:
            return {"tool": "edit", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Empty diff", "data": {"applied": False, "files_changed": 0}, "message": "Empty diff"}
        termprint("subitem", "Tool request (edit), diff:")
        termprint("box", diff)
        if not request_tool_approval(diff, write_request=True):
            return {"tool": "edit", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {"applied": False, "files_changed": 0}, "message": "Rejected by user"}
        try:
            completed = subprocess.run(
                ["patch", "-p0", "--forward"],
                input=diff,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TOOL_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            return {"tool": "edit", "ok": False, "exit_code": 124, "stdout": "", "stderr": f"Timed out after {DEFAULT_TOOL_TIMEOUT_SEC}s", "data": {"applied": False, "files_changed": 0}, "message": "Tool timeout"}
        except OSError as exc:
            return {"tool": "edit", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {"applied": False, "files_changed": 0}, "message": str(exc)}
        files_changed = self._count_files_changed(diff)
        return {"tool": "edit", "ok": completed.returncode == 0, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "data": {"applied": completed.returncode == 0, "files_changed": files_changed}}

class EditPreviewTool(BaseTool):
    name = "edit_preview"

    def max_calls_per_turn(self):
        return 5

    def argument_spec(self):
        return {"diff": str}

    def describe(self):
        return tool_description(
            "edit_preview",
            "Preview a unified diff without applying it.",
            {
                "diff": {
                    "type": "string",
                    "description": "Unified diff of the file edits to preview.",
                }
            },
            ["diff"],
        )

    def _count_files_changed(self, diff_body):
        files = set()
        for line in diff_body.splitlines():
            if line.startswith("+++ "):
                path = line[4:].strip()
                if path and path != "/dev/null":
                    files.add(path)
        return len(files)

    def handle(self, diff=None, **_):
        if not diff:
            return {"tool": "edit_preview", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Empty diff", "data": {"applied": False, "files_changed": 0}, "message": "Empty diff"}
        termprint("subitem", "Tool request (edit_preview), diff:")
        termprint("box", diff)
        if not request_tool_approval("preview diff", write_request=False):
            return {"tool": "edit_preview", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {"applied": False, "files_changed": 0}, "message": "Rejected by user"}
        files_changed = self._count_files_changed(diff)
        try:
            completed = subprocess.run(
                ["patch", "-p0", "--forward", "--dry-run"],
                input=diff,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TOOL_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            return {"tool": "edit_preview", "ok": False, "exit_code": 124, "stdout": "", "stderr": f"Timed out after {DEFAULT_TOOL_TIMEOUT_SEC}s", "data": {"applied": False, "files_changed": files_changed}, "message": "Tool timeout"}
        except OSError as exc:
            return {"tool": "edit_preview", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {"applied": False, "files_changed": files_changed}, "message": str(exc)}
        return {"tool": "edit_preview", "ok": completed.returncode == 0, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "data": {"applied": False, "files_changed": files_changed}}

class WriteTool(BaseTool):
    name = "write"

    def max_calls_per_turn(self):
        return 5

    def argument_spec(self):
        return {"path": str, "content": str}

    def describe(self):
        return tool_description(
            "write",
            "Create or overwrite a file with provided content.",
            {
                "path": {
                    "type": "string",
                    "description": "Path to the file to create or overwrite.",
                },
                "content": {
                    "type": "string",
                    "description": "Full content of the new file.",
                },
            },
            ["path", "content"],
        )

    def handle(self, path=None, content=None, **_):
        if not path:
            return {"tool": "write", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing path", "data": {}, "message": "Missing path"}
        if content is None:
            return {"tool": "write", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing content", "data": {}, "message": "Missing content"}
        termprint("subitem", f"Tool request (write), path: {path}")
        termprint("box", content)
        approval_subject = f"write to: {path}"
        if os.path.exists(path):
            approval_subject = f"overwrite existing file: {path}"
        if not request_tool_approval(approval_subject, write_request=True):
            return {"tool": "write", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            return {"tool": "write", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        return {"tool": "write", "ok": True, "exit_code": 0, "stdout": "OK\n", "stderr": "", "data": {"path": path, "bytes": len(content.encode("utf-8"))}}

class ReadTool(BaseTool):
    name = "read"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"path": str}

    def describe(self):
        return _path_tool_description(
            "read",
            "Read a text file and return its contents.",
        )

    def handle(self, path=None, **_):
        if not path: return {"tool": "read", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing path", "data": {}, "message": "Missing path"}
        termprint("subitem", f"Tool request (read), path: {path}")
        if not request_tool_approval(f"read from: {path}", write_request=False):
            return {"tool": "read", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = f.read()
        except OSError as exc:
            return {"tool": "read", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        return {"tool": "read", "ok": True, "exit_code": 0, "stdout": data, "stderr": "", "data": {"path": path, "content": data, "bytes": len(data.encode("utf-8"))}}

class ListTool(BaseTool):
    name = "list"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"path": str}

    def describe(self):
        return _path_tool_description(
            "list",
            "List directory entries.",
        )

    def handle(self, path=None, **_):
        if not path: return {"tool": "list", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing path", "data": {}, "message": "Missing path"}
        termprint("subitem", f"Tool request (list), path: {path}")
        if not request_tool_approval(f"list: {path}", write_request=False):
            return {"tool": "list", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        try:
            entries = os.listdir(path)
        except OSError as exc:
            return {"tool": "list", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        entries.sort()
        return {"tool": "list", "ok": True, "exit_code": 0, "stdout": "\n".join(entries) + "\n", "stderr": "", "data": {"files": entries, "count": len(entries)}}

class TreeTool(BaseTool):
    name = "tree"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"path": str, "depth": int}

    def describe(self):
        return tool_description(
            "tree",
            "Create a tree listing up to a maximum depth (1-3).",
            {
                "path": {"type": "string", "description": "Root path for the tree listing."},
                "depth": {"type": "integer", "description": "Maximum depth (1-3)."},
            },
            ["path", "depth"],
        )

    def handle(self, path=None, depth=None, **_):
        if not path:
            return {"tool": "tree", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing path", "data": {}, "message": "Missing path"}
        if not isinstance(depth, int):
            return {"tool": "tree", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing depth", "data": {}, "message": "Missing depth"}
        if depth < 1 or depth > 3:
            return {"tool": "tree", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Depth must be between 1 and 3", "data": {}, "message": "Depth must be between 1 and 3"}
        termprint("subitem", f"Tool request (tree), path: {path}, depth: {depth}")
        if not request_tool_approval(f"tree: {path} (depth {depth})", write_request=False):
            return {"tool": "tree", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        if not os.path.exists(path):
            return {"tool": "tree", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Path not found", "data": {}, "message": "Path not found"}
        if not os.path.isdir(path):
            return {"tool": "tree", "ok": True, "exit_code": 0, "stdout": path + "\n", "stderr": "", "data": {"path": path, "depth": depth}}
        root_label = path.rstrip(os.sep) or path
        lines = [root_label]
        for root, dirs, files in os.walk(path):
            rel = os.path.relpath(root, path)
            root_depth = 0 if rel == "." else rel.count(os.sep) + 1
            if root_depth >= depth:
                dirs[:] = []
            entries = [(name, True) for name in dirs] + [(name, False) for name in files]
            entries.sort(key=lambda x: (not x[1], x[0]))
            for name, is_dir in entries:
                entry_depth = root_depth + 1
                indent = "  " * entry_depth
                suffix = "/" if is_dir else ""
                lines.append(f"{indent}{name}{suffix}")
        return {"tool": "tree", "ok": True, "exit_code": 0, "stdout": "\n".join(lines) + "\n", "stderr": "", "data": {"path": path, "depth": depth}}

class ManTool(BaseTool):
    name = "man"

    def max_calls_per_turn(self):
        return 3

    def argument_spec(self):
        return {"topic": str}

    def describe(self):
        return tool_description(
            "man",
            "Read a system manual page.",
            {"topic": {"type": "string", "description": "Man page topic, e.g. \"ls\"."}},
            ["topic"],
        )

    def handle(self, topic=None, **_):
        if not topic:
            return {"tool": "man", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing topic", "data": {}, "message": "Missing topic"}
        termprint("subitem", f"Tool request (man), topic: {topic}")
        if not request_tool_approval(f"man {topic}", write_request=False):
            return {"tool": "man", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        try:
            completed = subprocess.run(["man", "-P", "cat", topic], capture_output=True, text=True)
        except OSError as exc:
            return {"tool": "man", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        return {"tool": "man", "ok": completed.returncode == 0, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "data": {"topic": topic}}

class MkdirTool(BaseTool):
    name = "mkdir"

    def max_calls_per_turn(self):
        return 5

    def argument_spec(self):
        return {"path": str}

    def describe(self):
        return _path_tool_description(
            "mkdir",
            "Create a new directory.",
        )

    def handle(self, path=None, **_):
        if not path: return {"tool": "mkdir", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing path", "data": {}, "message": "Missing path"}
        termprint("subitem", f"Tool request (mkdir), path: {path}")
        if not request_tool_approval(f"mkdir: {path}", write_request=True):
            return {"tool": "mkdir", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        try:
            os.makedirs(path, exist_ok=False)
        except FileExistsError:
            return {"tool": "mkdir", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Already exists", "data": {}, "message": "Already exists"}
        except OSError as exc:
            return {"tool": "mkdir", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        return {"tool": "mkdir", "ok": True, "exit_code": 0, "stdout": "OK", "stderr": "", "data": {"path": path}}

class ProcessListTool(BaseTool):
    name = "process_list"

    def max_calls_per_turn(self):
        return 5

    def argument_spec(self):
        return {"pattern": str}

    def describe(self):
        return tool_description(
            "process_list",
            "List running processes filtered by a required search pattern.",
            {
                "pattern": {
                    "type": "string",
                    "description": "Required non-empty substring filter for process rows (e.g. 'python').",
                }
            },
            ["pattern"],
        )

    def handle(self, pattern=None, **_):
        pattern = (pattern or "").strip()
        if not pattern:
            return {"tool": "process_list", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing pattern", "data": {}, "message": "Missing pattern"}
        termprint("subitem", f"Tool request (process_list), pattern: {pattern}")
        if not request_tool_approval("process_list", write_request=False):
            return {"tool": "process_list", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        try:
            completed = subprocess.run(["ps", "-eo", "pid,ppid,comm,args"], capture_output=True, text=True)
        except OSError as exc:
            return {"tool": "process_list", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        if completed.returncode != 0:
            return {"tool": "process_list", "ok": False, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "data": {"pattern": pattern}}
        lines = completed.stdout.splitlines()
        if not lines:
            return {"tool": "process_list", "ok": True, "exit_code": 0, "stdout": "", "stderr": "", "data": {"pattern": pattern, "count": 0}}
        header = lines[0]
        needle = pattern.lower()
        matched = [line for line in lines[1:] if needle in line.lower()]
        out_lines = [header, *matched] if matched else [header]
        return {"tool": "process_list", "ok": True, "exit_code": 0, "stdout": "\n".join(out_lines) + "\n", "stderr": "", "data": {"pattern": pattern, "count": len(matched)}}

class NetworkScanTool(BaseTool):
    name = "network_scan"

    def max_calls_per_turn(self):
        return 1

    def argument_spec(self):
        return {"target": str, "ports": list, "timeout_ms": int, "max_hosts": int}

    def describe(self):
        return tool_description(
            "network_scan",
            "Scan a host or local network for IPs and common services.",
            {
                "target": {
                    "type": "string",
                    "description": "Target IP, CIDR (e.g. 192.168.1.0/24), or 'self'/'localhost'. If omitted, scans local /24.",
                },
                "ports": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Ports to scan (default: common ports).",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Per-connection timeout in milliseconds (default 150).",
                },
                "max_hosts": {
                    "type": "integer",
                    "description": "Maximum number of hosts to scan (default 512).",
                },
            },
            [],
        )

    def _detect_local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            pass
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"

    def _local_ip_set(self):
        ips = {"127.0.0.1"}
        detected = self._detect_local_ip()
        if detected:
            ips.add(detected)
        try:
            _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
            ips.update(host_ips)
        except OSError:
            pass
        return ips

    def _parse_targets(self, target, max_hosts):
        if not target:
            local_ip = self._detect_local_ip()
            if local_ip.startswith("127."): return None, "Local IP resolves to loopback; provide a target."
            network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
            hosts = [str(ip) for ip in network.hosts()]
            if len(hosts) > max_hosts:
                return None, f"Too many hosts to scan ({len(hosts)}), set max_hosts or use a narrower target."
            return hosts, None

        target = target.strip().lower()
        if target in ("self", "local", "localip"): return [self._detect_local_ip()], None
        if target in ("localhost", "127.0.0.1"): return ["127.0.0.1"], None
        if "/" in target:
            try:
                network = ipaddress.ip_network(target, strict=False)
            except ValueError:
                return None, "Invalid CIDR target."
            hosts = [str(ip) for ip in network.hosts()]
            if len(hosts) > max_hosts: return None, f"Too many hosts to scan ({len(hosts)}), set max_hosts or use a narrower target."
            return hosts, None
        try:
            ipaddress.ip_address(target)
        except ValueError:
            return None, "Invalid IP target."
        return [target], None

    def _is_local_only(self, target, hosts):
        if not target and hosts: return False
        if target:
            target = target.strip().lower()
            if target in ("localhost", "127.0.0.1", "self", "local", "localip"): return True
        if len(hosts) != 1: return False
        return hosts[0] in self._local_ip_set()

    def _service_name(self, port):
        try:
            return socket.getservbyport(port)
        except OSError:
            return "unknown"

    def _scan_host(self, host, ports, timeout_sec):
        open_ports = []
        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(timeout_sec)
                    result = sock.connect_ex((host, port))
                if result == 0:
                    open_ports.append({"port": port, "service": self._service_name(port)})
            except OSError:
                continue
        return {"host": host, "open_ports": open_ports}

    def handle(self, target=None, ports=None, timeout_ms=None, max_hosts=None, **_):
        termprint("subitem", "Tool request (network_scan)")

        if ports is None: ports = [22, 23, 25, 53, 80, 110, 139, 143, 443, 445, 3389, 3306, 5432, 6379, 27017]
        if timeout_ms is None: timeout_ms = 150
        if max_hosts is None: max_hosts = 512

        if not isinstance(ports, list) or not all(isinstance(p, int) for p in ports):
            return {"tool": "network_scan", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Invalid ports list", "data": {}, "message": "Invalid ports list"}
        if not isinstance(timeout_ms, int) or timeout_ms < 1:
            return {"tool": "network_scan", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Invalid timeout_ms", "data": {}, "message": "Invalid timeout_ms"}
        if not isinstance(max_hosts, int) or max_hosts < 1:
            return {"tool": "network_scan", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Invalid max_hosts", "data": {}, "message": "Invalid max_hosts"}

        hosts, error = self._parse_targets(target, max_hosts)
        if error:
            return {"tool": "network_scan", "ok": False, "exit_code": 1, "stdout": "", "stderr": error, "data": {}, "message": error}

        if not self._is_local_only(target, hosts):
            if not request_tool_approval("network_scan (non-local)", write_request=True):
                return {"tool": "network_scan", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}

        timeout_sec = timeout_ms / 1000.0
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(64, len(hosts) or 1)) as executor:
            futures = [executor.submit(self._scan_host, host, ports, timeout_sec) for host in hosts]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda item: item["host"])
        lines = []
        for item in results:
            host = item["host"]
            ports_info = item["open_ports"]
            if not ports_info:
                lines.append(f"{host}: no open ports detected")
                continue
            port_text = ", ".join(f"{p['port']}/{p['service']}" for p in ports_info)
            lines.append(f"{host}: {port_text}")
        output = "\n".join(lines) + ("\n" if lines else "")

        return {"tool": "network_scan", "ok": True, "exit_code": 0, "stdout": output, "stderr": "", "data": {"targets": hosts, "ports": ports, "results": results}}

class ToolListTool(BaseTool):
    name = "tool_list"

    def max_calls_per_turn(self):
        return 1

    def describe(self):
        return tool_description("tool_list", "List all available tools and their descriptions.", {}, [])

    def handle(self, **_):
        termprint("subitem", "Tool request (tool_list)")
        if not request_tool_approval("tool_list", write_request=False):
            return {"tool": "tool_list", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        lines = []
        for tool in TOOL_INSTANCES:
            info = tool.describe().get("function", {})
            name = info.get("name") or tool.name
            desc = info.get("description") or ""
            lines.append(f"{name}: {desc}".strip())
        output = "\n".join(lines) + ("\n" if lines else "")
        return {"tool": "tool_list", "ok": True, "exit_code": 0, "stdout": output, "stderr": "", "data": {"count": len(lines)}}

class FindTool(BaseTool):
    name = "find"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"path": str, "name": str, "type": str, "max_depth": int}

    def describe(self):
        return tool_description(
            "find",
            "Find files or directories starting at a path, optionally filtering by name, type, or depth.",
            {
                "path": {"type": "string", "description": "Root path to search."},
                "name": {"type": "string", "description": "Optional glob pattern to match (e.g. '*.conf')."},
                "type": {"type": "string", "description": "Optional entry type filter: 'f' for files or 'd' for directories."},
                "max_depth": {"type": "integer", "description": "Optional maximum depth relative to path."},
            },
            ["path"],
        )

    def handle(self, path=None, name=None, type=None, max_depth=None, **_):
        if not path:
            return {"tool": "find", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing path", "data": {}, "message": "Missing path"}
        termprint("subitem", f"Tool request (find), path: {path}")
        if not request_tool_approval(f"find: {path}", write_request=False):
            return {"tool": "find", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        if type is not None and type not in ("f", "d"):
            return {"tool": "find", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Invalid type (use 'f' or 'd')", "data": {}, "message": "Invalid type"}
        if max_depth is not None and (not isinstance(max_depth, int) or max_depth < 0):
            return {"tool": "find", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Invalid max_depth", "data": {}, "message": "Invalid max_depth"}
        if not os.path.exists(path):
            return {"tool": "find", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Path not found", "data": {}, "message": "Path not found"}

        results = []
        base_depth = path.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(path):
            depth = root.count(os.sep) - base_depth
            if max_depth is not None and depth > max_depth:
                dirs[:] = []
                continue
            entries = []
            if type in (None, "d"):
                entries.extend([(d, True) for d in dirs])
            if type in (None, "f"):
                entries.extend([(f, False) for f in files])
            for entry, is_dir in entries:
                if name and not fnmatch.fnmatch(entry, name):
                    continue
                full_path = os.path.join(root, entry)
                results.append(full_path)
        results.sort()
        output = "\n".join(results) + ("\n" if results else "")
        return {"tool": "find", "ok": True, "exit_code": 0, "stdout": output, "stderr": "", "data": {"count": len(results)}}

class HTMLToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = []
        self.in_pre = False
        self.link_href = None
        self.link_text = []

    def _ensure_blankline(self):
        if not self.out: return
        text = "".join(self.out)
        if not text.endswith("\n\n"):
            if text.endswith("\n"):
                self.out.append("\n")
            else:
                self.out.append("\n\n")

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._ensure_blankline()
        elif tag == "br":
            self.out.append("\n")
        elif tag in ["strong", "b"]:
            self.out.append("**")
        elif tag in ["em", "i"]:
            self.out.append("*")
        elif tag == "code":
            if not self.in_pre: self.out.append("`")
        elif tag == "pre":
            self._ensure_blankline()
            self.out.append("```\n")
            self.in_pre = True
        elif tag == "a":
            self.link_href = None
            self.link_text = []
            for key, value in attrs:
                if key == "href": self.link_href = value

    def handle_endtag(self, tag):
        if tag in ["strong", "b"]:
            self.out.append("**")
        elif tag in ["em", "i"]:
            self.out.append("*")
        elif tag == "code":
            if not self.in_pre: self.out.append("`")
        elif tag == "pre":
            if not "".join(self.out).endswith("\n"): self.out.append("\n")
            self.out.append("```\n")
            self.in_pre = False
        elif tag == "a":
            text = "".join(self.link_text).strip()
            href = self.link_href or ""
            if text: self.out.append(f"[{text}]({href})")
            self.link_href = None
            self.link_text = []

    def handle_data(self, data):
        if not data: return
        if self.in_pre:
            self.out.append(data)
            return
        if self.link_href is not None:
            self.link_text.append(data)
        else:
            self.out.append(re.sub(r"\s+", " ", data))

    def get_markdown(self):
        return "".join(self.out).strip() + "\n"

def _parse_charset(content_type):
    if not content_type: return None
    match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
    if match: return match.group(1).strip()
    return None

def _is_text_mime(content_type):
    if not content_type: return False
    mime = content_type.split(";", 1)[0].strip().lower()
    return mime.startswith("text/")

class InternetReadTool(BaseTool):
    name = "internet_read"

    def max_calls_per_turn(self):
        return 10

    def argument_spec(self):
        return {"url": str}

    def describe(self):
        return tool_description(
            "internet_read",
            "Read a text resource from a URL; HTML is converted to Markdown.",
            {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (text/* only).",
                }
            },
            ["url"],
        )

    def handle(self, url=None, **_):
        if not url: return {"tool": "internet_read", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Missing url", "data": {}, "message": "Missing url"}
        termprint("subitem", f"Tool request (internet_read), url: {url}")
        if not request_tool_approval(url, write_request=False):
            return {"tool": "internet_read", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected by user", "data": {}, "message": "Rejected by user"}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "opx/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if not _is_text_mime(content_type):
                    return {"tool": "internet_read", "ok": False, "exit_code": 1, "stdout": "", "stderr": "Rejected: non-text mime type", "data": {}, "message": "Rejected: non-text mime type"}
                raw = resp.read()
        except urllib.error.URLError as exc:
            return {"tool": "internet_read", "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc), "data": {}, "message": str(exc)}
        charset = _parse_charset(content_type) or "utf-8"
        text = raw.decode(charset, errors="replace")
        if content_type.lower().startswith("text/html"):
            parser = HTMLToMarkdown()
            parser.feed(text)
            text = parser.get_markdown()
        return {"tool": "internet_read", "ok": True, "exit_code": 0, "stdout": text, "stderr": "", "data": {"url": url, "content": text, "bytes": len(text.encode("utf-8"))}}

def _tool_instances():
    return [
        ToolListTool(),
        BashTool(),
        GitTool(),
        FindTool(),
        GrepTool(),
        EditPreviewTool(),
        EditTool(),
        WriteTool(),
        ReadTool(),
        ListTool(),
        TreeTool(),
        ManTool(),
        MkdirTool(),
        ProcessListTool(),
        NetworkScanTool(),
        InternetReadTool(),
    ]

TOOL_INSTANCES = _tool_instances()
TOOL_REGISTRY = {tool.name: tool for tool in TOOL_INSTANCES}

DEFAULT_STREAM_PREFIX = ">>> "

class _LinePrefixWriter:
    def __init__(self, writer, prefix=DEFAULT_STREAM_PREFIX, max_line_length=132):
        self.writer = writer
        self.prefix = prefix
        self.at_line_start = True
        self.line_length = 0
        self.max_line_length = max_line_length

    def write(self, content):
        if not content or self.writer is None:
            return
        pending_word = ""

        def flush_word():
            nonlocal pending_word
            if not pending_word:
                return
            word_len = len(pending_word)
            if self.at_line_start:
                self.writer.write(self.prefix)
                self.at_line_start = False
            if self.line_length > 0 and self.line_length + word_len > self.max_line_length:
                self.writer.write("\n")
                self.writer.write(self.prefix)
                self.line_length = 0
            self.writer.write(pending_word)
            self.line_length += word_len
            pending_word = ""

        for ch in content:
            if ch == "\n":
                flush_word()
                self.writer.write(ch)
                self.at_line_start = True
                self.line_length = 0
                continue
            if ch == " ":
                flush_word()
                if self.line_length > 0 and self.line_length + 1 > self.max_line_length:
                    self.writer.write("\n")
                    self.at_line_start = True
                    self.line_length = 0
                if not self.at_line_start:
                    self.writer.write(" ")
                    self.line_length += 1
                continue
            pending_word += ch

        flush_word()

    def flush(self):
        if self.writer:
            self.writer.flush()

def _emit_content(content, writer):
    if not content: return
    if writer is None: return
    writer.write(content)
    writer.flush()

def process_response(resp, writer, tool_registry=None, content_collector=None):
    tool_calls_data = {}
    tool_call_order = []
    if tool_registry is None:
        tool_registry = TOOL_REGISTRY

    def _add_or_update_tool_call(call):
        key = call.get("id")
        if key is None and call.get("index") is not None:
            key = f"index_{call.get('index')}"
        if key is None:
            key = f"call_{len(tool_call_order) + 1}"
        if key not in tool_calls_data:
            tool_calls_data[key] = {"id": call.get("id"), "name": None, "arguments": ""}
            tool_call_order.append(key)
        func = call.get("function") or {}
        name = func.get("name")
        arguments = func.get("arguments")
        if name:
            tool_calls_data[key]["name"] = name
        if arguments:
            tool_calls_data[key]["arguments"] += arguments

    def _build_tool_request(tool_call):
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("arguments") or ""
        tool_id = tool_call.get("id")
        if tool_args and tool_name is None:
            # If exactly one tool is visible, map unnamed calls to it.
            # This avoids forcing an implicit "bash" when tools are filtered.
            if len(tool_registry) == 1:
                tool_name = next(iter(tool_registry.keys()))
            else:
                tool_name = "bash"
        tool = tool_registry.get(tool_name)
        if tool and tool_args:
            parsed_args = tool.parse_arguments(tool_args)
            if parsed_args is not None:
                tool_request = {"id": tool_id, "name": tool_name, "arguments": tool_args}
                tool_request.update(parsed_args)
                return tool_request
        return None

    try:
        while True:
            line = resp.readline()
            if not line: break
            if not line.startswith(b"data:"): continue
            data = line[5:].strip()
            if data == b"[DONE]": break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = payload.get("choices") or []
            if not choices: continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            tool_calls = delta.get("tool_calls") or []
            if content_collector is not None and content: content_collector.append(content)
            if not tool_calls:
                _emit_content(content, writer)
            for call in tool_calls:
                _add_or_update_tool_call(call)
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        termprint("error", f"Stream read failed: {exc}")

    if writer: writer.flush()
    tool_requests = []
    for key in tool_call_order:
        tool_request = _build_tool_request(tool_calls_data.get(key, {}))
        if tool_request: tool_requests.append(tool_request)
    return tool_requests

def _format_title(base, elapsed):
    if elapsed is None: return base
    return f"{base} ({elapsed:.2f}s)"

def _truncate_to_width(text, max_width):
    if max_width <= 0:
        return "", 0
    out = []
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            out.append(ch)
            continue
        ch_width = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + ch_width > max_width:
            break
        out.append(ch)
        width += ch_width
    return "".join(out), width

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

def _clean_box_line(line):
    line = _ANSI_CSI_RE.sub("", line)
    out = []
    for ch in line:
        if ch == "\b":
            if out:
                out.pop()
            continue
        if ch == "\r" or ch == "\x00":
            continue
        out.append(ch)
    return "".join(out)

def termprint(style: str, content: str, title=None, elapsed=None, writer=sys.stdout, width=132):
    header = _format_title(title, elapsed) if title else ""
    text = content or ""
    if header:
        text = f"{header}\n{text}" if text else header
    if style == "paragraph":
        writer.write(text)
        if text and not text.endswith("\n"): writer.write("\n")
        writer.flush()
        return
    if style == "item":
        wrap_width = max(1, width - 2)
        filled = textwrap.fill( text, width=wrap_width, initial_indent="* ", subsequent_indent="  ")
        writer.write(filled + "\n")
        writer.flush()
        return
    if style == "subitem":
        wrap_width = max(1, width - 4)
        filled = textwrap.fill( text, width=wrap_width, initial_indent="  └ ", subsequent_indent="    ")
        writer.write(filled + "\n")
        writer.flush()
        return
    if style == "error":
        wrap_width = max(1, width - 6)
        filled = textwrap.fill( text, width=wrap_width, initial_indent="ERROR ", subsequent_indent="      ")
        writer.write(filled + "\n")
        writer.flush()
        return
    if style == "box":
        lines = text.splitlines() if text else [""]
        top = "╭" + ("─" * width) + "╮"
        bottom = "╰" + ("─" * width) + "╯"
        writer.write(top + "\n")
        for line in lines:
            line = _clean_box_line(line).expandtabs(4)
            clipped, clipped_width = _truncate_to_width(line, width)
            padding = max(0, width - clipped_width)
            writer.write("│" + clipped + (" " * padding) + "│\n")
        writer.write(bottom + "\n")
        writer.flush()
        return
    writer.write(text)
    if text and not text.endswith("\n"):
        writer.write("\n")
    writer.flush()

def _format_tool_request(tool_request):
    name = tool_request.get("name") or "bash"
    if name == "bash":
        cmd = tool_request.get("command") or ""
        return f"bash: {cmd}".strip()
    args = []
    for key, value in tool_request.items():
        if key in ("id", "name", "arguments"): continue
        args.append(f"{key}={value}")
    args_text = " ".join(args).strip()
    return f"{name}: {args_text}".strip()

def _format_tool_result(tool_result):
    stdout = (tool_result.get("stdout") or "").rstrip("\n")
    stderr = (tool_result.get("stderr") or "").rstrip("\n")
    lines = []
    if stdout: lines.extend(stdout.splitlines())
    if stderr:
        if lines: lines.append("")
        lines.append("stderr:")
        lines.extend(stderr.splitlines())
    if not lines:
        message = (tool_result.get("message") or "").strip()
        lines.append(message if message else "OK")
    return "\n".join(lines)

def _resolve_visible_tools():
    only_tools_raw = (os.environ.get("OPX_ONLY_TOOLS") or "").strip()
    if not only_tools_raw:
        return TOOL_INSTANCES
    wanted = [name.strip() for name in only_tools_raw.split(",") if name.strip()]
    visible = []
    unknown = []
    for name in wanted:
        tool = TOOL_REGISTRY.get(name)
        if tool is None:
            unknown.append(name)
        else:
            visible.append(tool)
    if unknown:
        termprint("error", f"Unknown tool(s) in OPX_ONLY_TOOLS: {', '.join(unknown)}")
        sys.exit(2)
    if not visible:
        termprint("error", "OPX_ONLY_TOOLS resolved to an empty tool set.")
        sys.exit(2)
    return visible

def _apply_tool_call_budgets(tool_requests, call_register):
    # Per-turn register of tool usage counts (mutated in-place).
    allowed = []
    dropped = {}
    for tool_request in tool_requests:
        tool_name = tool_request.get("name") or "bash"
        tool = TOOL_REGISTRY.get(tool_name, TOOL_REGISTRY["bash"])
        normalized_name = tool.name
        limit = tool.max_calls_per_turn()
        current = call_register.get(normalized_name, 0)
        if current >= limit:
            dropped[normalized_name] = dropped.get(normalized_name, 0) + 1
            continue
        call_register[normalized_name] = current + 1
        allowed.append({"tool_request": tool_request, "tool": tool})
    return allowed, dropped

def main():
    prompt = " ".join(sys.argv[1:])
    extra = sys.stdin.read() if not sys.stdin.isatty() else ""
    if extra:
        prompt = f"{prompt}\n\n```\n{extra}\n```" if prompt else extra
    if not prompt:
        termprint("error", "Prompt is required.")
        sys.exit(1)
    
    termprint("paragraph", "  ___   ___  __  __")
    termprint("paragraph", " / _ \\ | _ \\ \\ \\/ /")
    termprint("paragraph", "| (_) ||  _/  >  < ")
    termprint("paragraph", " \\___/ |_|   /_/\\_\\")
    termprint("paragraph", "")

    termprint("paragraph", f"Using model: {OPENAI_MODEL} at {OPENAI_BASE_URL}")
    termprint("paragraph", "")
    initial_prompt = prompt

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    visible_tools = _resolve_visible_tools()
    visible_tool_names = {tool.name for tool in visible_tools}
    visible_tool_registry = {tool.name: tool for tool in visible_tools}
    turn_call_register = {}
    synthetic_call_seq = 0
    turn_count = 0

    while True:
        turn_count += 1
        if turn_count > DEFAULT_MAX_TURNS:
            termprint("error", f"Reached max turns ({DEFAULT_MAX_TURNS}); aborting run.")
            break
        tools = [
            tool.describe()
            for tool in visible_tools
            if turn_call_register.get(tool.name, 0) < tool.max_calls_per_turn()
        ]
        body = json.dumps({
            "model": OPENAI_MODEL,
            "temperature": OPENAI_TEMPERATURE,
            "reasoning_effort": OPENAI_REASONING_EFFORT,
            "messages": messages,
            "tools": tools,
            "stream": True,
        })
        start_time = time.monotonic()
        
        termprint("paragraph", "\n")
        termprint("item", "Calling LLM to get tool instructions...")
        resp, _ = _http_request("POST", "/v1/chat/completions", body=body, read_body=False, leave_open=True)
        if resp is None:
            termprint("error", f"Failed to connect to {OPENAI_BASE_URL}")
            sys.exit(1)

        content_chunks = [] # we collect the content to use them in the fullfillment test
        stream_writer = _LinePrefixWriter(sys.stdout)
        tool_requests = process_response(resp, stream_writer, tool_registry=visible_tool_registry, content_collector=content_chunks)
        resp.close()

        if tool_requests:
            filtered_requests = []
            hidden_dropped = 0
            coerced_hidden = 0
            sole_visible_tool = next(iter(visible_tool_names)) if len(visible_tool_names) == 1 else None
            for req in tool_requests:
                req_name = req.get("name") or "bash"
                normalized = TOOL_REGISTRY.get(req_name, TOOL_REGISTRY["bash"]).name
                if normalized not in visible_tool_names:
                    if sole_visible_tool is not None:
                        coerced = dict(req)
                        coerced["name"] = sole_visible_tool
                        filtered_requests.append(coerced)
                        coerced_hidden += 1
                        continue
                    hidden_dropped += 1
                    continue
                filtered_requests.append(req)
            if coerced_hidden:
                termprint("subitem", f"Coerced {coerced_hidden} hidden call(s) to visible tool: {sole_visible_tool}")
            if hidden_dropped:
                termprint("subitem", f"Dropped {hidden_dropped} call(s) to hidden tools.")
            if not filtered_requests:
                termprint("subitem", "Only hidden tools were requested; retrying with current tool visibility.")
                continue

            allowed_calls, dropped = _apply_tool_call_budgets(filtered_requests, turn_call_register)
            if dropped:
                for tool_name, count in sorted(dropped.items()):
                    termprint("subitem", f"Dropped {count} over-budget call(s) for tool: {tool_name}")

            if not allowed_calls:
                termprint("subitem", "All requested tools are over budget for this turn; retrying with reduced tool visibility.")
                continue

            tool_calls = []
            for plan in allowed_calls:
                tool_request = plan["tool_request"]
                tool_name = tool_request.get("name")
                call_id = tool_request.get("id")
                if not call_id:
                    synthetic_call_seq += 1
                    call_id = f"opx_call_{synthetic_call_seq}"
                plan["resolved_call_id"] = call_id
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tool_request.get("arguments", "")},
                    }
                )
            messages.append({"role": "assistant", "tool_calls": tool_calls})
            for tool_name, count in sorted(turn_call_register.items()):
                tool_limit = TOOL_REGISTRY.get(tool_name, TOOL_REGISTRY["bash"]).max_calls_per_turn()
                termprint("subitem", f"Tool budget usage this turn: {tool_name} {count}/{tool_limit}")
            for plan in allowed_calls:
                tool_request = plan["tool_request"]
                tool = plan["tool"]
                tool_name = tool.name
                termprint("subitem", _format_tool_request(tool_request), title=f"Tool call: {tool_name}")
                tool_start = time.monotonic()
                try:
                    tool_result = tool.handle_request(tool_request)
                except Exception as exc:
                    tool_result = {
                        "tool": tool_name,
                        "ok": False,
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": f"Tool execution failed: {exc}",
                        "data": {"exception_type": exc.__class__.__name__},
                            "message": "Tool execution failed",
                        }
                tool_elapsed = time.monotonic() - tool_start
                elapsed_override = None
                if isinstance(tool_result, dict):
                    data = tool_result.get("data")
                    if isinstance(data, dict):
                        elapsed_override = data.get("elapsed_exec_sec")
                termprint("box", _format_tool_result(tool_result), title="Tool result", elapsed=elapsed_override if isinstance(elapsed_override, (int, float)) else tool_elapsed)
                tool_msg = {"role": "tool", "content": json.dumps(tool_result)}
                tool_msg["tool_call_id"] = plan["resolved_call_id"]
                messages.append(tool_msg)
            continue
        assistant_elapsed = time.monotonic() - start_time
        assistant_content = "".join(content_chunks).strip()
        if assistant_content and not assistant_content.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
        messages.append({"role": "assistant", "content": assistant_content})
        turn_call_register = {}
        
        # test if task is fullfilled
        termprint("paragraph", "\n")
        termprint("item", "Testing the results so far if they fulfill the initial request...")
        conversation = _format_conversation(messages)
        judge_prompt = (
            "You are a strict judge. Return true only if the initial request is fully fulfilled "
            "by the conversation and the latest assistant response. Otherwise return false."
        )
        is_fulfilled, confidence = truth_test(
            judge_prompt,
            f"Conversation:\n{conversation}\n\nQuestion: was the initial request fulfilled?",
            compute_confidence=True)
        
        if (is_fulfilled):
            termprint("subitem", f"The initial request was fullfilled, confidence: {confidence * 100.0}%")
            break

        termprint("subitem", f"The initial request was not fullfilled; we compute a follow-up prompt to continue, confidence: {confidence * 100.0}%")
        follow_up_prompt = _build_follow_up_prompt(conversation, initial_prompt)
        
        if not follow_up_prompt:
            termprint("error", "no follow-up prompt computed; thats an error")
            break
        
        termprint("subitem", f"follow-up prompt: {follow_up_prompt}%")
        messages.append({"role": "user", "content": follow_up_prompt})
        continue

if __name__ == "__main__":
    main()
