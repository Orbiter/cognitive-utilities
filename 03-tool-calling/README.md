# 03 — Tool Calling

This chapter extends a normal LLM request with tools. The model can either answer
directly or return a structured request to call a function.

```text
user prompt
  → LLM requests a tool
  → host program runs the tool
  → tool result is added to the conversation
  → LLM writes the final answer
```

The LLM does not execute Python or shell commands. It only selects a tool and
provides arguments. The surrounding program remains responsible for validating
the arguments, executing the function, and returning its result.

## Learning goals

After this chapter, you should be able to:

- describe a function with a name, description, and JSON parameter schema;
- recognize a tool call in an assistant response;
- execute a requested function in the host program;
- add the tool call and result to the conversation;
- handle zero, one, or two tool calls;
- route calls to different helper functions;
- distinguish this single-step flow from a full agentic loop.

## Requirements

- Bash
- `curl`
- Git
- `jq`
- `rg`
- Python 3
- an OpenAI-compatible endpoint with tool-calling support

Load the workshop configuration before running the examples:

```bash
source ../configure.sh
```

## Scripts

| Script | Purpose |
|---|---|
| `basic-tool-call.sh` | Introduces a minimal `lightswitch` tool definition. |
| `basic-tool-response.sh` | Adds a known tool result to the conversation. |
| `calculator-tool-call.sh` | Asks the LLM to produce a structured calculator call. |
| `calculator-tool-response.sh` | Supplies a calculator call and its known result, then asks for the final response. |
| `calculator.sh` | Implements the complete zero-or-one-tool-call flow as a filter. |
| `inspect.sh` | Searches and reads repository files with up to two tool calls. |
| `history.sh` | Searches and inspects Git history with up to two tool calls. |

The examples intentionally repeat some code. Each script should remain readable
on its own during a workshop.

## 1. Define a tool

Run:

```bash
./basic-tool-call.sh
```

The request contains an ordinary conversation plus a function definition:

```json
{
  "name": "lightswitch",
  "description": "With this tool you can switch on the light",
  "parameters": {
    "type": "object",
    "properties": {
      "switch": {
        "type": "boolean",
        "description": "true for on, false for off"
      }
    },
    "required": ["switch"],
    "additionalProperties": false
  },
  "strict": true
}
```

The descriptions tell the model when to use the tool and how to fill its
arguments. The schema states that `switch` is required, must be a boolean, and
that no additional arguments are allowed.

The response may contain a tool call such as:

```json
{
  "name": "lightswitch",
  "arguments": "{\"switch\":true}"
}
```

This is a request to the host program. It does not mean that a light has already
been switched on.

## 2. Return a tool result

Run:

```bash
./basic-tool-response.sh
```

This example takes the result for granted and adds it as a `tool` message:

```json
{
  "role": "tool",
  "tool_call_id": "0",
  "name": "lightswitch",
  "content": "The light was switched on"
}
```

The next LLM response can now turn that machine-oriented result into a natural
language answer. No real light switch is implemented in this example.

## 3. Ask for a calculator call

Run:

```bash
./calculator-tool-call.sh
```

The script introduces three variables that will also be used by the complete
program:

- `messages` contains the conversation;
- `tools` contains the available function definitions;
- `answer` contains the LLM response.

The `llm` function sends the current `messages` and `tools` to the API. For the
fixed question about seconds in 17 days, the assistant should request the
`calculator` tool with an argument similar to:

```json
{
  "term": "17 * 24 * 60 * 60"
}
```

The argument is a string because the model creates the expression while Python
will evaluate it later.

## 4. Continue after a calculator call

Run:

```bash
./calculator-tool-response.sh
```

This script skips the actual calculation. Its `messages` variable already
contains:

1. the user question;
2. the assistant tool call;
3. the known tool result `1468800`.

The `tool_call_id` connects the result to the assistant's request:

```json
{"role":"tool","tool_call_id":"call_calculator","name":"calculator","content":"1468800"}
```

The script performs only the final LLM request and prints the complete API
response. This isolates the second half of the protocol before both halves are
combined.

## 5. Put the flow together

`calculator.sh` is a filter: it reads a prompt from standard input and writes the
assistant answer to standard output.

```bash
echo "How many seconds are there in 17 days?" | ./calculator.sh
```

For an arithmetic question, the flow is:

```text
prompt → LLM → calculator call → Python → tool result → LLM → answer
```

For a question that needs no calculation, the first assistant response is
returned directly:

```bash
echo "Three little pigs built a house. Which one survives?" | ./calculator.sh
```

```text
prompt → LLM → answer
```

The program therefore does not need a real loop. One conditional handles both
possibilities:

```bash
if call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); then
  # calculate and ask the LLM once more
fi
```

There can be zero or one calculator call. The next example adds a small,
deliberately bounded loop.

## Executing the requested function

When the assistant requests the calculator, the script:

1. reads `function.arguments`;
2. parses the JSON string and extracts `term`;
3. parses the expression with Python's `ast` module;
4. accepts only numeric constants and arithmetic operators;
5. evaluates the checked expression;
6. adds the assistant tool call and tool result to `messages`;
7. calls the LLM again for the final answer.

The AST check matters because tool arguments are model output and must be treated
as untrusted input. The term is never passed to a shell.

For workshop visibility, `calculator.sh` prints the executed calculation before
the final answer:

```text
# Tool Call: compute '17 * 24 * 60 * 60' = 1468800
```

## Conversation state

After a tool has run, both messages are kept in the conversation:

```text
assistant: requests calculator(term)
tool:      returns the result for that request
```

Keeping the assistant message is important: the following `tool` message refers
to it through `tool_call_id`. The final LLM request can then see what was
requested and what the host program returned.

## 6. Allow two investigative steps

`inspect.sh` is the bridge from one optional tool call to an agentic loop. It
answers questions about this repository with two read-only Bash helpers:

- `find_file` searches for exact text and returns matching relative paths;
- `read_file` returns the first 200 lines of a known relative path.

The examples cover every intended route:

```bash
# No tool: answer from general knowledge
echo "What is a README file?" | ./inspect.sh

# One tool: search for a file
echo "Which file contains 'Python Guardrails'?" | ./inspect.sh

# One tool: read a path already given by the user
echo "Summarize the README.md." | ./inspect.sh

# Two tools: discover a path, then inspect it
echo "Find the file containing 'Python Guardrails', read it, and explain the guardrails." | ./inspect.sh
```

The last prompt requires dependent tool calls:

```text
prompt
  → find_file("Python Guardrails")
  → one or more matching paths
  → read_file(a matching path)
  → final answer
```

The second call cannot be prepared in advance because its path comes from the
first result.

### A bounded loop

Instead of duplicating the calculator's `if`, the script checks for another tool
call at most twice:

```bash
for step in 1 2; do
  call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer") || break
  # run the tool, append its result, and ask again
done
```

The loop stops early as soon as the assistant gives a normal answer. Its fixed
upper bound makes the three possible flows easy to see:

```text
0 calls: LLM → answer
1 call:  LLM → tool → LLM → answer
2 calls: LLM → tool → LLM → tool → LLM → answer
```

### Tool routing

The model chooses a function by name. The host program maps that name to an
explicitly allowed Bash function:

```bash
case "$name" in
  find_file) find_file ... ;;
  read_file) read_file ... ;;
  *) echo "Error: unknown tool '$name'" ;;
esac
```

`read_file` rejects absolute paths, missing files, symlinks, and paths outside
the repository. `find_file` limits output to ten paths, while `read_file` limits
output to 200 lines. These boundaries keep tool results small and make the
example safe to run in the workshop repository.

## 7. Wrap an existing command-line tool

`history.sh` applies the same bounded flow to Git. Its two read-only helpers
answer questions about the repository's past:

- `git_log` lists recent commits or searches their messages;
- `git_show` returns metadata, changed files, and a patch for a known commit.

The examples again exercise zero, one, and two calls:

```bash
# No tool: answer from general knowledge
echo "What is a Git commit?" | ./history.sh

# One tool: list recent history
echo "What are the latest commits in this repository?" | ./history.sh

# One tool: inspect a hash already given by the user
echo "Summarize commit 182b60b." | ./history.sh

# Two tools: discover a commit, then inspect it
echo "Find the commit that added the basic LLM shell examples and explain what it changed." | ./history.sh
```

The examples refer to this repository's actual history:

```text
182b60b  better config, added comments
fa1dcd7  added basic LLM shell examples
```

For the last question, the model does not initially know the commit hash:

```text
prompt
  → git_log("basic LLM shell examples")
  → commit: fa1dcd7
  → git_show("fa1dcd7")
  → final explanation
```

This is the same dependency pattern as `find_file` followed by `read_file`.
Only the tool implementation has changed: instead of custom file operations,
the helpers wrap a familiar command-line program.

### Constrain command-line tools

Tool arguments must not be appended to a command string and evaluated. Each
value is passed as one quoted argument to a fixed Git command:

```bash
git -C "$repo_root" log ... --grep="$query"
git -C "$repo_root" show ... "$commit"
```

`git_show` accepts only a hexadecimal commit hash. It resolves that hash as a
commit before running `git show`, rejects option-like or unknown revisions, and
limits the result to 200 lines. The script exposes no Git command that changes
the working tree or repository history.

The tools inspect committed history only. Uncommitted files and working-tree
changes are intentionally outside their scope.

## Safety lessons

- Tool calls are data, not commands.
- Only explicitly defined tools should be executable.
- Validate arguments again in the host program.
- Do not pass model-generated text to a shell.
- Wrap command-line tools with fixed commands and quoted arguments.
- Connect each result to its request with `tool_call_id`.
- Keep diagnostics separate from machine-readable output in production tools.
- Limit the number of tool calls unless a deliberate agentic loop is required.

## Next chapter

[`04-agentic-loop`](../04-agentic-loop/) generalizes these bounded two-step loops
into an agent that can keep selecting and running tools until it reaches a final
answer or a configured step limit.
