#!/usr/bin/env python3
# Small coding agent for interactive or piped prompts.
#
# Workshop test prompts:
# - "Hello! What can you do?"                         # no tool needed
# - "List this directory and summarize README.md."    # list + read
# - "Read README.md and configure.sh in one turn."    # multiple calls
# - "Read missing.txt; recover by inspecting the directory."  # tool error
# - "List the skills, load the debugging skill, and explain its workflow."
# - "Use a relevant skill to review opx.py without changing it."
# - "How does OPX decide whether a Bash command needs approval?"  # help skill
# - printf 'Summarize README.md.\n' | ./opx.py       # one piped prompt
# - printf 'Create report.md.\n' | ./opx.py --yolo  # no guardrails
#
# Run these file-changing examples in an expendable directory:
# - "Create hello.py with a program that prints Hello."
# - "Replace Hello in hello.py with Hello, workshop!"  # asks first
# - "Run python3 hello.py and correct the program if it fails."  # Bash policy
# - "Add a skill that explains small Python scripts."   # extends skills

import os
import sys
import json
import fnmatch
import itertools
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = os.environ["OPENAI_BASE_URL"].rstrip("/")
API_KEY = os.environ["OPENAI_API_KEY"]
MODEL = os.environ["OPENAI_MODEL"]
TEMPERATURE = float(os.environ["OPENAI_TEMPERATURE"])
REASONING_EFFORT = os.environ["OPENAI_REASONING_EFFORT"]
MAX_TURNS = int(os.environ.get("OPX_MAX_TURNS", "24"))
CALL_IDS = itertools.count(1)
SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
YOLO = False

SYSTEM_PROMPT = """
You are a small coding agent working in the current directory.
Prefer the dedicated file tools and use Bash only when necessary.
Keep projects in one source file unless the user requests otherwise.
Prefer replace_in_file over rewriting a complete existing file.
Discover and read a relevant skill when its procedure would help the task.
Load only skills that are actually needed.
For questions about OPX itself, load the OPX Help skill before answering.
For requests to change the skill collection, load the Extend Skills skill.
You may request several independent tool calls in one response.
When a tool fails, read error.retry_hint and correct the next call.
Do not repeat an unchanged tool call after an error.
Answer conversational messages directly without using tools.
When the task is complete, return a short final answer.
""".strip()

# Patterns are checked in this order. The last matching rule wins.
BASH_PERMISSIONS = {
    "*": "ask",
    "python*": "ask", "node*": "ask", "ruby*": "ask",
    "pytest*": "ask", "make*": "ask", "npm*": "ask",
    "cargo*": "ask", "sed*": "ask", "awk*": "ask",
    "diff*": "ask", "git grep*": "ask",
    "curl*": "ask", "wget*": "ask",
    "rm*": "ask", "mv*": "ask", "cp*": "ask",
    "install*": "ask",
    "ls": "allow", "ls *": "allow", "pwd": "allow",
    "pwd *": "allow", "cat *": "allow",
    "head *": "allow", "chmod *": "ask", "tail *": "allow",
    "wc *": "allow", "stat *": "allow", "file *": "allow",
    "mkdir *": "ask", "find *": "ask", "grep *": "allow",
    "rg *": "allow", "which *": "allow", "touch *": "ask",
    "whereis *": "allow", "env *": "ask", "printenv *": "allow",
    "ps *": "allow", "top *": "allow", "du *": "allow",
    "df *": "allow", "tree *": "allow", "whoami": "allow",
    "id": "allow", "uname -a": "allow", "basename *": "allow",
    "dirname *": "allow", "realpath *": "allow",
    "readlink *": "allow", "cksum *": "allow",
    "shasum *": "allow", "bash -n *": "allow",
    "git status": "allow", "git status *": "allow",
    "git diff *": "ask", "git log *": "allow",
    "git show*": "ask", "git rev-parse *": "allow",
    "git ls-files": "allow", "git ls-files *": "allow",
    "git branch --show-current": "allow",
    "git diff --check": "allow", "git diff --stat": "allow",
    "git diff --name-only": "allow",
    "git diff --cached --check": "allow",
    "git diff --cached --stat": "allow",
    "git diff --cached --name-only": "allow",
}

def tool(name, description, properties, required):
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

PATH = {
    "type": "string",
    "description": "Relative or absolute filesystem path.",
}

TOOLS = [
    tool(
        "bash",
        "Run one guarded Bash command under the inline policy.",
        {
            "command": {
                "type": "string",
                "description": "One command without shell composition.",
            }
        },
        ["command"],
    ),
    tool(
        "list_files",
        "List a directory and return absolute paths.",
        {"path": PATH},
        [],
    ),
    tool(
        "read_file",
        "Read a file from a relative or absolute path.",
        {"path": PATH},
        ["path"],
    ),
    tool(
        "write_file",
        "Create a file directly or overwrite it after approval.",
        {
            "path": PATH,
            "content": {
                "type": "string",
                "description": "Complete new file content.",
            },
        },
        ["path", "content"],
    ),
    tool(
        "replace_in_file",
        "Replace one unique text occurrence after approval.",
        {
            "path": PATH,
            "old": {
                "type": "string",
                "description": "Existing text that must occur exactly once.",
            },
            "new": {
                "type": "string",
                "description": "Replacement text.",
            },
        },
        ["path", "old", "new"],
    ),
    tool(
        "list_skills",
        "List available skills and their purposes.",
        {},
        [],
    ),
    tool(
        "read_skill",
        "Read a SKILL.md selected from list_skills.",
        {
            "skill": {
                "type": "string",
                "description": "Skill path returned by list_skills.",
            }
        },
        ["skill"],
    ),
]

def enable_yolo():
    global YOLO
    YOLO = True
    descriptions = {
        "bash": "Run one unguarded Bash command in YOLO mode.",
        "write_file": "Create or overwrite a file without approval.",
        "replace_in_file": "Replace one unique text occurrence without approval.",
    }
    for item in TOOLS:
        function = item["function"]
        if function["name"] in descriptions:
            function["description"] = descriptions[function["name"]]


def terminal_input(prompt=""):
    """Read from the terminal, never from redirected stdin."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    with open("/dev/tty", encoding="utf-8") as terminal:
        line = terminal.readline()
    if not line:
        raise EOFError
    return line.rstrip("\n")

def approve(question):
    if YOLO:
        print(f"YOLO: auto-approved: {question}", file=sys.stderr)
        return True
    answer = terminal_input(f"{question} [y/N] ").strip().lower()
    return answer in {"y", "yes"}

def chat(messages):
    body = json.dumps({
        "model": MODEL,
        "temperature": TEMPERATURE,
        "reasoning_effort": REASONING_EFFORT,
        "stream": False,
        "messages": messages,
        "tools": TOOLS,
    }).encode()
    request = Request(
        f"{BASE_URL}/v1/chat/completions",
        body,
        {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=600) as response:
            data = json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error
    return data["choices"][0]["message"]

def result(ok, output="", exit_code=0, **data):
    value = {"ok": ok, "exit_code": exit_code, "output": output}
    value.update(data)
    return value

def tool_error(code, message, retry_hint, exit_code=1, output=None, **data):
    error = {
        "code": code,
        "message": message,
        "retry_hint": retry_hint,
    }
    return result(
        False,
        message if output is None else output,
        exit_code,
        error=error,
        **data,
    )

def permission_for(command):
    permission = "ask"
    for pattern, action in BASH_PERMISSIONS.items():
        if fnmatch.fnmatchcase(command, pattern):
            permission = action
    return permission

def run_bash(command):
    forbidden = ("|", ";", "&", ">", "<", "$(", "`", "\n", "\r")
    if YOLO:
        print("Policy: yolo (unguarded)", file=sys.stderr)
    else:
        if not command:
            print("Policy: deny (syntax guard)", file=sys.stderr)
            return tool_error(
                "empty_command",
                "The Bash command is empty.",
                "Call bash again with one non-empty command.",
            )
        if any(token in command for token in forbidden):
            print("Policy: deny (syntax guard)", file=sys.stderr)
            return tool_error(
                "shell_composition_rejected",
                "The command contains forbidden shell composition syntax.",
                "Use one simple command without pipes, redirection, command "
                "substitution, separators or newlines.",
                command=command,
            )

        permission = permission_for(command)
        print(f"Policy: {permission}", file=sys.stderr)
        if permission == "deny":
            return tool_error(
                "policy_denied",
                "The Bash command is denied by the inline policy.",
                "Do not repeat it unchanged. Use a dedicated tool or a "
                "permitted command instead.",
                command=command,
            )
        if permission == "ask" and not approve(f"Run '{command}'?"):
            return tool_error(
                "user_rejected",
                "The user declined this Bash command.",
                "Do not request the same operation again. Choose a safe "
                "alternative or explain that user approval is required.",
                command=command,
            )
        if permission not in {"allow", "ask"}:
            return tool_error(
                "invalid_policy",
                f"The policy returned the unsupported action '{permission}'.",
                "Do not retry; report the policy configuration error.",
                command=command,
            )

    try:
        completed = subprocess.run(
            ["/bin/bash", "-lc", command],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return tool_error(
            "command_timeout",
            "The Bash command exceeded the 30 second timeout.",
            "Use a faster or more narrowly scoped command.",
            command=command,
        )
    except OSError as error:
        return tool_error(
            "command_start_failed",
            f"The Bash command could not be started: {error}",
            "Correct the command or use a dedicated tool instead.",
            command=command,
        )

    output = completed.stdout + completed.stderr
    if completed.returncode:
        return tool_error(
            "command_failed",
            f"The command exited with status {completed.returncode}.",
            "Inspect the command output, correct the command and retry only "
            "with changed arguments.",
            exit_code=completed.returncode,
            output=output or None,
            command=command,
        )
    return result(True, output)

def full_path(path):
    return os.path.abspath(os.path.expanduser(path))

def list_files(path="."):
    path = full_path(path)
    try:
        entries = sorted(os.scandir(path), key=lambda entry: entry.name)
    except OSError as error:
        return tool_error(
            "directory_unavailable",
            f"Cannot list '{path}': {error}",
            "Correct the directory path and call list_files again.",
            path=path,
        )
    paths = [os.path.abspath(entry.path) for entry in entries]
    return result(True, "\n".join(paths), path=path, paths=paths)

def read_file(path):
    path = full_path(path)
    try:
        with open(path, encoding="utf-8") as file:
            return result(True, file.read(), path=path)
    except OSError as error:
        return tool_error(
            "file_unavailable",
            f"Cannot read '{path}': {error}",
            "Correct the file path or inspect its parent directory first.",
            path=path,
        )


def write_file(path, content):
    path = full_path(path)
    exists = os.path.lexists(path)
    if exists and not approve(f"Overwrite '{path}'?"):
        return tool_error(
            "user_rejected",
            f"The user declined overwriting '{path}'.",
            "Do not request the same overwrite again. Preserve the existing "
            "file or choose a different path.",
            path=path,
        )

    try:
        with open(path, "w" if exists else "x", encoding="utf-8") as file:
            file.write(content)
    except FileExistsError:
        if not approve(f"Overwrite '{path}'?"):
            return tool_error(
                "user_rejected",
                f"The user declined overwriting '{path}'.",
                "Do not request the same overwrite again. Preserve the "
                "existing file or choose a different path.",
                path=path,
            )
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(content)
        except OSError as error:
            return tool_error(
                "write_failed",
                f"Cannot write '{path}': {error}",
                "Correct the path or permissions, then retry.",
                path=path,
            )
    except OSError as error:
        return tool_error(
            "write_failed",
            f"Cannot write '{path}': {error}",
            "Correct the path or permissions, then retry.",
            path=path,
        )
    return result(True, f"Wrote {path}.", path=path)


def replace_in_file(path, old, new):
    path = full_path(path)
    if not old:
        return tool_error(
            "empty_old_text",
            "The old text must not be empty.",
            "Read the file and retry with the exact non-empty text to replace.",
            path=path,
        )
    try:
        with open(path, encoding="utf-8", newline="") as file:
            content = file.read()
    except OSError as error:
        return tool_error(
            "file_unavailable",
            f"Cannot read '{path}' before replacing text: {error}",
            "Correct the file path or inspect its parent directory first.",
            path=path,
        )

    matches = content.count(old)
    if matches != 1:
        message = f"Old text occurs {matches} times; expected exactly once."
        hint = (
            "Read the current file and retry with text that occurs exactly once."
            if matches == 0 else
            "Retry with a larger, unique old text fragment."
        )
        return tool_error(
            "old_text_not_unique",
            message,
            hint,
            path=path,
            matches=matches,
        )
    if not approve(f"Replace text in '{path}'?"):
        return tool_error(
            "user_rejected",
            f"The user declined modifying '{path}'.",
            "Do not request the same replacement again. Preserve the file or "
            "explain that approval is required.",
            path=path,
        )

    try:
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(content.replace(old, new, 1))
    except OSError as error:
        return tool_error(
            "write_failed",
            f"Cannot update '{path}': {error}",
            "Correct the path or permissions, then read the file before retrying.",
            path=path,
        )
    return result(True, f"Updated {path}.", path=path, matches=1)


def skill_catalog():
    manifest = os.path.join(SKILLS_DIR, "skills.json")
    with open(manifest, encoding="utf-8") as file:
        return json.load(file)


def list_skills():
    try:
        skills = skill_catalog()
    except (OSError, json.JSONDecodeError) as error:
        return tool_error(
            "skill_catalog_unavailable",
            f"Cannot read the skill catalog: {error}",
            "Do not retry unchanged; report that the skill catalog needs repair.",
            path=SKILLS_DIR,
        )
    try:
        lines = [f"{item['path']}: {item['purpose']}" for item in skills]
    except (TypeError, KeyError) as error:
        return tool_error(
            "invalid_skill_catalog",
            f"The skill catalog has an invalid entry: {error}",
            "Do not retry unchanged; report that skills.json needs repair.",
            path=SKILLS_DIR,
        )
    return result(True, "\n".join(lines), path=SKILLS_DIR)


def read_skill(skill):
    try:
        skills = skill_catalog()
    except (OSError, json.JSONDecodeError) as error:
        return tool_error(
            "skill_catalog_unavailable",
            f"Cannot read the skill catalog: {error}",
            "Do not retry unchanged; report that the skill catalog needs repair.",
            skill=skill,
        )
    try:
        entry = next(
            item for item in skills
            if item.get("path") == skill
        )
    except (TypeError, AttributeError) as error:
        return tool_error(
            "invalid_skill_catalog",
            f"The skill catalog has an invalid entry: {error}",
            "Do not retry unchanged; report that skills.json needs repair.",
            skill=skill,
        )
    except StopIteration:
        available = [
            item.get("path") for item in skills
            if isinstance(item, dict) and item.get("path")
        ]
        return tool_error(
            "unknown_skill",
            f"There is no skill named '{skill}'.",
            "Call list_skills and retry with one exact skill path.",
            skill=skill,
            available_skills=available,
        )

    try:
        path = os.path.abspath(os.path.join(SKILLS_DIR, entry["file"]))
    except (KeyError, TypeError) as error:
        return tool_error(
            "invalid_skill_entry",
            f"The catalog entry for '{skill}' is invalid: {error}",
            "Do not retry unchanged; report that skills.json needs repair.",
            skill=skill,
        )
    if os.path.commonpath([SKILLS_DIR, path]) != SKILLS_DIR:
        return tool_error(
            "invalid_skill_path",
            f"The configured file for '{skill}' is outside the skills directory.",
            "Do not retry unchanged; report that skills.json needs repair.",
            skill=skill,
        )
    try:
        with open(path, encoding="utf-8") as file:
            return result(True, file.read(), path=path, skill=skill)
    except OSError as error:
        return tool_error(
            "skill_file_unavailable",
            f"Cannot read the file for '{skill}': {error}",
            "Do not retry unchanged; report the missing or unreadable skill file.",
            path=path,
            skill=skill,
        )


TOOL_HANDLERS = {
    "bash": run_bash,
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "replace_in_file": replace_in_file,
    "list_skills": list_skills,
    "read_skill": read_skill,
}


def tool_spec(name):
    for item in TOOLS:
        function = item["function"]
        if function["name"] == name:
            return function["parameters"]
    return None


def expected_arguments(name, spec):
    required = set(spec["required"])
    parts = []
    for key, value in spec["properties"].items():
        suffix = "" if key in required else " (optional)"
        parts.append(f"{key}: {value['type']}{suffix}")
    return f"{name}({', '.join(parts)})"


def validate_arguments(name, arguments, spec):
    expected = expected_arguments(name, spec)
    if not isinstance(arguments, dict):
        return tool_error(
            "arguments_not_object",
            "Tool arguments must be one JSON object.",
            f"Retry using this argument shape: {expected}.",
        )

    properties = spec["properties"]
    missing = [key for key in spec["required"] if key not in arguments]
    unexpected = [key for key in arguments if key not in properties]
    wrong_types = [
        key for key, value in arguments.items()
        if key in properties
        and properties[key]["type"] == "string"
        and not isinstance(value, str)
    ]

    problems = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if unexpected:
        problems.append(f"unexpected: {', '.join(unexpected)}")
    if wrong_types:
        problems.append(f"must be strings: {', '.join(wrong_types)}")
    if not problems:
        return None

    return tool_error(
        "invalid_arguments",
        "Invalid tool arguments (" + "; ".join(problems) + ").",
        f"Retry using this argument shape: {expected}.",
        received=list(arguments),
    )


def call_tool(call):
    if not isinstance(call, dict):
        return tool_error(
            "invalid_tool_call",
            "The tool call is not an object.",
            "Create a new function tool call using the advertised tool schema.",
        )

    function = call.get("function")
    if not isinstance(function, dict):
        return tool_error(
            "invalid_tool_call",
            "The tool call has no valid function object.",
            "Create a new function tool call with a name and JSON arguments.",
        )

    name = function.get("name", "")
    raw = function.get("arguments", "{}")
    spec = tool_spec(name)
    if not spec:
        available = sorted(TOOL_HANDLERS)
        return tool_error(
            "unknown_tool",
            f"There is no tool named '{name}'.",
            "Retry with one of these exact tool names: " + ", ".join(available),
            requested_tool=name,
            available_tools=available,
        )

    try:
        arguments = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as error:
        expected = expected_arguments(name, spec)
        return tool_error(
            "invalid_json",
            f"Tool arguments are not valid JSON: {error.msg} at "
            f"line {error.lineno}, column {error.colno}.",
            f"Retry with one JSON object shaped like: {expected}.",
        )

    invalid = validate_arguments(name, arguments, spec)
    if invalid:
        return invalid

    shown = arguments
    if name == "write_file":
        shown = {"path": arguments.get("path"), "content": "<omitted>"}
    if name == "replace_in_file":
        shown = {"path": arguments.get("path"), "old": "<omitted>"}
        shown["new"] = "<omitted>"
    print(f"Tool: {name} {json.dumps(shown)}", file=sys.stderr)

    handler = TOOL_HANDLERS[name]
    try:
        outcome = handler(**arguments)
    except Exception as error:
        return tool_error(
            "tool_execution_error",
            f"The tool raised {type(error).__name__}: {error}",
            "Do not repeat the call unchanged. Correct its arguments, use an "
            "alternative tool or report the unexpected tool failure.",
            tool=name,
        )

    if not isinstance(outcome, dict):
        return tool_error(
            "invalid_tool_result",
            f"The tool returned {type(outcome).__name__}, not a result object.",
            "Do not retry unchanged; report the broken tool implementation.",
            tool=name,
        )
    if not outcome.get("ok") and "error" not in outcome:
        message = outcome.get("output") or "The tool failed without details."
        return tool_error(
            "tool_failed",
            message,
            "Inspect the message, correct the arguments and retry only if the "
            "cause is understood.",
            exit_code=outcome.get("exit_code", 1),
            **{key: value for key, value in outcome.items()
               if key not in {"ok", "exit_code", "output"}},
        )
    return outcome


def run_prompt(messages, prompt):
    messages.append({"role": "user", "content": prompt})

    for _ in range(MAX_TURNS):
        assistant = chat(messages)
        calls = assistant.get("tool_calls") or []
        if not isinstance(calls, list):
            raise RuntimeError("The model returned tool_calls as a non-list.")
        for index, call in enumerate(calls):
            if not isinstance(call, dict):
                call = {
                    "type": "function",
                    "function": {"name": "", "arguments": "{}"},
                }
                calls[index] = call
            if not call.get("id"):
                call["id"] = f"opx_call_{next(CALL_IDS)}"
        if calls:
            assistant["tool_calls"] = calls
        messages.append(assistant)

        if not calls:
            print(f"\nAnswer: {assistant.get('content') or ''}\n")
            return

        # Execute every tool call from this response before calling the LLM again.
        for call in calls:
            try:
                tool_output = call_tool(call)
            except Exception as error:
                tool_output = tool_error(
                    "tool_dispatch_error",
                    f"Tool dispatch raised {type(error).__name__}: {error}",
                    "Do not repeat the call unchanged. Correct its structure "
                    "or report the unexpected dispatcher failure.",
                )
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(tool_output),
            })

    print(f"Error: reached {MAX_TURNS} agent turns.", file=sys.stderr)


def main():
    global YOLO
    arguments = sys.argv[1:]
    if arguments not in ([], ["--yolo"]):
        raise SystemExit("Usage: ./opx.py [--yolo]")
    if arguments:
        enable_yolo()
        print(
            "WARNING: --yolo disables Bash guardrails and approvals.",
            file=sys.stderr,
        )

    print(f"OPX using {MODEL} at {BASE_URL}")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if YOLO:
        messages.append({
            "role": "system",
            "content": "YOLO mode is active. Tools run without approval.",
        })

    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
        if not prompt:
            raise SystemExit("Error: no prompt received on standard input.")
        try:
            run_prompt(messages, prompt)
        except (OSError, RuntimeError, KeyError, ValueError) as error:
            raise SystemExit(f"Error: {error}") from error
        return

    print("Exit with 'exit', 'quit', or 'ende'.\n")
    while True:
        try:
            prompt = terminal_input("Prompt: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        except OSError as error:
            raise SystemExit(f"Interactive terminal required: {error}")

        if prompt.casefold() in {"exit", "quit", "ende"}:
            return
        if prompt:
            try:
                run_prompt(messages, prompt)
            except (OSError, RuntimeError, KeyError, ValueError) as error:
                print(f"Error: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
