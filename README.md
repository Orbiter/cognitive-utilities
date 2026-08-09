# Cognitive Utilities

> Example code and tutorial repository for the workshop  
> **“Build Your Own AI Agents with Local LLMs”**

How does an AI agent work when reduced to its essential components? This repository answers that question with small, executable examples:

```text
LLM + prompt + tools + loop = simple agent
```

Instead of using a ready-made agent framework, the material exposes the individual mechanisms. The examples begin with a direct HTTP request to a local model and progress through structured output and tool calls to agents that can perform local operations.

This repository serves as:

- a source code collection for the workshop's live demonstrations;
- a step-by-step tutorial for self-study;
- a starting point for experiments with local LLMs; and
- an illustration of how coding agents work internally.

## What the workshop is about

The workshop shows how to run small AI utilities and agents under your own control. The included configuration uses an open-weight model through [Ollama](https://ollama.com/) and does not require a cloud API. Once Ollama and the model are available locally, the examples can run against the local endpoint.

The goal is not to build the largest possible “super-agent,” but to create a comprehensible toolkit. Each stage answers one concrete question:

1. How is a prompt transmitted as an API request?
2. How does a single LLM request become a Unix-style filter?
3. How can multiple records be processed as a JSONL pipeline?
4. How does a model request a tool and receive its result?
5. How does that exchange become a loop with multiple tool calls?
6. How can local shell and file operations be controlled and approved?
7. How does a small coding agent combine these building blocks?
8. How can reusable instructions turn a general agent into a specialist?
9. How can an existing utility run unattended on a schedule?

The examples are deliberately small and direct. Request bodies, conversation history, tool descriptions, validation, and loops remain visible in the code and can be modified during the workshop.

## The basic pattern

The first utilities follow the traditional filter pattern:

```text
stdin → LLM request → stdout
```

A tool call extends this pattern. The model does not execute the tool itself; it only produces a structured request. The calling script decides whether and how to execute it:

```text
User request
     ↓
    LLM
     ↓
 Tool request
     ↓
Validate and execute
     ↓
 Tool result
     ↓
    LLM
     ↓
 Final answer
```

An agentic loop repeats this exchange until the model responds without another tool request or an implemented limit is reached.

## Learning path through the repository

The directories are numbered. For the workshop, work through them in order.

### 00 — API basics

[`00-api-basics`](00-api-basics/) presents the Chat Completions interface without additional abstraction. The shell examples send their JSON request bodies directly with `curl`; `chat.py` demonstrates the same idea using Python's standard library.

Included scripts:

| Script | Subject |
|---|---|
| `chat.sh` | A non-streaming chat request |
| `chat.py` | A chat request using Python instead of `curl` |
| `chat-terminal.py` | An interactive Python chat that retains the conversation history |
| `chat-stream.sh` | A streamed response |
| `context.sh` | System, user, and assistant messages as conversation context |
| `forms-json_.sh` | JSON requested only through prompting |
| `forms-json_object.sh` | The `json_object` response format |
| `forms-json_schema.sh` | Strict schema-constrained output |
| `vision.sh` | A local image represented as a Base64 data URL |
| `vision-forms.sh` | Image processing with strict structured output |

First experiment:

```bash
source ./configure.sh
./00-api-basics/chat.sh
```

The vision examples use a relative image path and must be run from their directory:

```bash
cd 00-api-basics
./vision.sh
```

While reading the scripts, pay particular attention to `messages`, `stream`, and `response_format`. Then compare the three `forms-*` variants: what is requested only through the prompt, and what is structurally constrained by the API?

The [chapter README](00-api-basics/README.md) explains every request in detail.

### 01 — Cognitive filters

[`01-cognitive-filters`](01-cognitive-filters/) turns one LLM request into a small command-line utility. Text arrives on `stdin`; `stdout` contains only the result selected by the script.

| Script | Input and output |
|---|---|
| `summarize.sh` | Text → a summary of no more than three sentences |
| `classify.sh` | Text → `bug`, `feature`, `question`, or `other` |
| `extract.sh` | Invoice text → JSON containing sender, invoice number, amount, and currency |
| `translate.sh TARGET_LANGUAGE` | Text and target language → translated text |

Examples:

```bash
printf '%s\n' 'The application crashes during startup.' \
  | ./01-cognitive-filters/classify.sh

printf '%s\n' 'The build completed successfully.' \
  | ./01-cognitive-filters/translate.sh de

printf '%s\n' 'Invoice RE-2026-017 from Example GmbH: 149.90 EUR.' \
  | ./01-cognitive-filters/extract.sh
```

All four filters internally require output matching a strict JSON Schema. Examine how `jq` safely encodes input text as JSON and converts the JSON string from `message.content` back into a value.

See the [chapter README](01-cognitive-filters/README.md) for more detail.

### 02 — Map, filter, and reduce

[`02-map-reduce`](02-map-reduce/) applies the filter pattern to sequences of records. JSON Lines is the interchange format: each line contains one complete JSON object.

| Script | Function |
|---|---|
| `map-lines.sh` | Nonblank lines → `{id, text}` records |
| `map-paragraphs.sh` | Paragraphs → `{id, text}` records |
| `filter-classify.sh` | Adds `category` to every record through `classify.sh` |
| `filter-category.sh CATEGORY` | Keeps only records matching one category |
| `filter-triage.sh` | Adds category, priority, summary, and route through an LLM |
| `reduce-category-counts.sh` | Produces total and per-category counts |
| `reduce-report.sh` | Reduces JSONL records to a structured LLM-generated report |

A complete pipeline:

```bash
printf 'Server unavailable.\nAdd dark mode.\nHow do I log in?\n' \
  | ./02-map-reduce/map-lines.sh \
  | ./02-map-reduce/filter-classify.sh \
  | ./02-map-reduce/reduce-category-counts.sh
```

The included `02-map-reduce/article.txt` can be used with the paragraph mapper:

```bash
./02-map-reduce/map-paragraphs.sh < ./02-map-reduce/article.txt
```

As an exercise, insert `tee` between pipeline stages. This makes the JSONL format expected and produced by each stage visible. See the [chapter README](02-map-reduce/README.md) for details.

### 03 — Tool calling

[`03-tool-calling`](03-tool-calling/) first demonstrates the message exchange behind a tool call, then executes small, bounded local tools.

| Script | Subject |
|---|---|
| `basic-tool-call.sh` | A fixed light-switch request with a tool description |
| `basic-tool-response.sh` | A fixed light-switch result returned to the model |
| `calculator-tool-call.sh` | A model-generated tool call for a fixed arithmetic question |
| `calculator-tool-response.sh` | A model response after a predefined calculator result |
| `calculator.sh` | A question from `stdin`, optional local evaluation, and a final answer |
| `inspect.sh` | Up to two search or read operations on files in this repository |
| `history.sh` | Up to two read-only `git log` or `git show` operations |

Start with the complete calculator:

```bash
printf '%s\n' 'How many seconds are there in 17 days?' \
  | ./03-tool-calling/calculator.sh
```

When the model requests the calculator, the script displays the expression and local result. Before Python evaluates it, only numbers and arithmetic operators are permitted.

Next, let the repository inspector choose from its bounded tools:

```bash
printf '%s\n' 'Which scripts define a calculator tool?' \
  | ./03-tool-calling/inspect.sh
```

Compare `calculator-tool-call.sh`, `calculator-tool-response.sh`, and `calculator.sh`. Together they show the three parts of the protocol: tool request, tool result, and another LLM request. The [chapter README](03-tool-calling/README.md) provides further explanation.

### 04 — Agentic loops

[`04-agentic-loop`](04-agentic-loop/) repeats tool calls. The tools are deliberately restricted to one investigation task each.

| Script | Loop |
|---|---|
| `sysop-synthetic-log.sh` | Follows identifiers through an embedded synthetic log |
| `sysop-system-log.sh` | Lists and searches files below `/var/log`, with call and repetition limits |
| `mastermind-research.sh` | Experiments with a four-bit Mastermind game to determine its hidden code |
| `mandelbrot.sh` | Renders ASCII Mandelbrot observations while searching for a smaller copy of the reference image |
| `search-server.py` | Provides JSON search results from a local copy of the BGB through HTTP |
| `search-agent.py` | Uses that search API as a tool in a German-language agentic loop |
| `search-client.html` | Tests the search server directly from a browser, including via `file://` |
| `yacy-agent.py` | Uses a local YaCy index as the search backend of an agentic loop |

The synthetic examples do not modify the system, making them a good place to study only the loop:

```bash
printf '%s\n' 'Diagnose incident INC-781.' \
  | ./04-agentic-loop/sysop-synthetic-log.sh

printf '%s\n' 'Find the hidden code.' \
  | ./04-agentic-loop/mastermind-research.sh
```

Find the `while` loop in each script. The important detail is that every tool result causes both the assistant message containing the tool call and a corresponding tool message to be appended to `messages`.

The search-backed loop runs as two processes:

```bash
./04-agentic-loop/search-server.py
./04-agentic-loop/search-agent.py
```

`search-client.html` provides a small browser-based test client for the same API.

`yacy-agent.py` demonstrates the same search-agent pattern with a separately
running YaCy instance at `http://127.0.0.1:8090`.

The [chapter README](04-agentic-loop/README.md) describes the variants in more detail.

### 05 — Controlled local operations

[`05-operation-execution`](05-operation-execution/) applies the agentic loop to general local operations. Its variants deliberately demonstrate different levels of control, from direct execution to individual approval and strict self-isolation.

| Script | Available operations |
|---|---|
| `opx-bash.sh` | Guarded Bash commands with an inline, last-match-wins `allow`/`ask`/`deny` policy |
| `opx-bash-terminal.sh` | Interactive, non-streaming Bash agent that retains the complete conversation and tool history |
| `opx-rw.sh` | Current-directory `list_files`, `read_file`, and no-overwrite `write_file` tools |
| `opx-evo.sh` | Can only read, replace, and restart its own Bash source, without approval prompts |

A read-oriented task:

```bash
printf '%s\n' 'Inspect this directory and summarize its contents.' \
  | ./05-operation-execution/opx-bash.sh
```

`opx-bash.sh` can process several commands returned in one model response. Each
call is logged to standard error and checked for shell-composition characters.
An inline JSON policy is evaluated in source order, with the last matching rule
winning: `allow` runs directly, `ask` requests approval on `/dev/tty`, and `deny`
rejects the command. The character guard also rejects command substitutions and
newlines before the configurable policy is evaluated.

For an ongoing conversation with the same Bash tools and guardrails, start the
non-streaming terminal variant without a pipe:

```bash
./05-operation-execution/opx-bash-terminal.sh
```

Every final answer, tool request, and tool result remains in its conversation
context until the program is closed with `exit`, `quit`, `ende`, or EOF.

A task that may change a file:

```bash
printf '%s\n' 'Inspect the current directory and create a short report.' \
  | ./05-operation-execution/opx-rw.sh
```

`opx-rw.sh` can process several tool calls returned in one model response. It logs tool calls to standard error, executes the complete batch in order, appends one result for every tool-call ID, and then asks the model again. Logs show all arguments except `write_file` content, for which only the filename is printed. Its file tools are intentionally direct: `list_files` runs `ls -la`, `read_file` calls `cat`, and `write_file` creates a new file. `list_files` can be called only once per run. The read and write tools accept only a filename in the current directory and reject `/`; `write_file` also rejects existing files, uses Bash's no-clobber mode, and can be called only once per run. Its result tells the model to finish with a final answer. There are no approval or size checks.

`opx-evo.sh` is a deliberately isolated self-modification experiment. It has no
Bash tool and accepts no paths: the model can only read its own source, replace
that source after syntax validation, and restart with the original prompt. These
operations execute directly without interactive approval. Tool calls are logged
to standard error, while replacement source content is omitted from the log.
The evolution prompt requires newly added tools to preserve this logging and add
redaction for large or sensitive parameters. Its API request permits completions
of up to 200,000 tokens, subject to the model server's total context limit.

Compare the variants: `opx-bash.sh` validates and asks before commands, `opx-rw.sh` exposes only bounded file operations, and `opx-evo.sh` confines modification to its own source. Which responsibilities remain with the human operator in each case?

### 06 — The larger OPX coding agent

[`06-coding-agent/opx.py`](06-coding-agent/opx.py) combines the previous building blocks in a larger Python script. A prompt can be supplied as arguments, through `stdin`, or through both. OPX streams the response, processes tool requests, uses another LLM request to judge whether the original task was fulfilled, and may generate a follow-up prompt.

The script implements these tools:

- tool listing, Bash, and read-only Git commands;
- file and directory discovery through `find` and `grep`;
- reading, writing, listing, and creating local paths;
- previewing and applying unified diffs;
- directory trees, manual pages, and process listings; and
- TCP port scanning and reading text-based URLs.

Read operations are approved by default; write or similarly classified operations ask for approval by default. For the first run, further restrict the set of visible tools:

```bash
OPX_ONLY_TOOLS=git,find,grep,read,list,tree \
  ./06-coding-agent/opx.py 'Summarize the current repository state.'
```

Supported control variables:

| Variable | Effect |
|---|---|
| `OPX_ONLY_TOOLS` | Comma-separated list of tools visible to the model |
| `OPX_AUTO_APPROVE` | Changes interactive approval for read or write operations |
| `OPX_TOOL_TIMEOUT_SEC` | Timeout for diff tools; default `300` |
| `OPX_MAX_TURNS` | Maximum number of outer agent turns; default `24` |

For a code-reading exercise, begin with `_tool_instances()`. From there, follow the individual tool classes and then the loop in `main()`.

### 07 — Skills

[`07-skills`](07-skills/) contains a minimal reusable skill. The
`explain-shell-script` example consists of a `SKILL.md` instruction file and
small UI metadata. It teaches an agent to explain shell scripts consistently
without executing them unless execution is explicitly requested.

### 08 — Autonomous worker

[`08-autonomous-worker`](08-autonomous-worker/) turns the summarization filter
from chapter 01 into a small scheduled worker. It reads `README.md`, produces
`latest-report.md`, and includes an example Cron entry without modifying the
user's Crontab automatically.

Run it manually before adding the schedule:

```bash
./08-autonomous-worker/worker.sh
```

## Requirements

Most examples require:

- a Unix-like environment with Bash;
- `curl` and `jq`;
- an OpenAI-compatible endpoint providing `/v1/chat/completions`; and
- a model supporting the feature used by the respective chapter.

Individual scripts additionally use common tools such as `base64`, `fold`, `git`, `python3`, `realpath`, and `sed`. `06-coding-agent/opx.py` itself uses only Python's standard library, but some of its tools invoke external programs such as `git`, `rg`, `patch`, and `man`.

Depending on the example, the API server and model must support streaming, strict structured output, image input, or tool calling.

## Local configuration with Ollama

All API examples read the same five environment variables:

```text
OPENAI_BASE_URL
OPENAI_API_KEY
OPENAI_MODEL
OPENAI_TEMPERATURE
OPENAI_REASONING_EFFORT
```

The included [`configure.sh`](configure.sh) configures Ollama at `http://localhost:11434` and selects the quantized `qwen3.5:4b-q4_K_M` model. The script must be sourced into the current shell:

```bash
source ./configure.sh
```

This exports the variables and runs `ollama pull` for the configured model. The initial download requires Ollama to be installed and may require internet access. Once the model is available locally, the configuration can be used without a cloud API.

To use another compatible local server or model, export the five variables yourself instead.

## Recommended workshop workflow

The same short learning cycle works well for every chapter:

1. Run the smallest example.
2. Read the complete request or tool description in the script.
3. Change one prompt, schema, or tool property.
4. Compare the observed output with the original variant.
5. Combine the utility with an adjacent pipeline stage.

These scripts are demonstration and teaching code. They prioritize visible mechanisms and small files over a complete production architecture.

## Tool-execution safety

Chapters 00 through 04 send API requests, transform data streams, read this repository, or inspect `/var/log`. The scripts in chapters 05 and 06 can execute commands and modify local files. Not every variant asks for approval.

Their boundaries differ:

- `05-operation-execution/opx-bash.sh` rejects shell composition and applies its inline `allow`/`ask`/`deny` policy. Allowed or approved commands can still affect the wider system.
- `05-operation-execution/opx-rw.sh` has no Bash tool. It can list the current directory, read filenames without `/`, and create—but not overwrite—files without approval. Existing symlinks can still affect reads.
- `06-coding-agent/opx.py` does not confine every tool to this repository and also provides network operations.
- `OPX_AUTO_APPROVE` can reduce or bypass interactive checks in the Python agent.

Run `opx-rw.sh` only in an expendable, isolated environment. Read requests carefully before approving the other agents, and use `OPX_ONLY_TOOLS` to restrict the Python agent to the tools needed for the task.
