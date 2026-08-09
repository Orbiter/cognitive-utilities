# 04 — Agentic Loop

Chapter 03 allowed a model to use zero, one, or two tools. The number of steps
was fixed by the host program.

This chapter removes that assumption. The model can inspect one result, decide
that more evidence is needed, and request another tool call. The host continues
until the model returns a normal answer.

```text
task
  → LLM
  → tool call?
      yes → run tool → append result → LLM
      no  → final answer
```

The central idea is deliberately small:

```bash
# Chapter 03: at most one step
if call=...; then
  ...
fi

# Chapter 04: investigate until done
while call=...; do
  ...
done
```

That loop is the foundation of an agent.

## Learning goals

After this chapter, you should be able to:

- turn a single tool call into an agentic loop;
- preserve the conversation across multiple iterations;
- let one observation determine the next tool call;
- process several tool calls from one assistant message;
- route calls to different helper functions;
- enforce call, path, and output limits;
- detect an investigation that repeats itself;
- distinguish a read-only agent from a coding agent.

## Requirements

- Chapter [`03-tool-calling`](../03-tool-calling/)
- Bash
- Python 3
- `curl`
- `jq`
- `grep`, `find`, `gzip`, and `realpath`
- an OpenAI-compatible endpoint with tool-calling support
- access to `/var/log` for the real-system example

Load the workshop configuration before running the examples:

```bash
source ../configure.sh
```

## Scripts

| Script | Purpose |
|---|---|
| `sysop-synthetic-log.sh` | Demonstrates the smallest useful agentic loop with one tool and deterministic data. |
| `sysop-system-log.sh` | Applies the loop to real system logs with two tools and practical limits. |
| `mastermind-research.sh` | Discovers a hidden four-bit code through repeated experiments. |
| `mandelbrot.sh` | Searches an ASCII Mandelbrot image through repeated render experiments. |
| `search-server.py` | Searches one local BGB document and exposes results as JSON over HTTP. |
| `search-agent.py` | Uses the BGB search API as a tool in a German-language agentic loop. |
| `search-client.html` | Provides a minimal browser test page for the search API. |
| `yacy-agent.py` | Uses a local YaCy index as the search backend of an agentic loop. |

The first script isolates the loop. The second retains that loop and adds the
management needed when tools operate on a real system.

## 1. Investigate a synthetic incident

Run:

```bash
echo "Diagnose incident INC-781." | ./sysop-synthetic-log.sh
```

The script contains three synthetic log records:

```text
incident=INC-781 status=unresolved next_id=db-42
incident=db-42   status=unresolved next_id=fs-9
incident=fs-9    status=resolved root_cause="/var/lib is 100% full"
```

Its only tool is:

```text
lookup(id)
```

`lookup` returns exactly one record. An unresolved record reveals the identifier
needed for the next call:

```text
lookup("INC-781")
  → next_id=db-42

lookup("db-42")
  → next_id=fs-9

lookup("fs-9")
  → root_cause="/var/lib is 100% full"

final answer
```

Neither the model nor the host knows the complete sequence as an explicit plan.
Each tool result supplies the information required for the next decision.

## The minimal loop

The first LLM request happens before the loop:

```bash
answer=$(llm)
```

The program then continues for as long as the assistant requests `lookup`:

```bash
while call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); do
  id=$(jq -r '.function.arguments | fromjson | .id' <<<"$call")
  result=$(lookup "$id")
  # append assistant call and tool result
  answer=$(llm)
done
```

When the assistant returns text instead of a tool call, the condition becomes
false and the final answer is printed.

This is the chapter's main insight: an agentic loop is a normal LLM call wrapped
in a repeated tool-response cycle.

## Conversation state

After the three lookups, `messages` contains:

```text
system      diagnostic rules
user        Diagnose incident INC-781.
assistant   lookup(INC-781)
tool        next_id=db-42
assistant   lookup(db-42)
tool        next_id=fs-9
assistant   lookup(fs-9)
tool        root_cause="/var/lib is 100% full"
assistant   final diagnosis
```

The growing `messages` array is the agent's visible state. Every new model call
can see the original task, previous decisions, and all observations.

Each tool result is connected to its request through `tool_call_id`. Omitting an
assistant call or one of its results would leave the protocol incomplete.

## 2. Research a hidden binary code

Run:

```bash
echo "Find the hidden code." | ./mastermind-research.sh
```

The hidden code contains four binary digits. The agent's only tool tests one
possible code and returns the number of bits in the correct position plus the
first position that is wrong. Because each bit has only two states, the tool
also supplies the next experiment directly:

```text
experiment("0000")
  → correct_positions=1, first_wrong_position=1, next_guess="1000"
  → evidence="Position 1, counted from the left, is the first mismatch ..."
```

The agent starts with `0000` and passes each `next_guess` back into the tool.
This deliberately simple chain keeps the focus on the repeated tool exchange.
When `next_guess` is `null`, four correct positions prove the solution. The
script limits the investigation to six experiments, while the tool schema lists
all 16 possible codes explicitly. Its final response must explain the complete
evidence chain rather than merely print the discovered code. The tool supplies
plain-language evidence to prevent ambiguity about bit numbering.

## 3. Investigate real system logs

The synthetic example has one known tool and perfect data. Real investigations
need discovery, bounded access, and failure handling.

Run:

```bash
echo "Inspect /var/log and report recent errors. Make a full audit." \
  | ./sysop-system-log.sh
```

Results depend on the operating system, available logs, file permissions, and
the events recorded on the current machine.

The agent receives two read-only tools:

```text
list(directory)
lookup(path, query)
```

`list` discovers up to 50 entries in a directory. `lookup` searches one plain or
gzip-compressed log and returns at most 20 literal matches.

A possible investigation is:

```text
list("/var/log")
  → system.log, rotated logs, service directories, ...

lookup("/var/log/system.log", "error")
  → matching messages

list("/var/log/apache2")
  → access_log, error_log

lookup("/var/log/apache2/error_log", "fail")
  → matching messages

final audit
```

The model decides which paths and search terms are useful based on earlier
results.

## Tool routing

With more than one tool, the host must route the model's selected function name
to an explicitly implemented helper:

```bash
case "$name" in
  list)   result=$(list ...) ;;
  lookup) result=$(lookup ...) ;;
  *)      result="Error: unknown tool '$name'" ;;
esac
```

The model chooses a tool. The host retains authority over what that name is
allowed to execute.

## Multiple calls in one response

An assistant message may contain several entries in `tool_calls`. Reading only
`tool_calls[0]` would leave the remaining call IDs unanswered.

The real-system example therefore appends the assistant message once and handles
every requested call:

```bash
messages=$(jq --argjson assistant ... '. + [$assistant]' <<<"$messages")

while IFS= read -r call; do
  # execute this call
  # append one tool result with its tool_call_id
done < <(jq -c '.choices[0].message.tool_calls[]' <<<"$answer")
```

Only after every result has been appended does the program call the LLM again.

```text
one assistant message
  ├── list call   → list result
  ├── lookup call → lookup result
  └── lookup call → lookup result
next LLM request
```

Each individual call counts toward the global limit.

## Path boundary

Model-generated paths are untrusted input. Both tools pass their paths through
`safe_path`:

```bash
log_root=$(realpath /var/log)

safe_path() {
  local path
  path=$(realpath "$1" 2>/dev/null) || return 1
  [[ "$path" == "$log_root" || "$path" == "$log_root/"* ]] || return 1
  printf '%s\n' "$path"
}
```

Canonical paths matter because a string beginning with `/var/log` could still
escape through `..` components or symbolic links. `realpath` resolves those
before the boundary comparison.

The tools add their own type checks:

- `list` accepts only a directory;
- `lookup` accepts only a regular file.

Errors are returned as observations so the model can correct its next action.

## Plain and compressed logs

Rotated logs are commonly gzip-compressed. `lookup` hides that storage detail
behind one tool interface:

```bash
case "$path" in
  *.gz) gzip -cd -- "$path" | grep ... ;;
  *)    grep ... "$path" ;;
esac
```

The query is one case-insensitive literal string, not a regular expression.
Searching for several alternatives requires separate calls:

```text
lookup(path, "error")
lookup(path, "fail")
lookup(path, "critical")
```

This keeps model input from becoming executable grep syntax.

## Call limit

An agent may misunderstand a result, explore irrelevant files, or fail to
finish. The real-system example limits the complete investigation to 20
individual tool calls:

```bash
((calls += 1))
((calls <= 20)) || {
  echo "Error: tool call limit reached" >&2
  exit 1
}
```

The counter belongs to the host, not the model. A system instruction can request
careful behavior, but only host code can enforce a resource limit.

## Repetition detection

A model can become stuck requesting the same observation:

```text
lookup("/var/log/system.log", "Error")
lookup("/var/log/system.log", "Error")
lookup("/var/log/system.log", "Error")
```

The script stores a canonical JSON key for every call. When the same tool and
arguments appear again, it returns an error result:

```text
Error: duplicate tool call. Finish with the evidence already collected.
```

The duplicate request is still appended to `messages` because it already exists
in the assistant response and requires a matching tool result. The script then
sets `tools` to an empty array before the next LLM request:

```bash
if [[ "$duplicate_call" == true ]]; then
  tools='[]'
fi
```

The model can now produce a final answer from existing evidence but cannot
request another tool.

## Output and observability

Tool activity is shown during the workshop:

```text
# Tool Call 1: list {"directory":"/var/log"}
# Tool Call 2: lookup {"path":"/var/log/system.log","query":"error"}
```

The final line is extracted from the assistant response:

```bash
jq -er '.choices[0].message.content' <<<"$answer"
```

In a production filter, progress messages would normally go to `stderr`, leaving
only the final answer on `stdout`.

## Search local knowledge through an HTTP tool

The BGB example separates knowledge retrieval from the agent. Start the search
server in one terminal:

```bash
./search-server.py
```

The server downloads `bgb.md` only when the file is missing and then provides a
small JSON API with one query parameter:

```bash
curl --get --data-urlencode 'q=Kauf Mangel Nacherfüllung' \
  http://127.0.0.1:8080/search
```

Start the German-language agent in a second terminal:

```bash
./search-agent.py
```

The agent does not read `bgb.md` itself. Its `bgb_suche(q)` tool calls the HTTP
API, receives ranked text passages as JSON, and returns them to the model. The
model may issue another search with improved terms before answering.

Open `search-client.html` directly in a browser to test the same API without an
LLM. The server permits cross-origin `GET` and `OPTIONS` requests so the client
also works when loaded through a `file://` URL.

## Search a YaCy index

`yacy-agent.py` provides an English-language tool-calling loop backed by YaCy's
`/yacysearch.json` interface. YaCy must already be running and contain indexed
documents.

```bash
./yacy-agent.py
```

By default the agent queries `http://127.0.0.1:8090/yacysearch.json`. Override
that endpoint when necessary:

```bash
YACY_SEARCH_URL=http://search-host:8090/yacysearch.json ./yacy-agent.py
```

The adapter always requests `resource=local`, at most five text results, and
`verify=cacheonly`. This keeps retrieval inside the selected YaCy peer and
prevents result verification from fetching pages from the network.

## Safety lessons

- Tool descriptions guide the model; host code enforces boundaries.
- Treat function names, arguments, paths, and queries as untrusted data.
- Resolve paths before comparing them with an allowed root.
- Keep tools read-only when the task is investigation.
- Bound directory listings, search results, and total calls.
- Return tool errors as observations when the model can recover.
- Answer every call ID when one assistant message requests several tools.
- Detect repeated actions instead of spending the entire call budget.
- Real system logs may contain sensitive operational or personal information.

## Why this is not a coding agent

Both examples investigate and report. They cannot modify files, run arbitrary
commands, apply patches, or change repository state.

Chapter 05 adds approved shell commands and workspace-relative file writes:

```text
investigate → request operation → approve → execute → report
```

That additional responsibility—not the loop itself—is what turns a read-only
investigation into an operation-execution agent.

## Next chapter

[`05-operation-execution`](../05-operation-execution/) reuses the same agentic
loop with approved Bash and file-writing tools.
