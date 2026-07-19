# 01 — Cognitive Filters

This chapter applies the Unix filter pattern to language-model tasks. Each script reads data from standard input, performs one narrowly defined cognitive operation, and writes its result to standard output:

```text
stdin → one LLM request → stdout
```

The scripts are intentionally small and repetitive. Their purpose is educational: each example exposes the complete API request so that you can see how a traditional Unix filter can wrap a language model.

## Learning objectives

After completing this chapter, you should understand how to:

- read piped input in a shell script;
- encode arbitrary text safely as JSON;
- provide instructions and input through different message roles;
- constrain model output with a strict JSON Schema;
- turn a schema-backed API response into plain text or JSON; and
- compose cognitive filters with standard Unix tools.

## Requirements

The examples require:

- Bash;
- `curl`;
- `jq`;
- `fold`; and
- an OpenAI-compatible Chat Completions API that supports structured output.

Load the shared API configuration before running the examples:

```sh
source ../configure.sh
```

The scripts expect `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` to be available in their environment. Run the examples from this directory:

```sh
cd 01-cognitive-filters
```

## The common filter design

All four scripts use `cat` to consume standard input. Most encode it directly with:

```sh
input_json=$(jq -Rn --arg value "$(cat)" '$value')
```

Command substitution captures the complete input. `jq` then converts it into a valid JSON string, escaping quotation marks, backslashes, and line breaks when necessary. This is safer than inserting unescaped input into the request body.

Each filter sends a non-streaming request to:

```text
$OPENAI_BASE_URL/v1/chat/completions
```

The common settings are:

```json
{
  "temperature": 0.0,
  "reasoning_effort": "none",
  "stream": false
}
```

Every request uses `response_format` with `type` set to `json_schema` and `strict` set to `true`. The model must first produce a predictable JSON value, even when the filter ultimately prints plain text.

The API returns generated content as a JSON-formatted string inside the response object. The scripts therefore use this pattern:

```jq
.choices[0].message.content | fromjson
```

`fromjson` parses the content string into a real JSON value. A subsequent selector can then retrieve a field such as `.summary` or `.category`.

Work through the scripts in the following order, from the simplest output transformation to the richest structured result.

## 1. `summarize.sh` — text in, shorter text out

`summarize.sh` reads a document from standard input and asks the model to summarize it in its original language using no more than three concise sentences.

```sh
cat README.md | ./summarize.sh
```

The response schema is deliberately small:

```json
{
  "type": "object",
  "properties": {
    "summary": { "type": "string" }
  },
  "required": ["summary"],
  "additionalProperties": false
}
```

Although the model returns an object, the filter extracts only its `summary` field:

```sh
jq -er '.choices[0].message.content | fromjson | .summary'
```

The options have useful effects:

- `-e` makes `jq` return a failure status for a missing or null result;
- `-r` prints the string as plain text rather than as a quoted JSON string.

Finally, the output passes through:

```sh
fold -s -w 75
```

This wraps lines at a maximum width of 75 characters and prefers breaking at spaces. The result is human-readable text suitable for a terminal or text file.

```sh
cat README.md | ./summarize.sh > summary.txt
```

## 2. `translate.sh` — adding a command-line parameter

`translate.sh` translates standard input into a target language supplied as its only command-line argument:

```sh
printf '%s\n' 'The build completed successfully.' | ./translate.sh de
```

Possible output:

```text
Der Build wurde erfolgreich abgeschlossen.
```

The source language is not specified. The model infers it from the input. The script requires exactly one argument:

```sh
if (( $# != 1 )); then
  echo "Usage: $0 TARGET_LANGUAGE" >&2
  exit 2
fi
```

This demonstrates an important interface rule: document content travels through `stdin`, while control information travels through command-line arguments.

The target language becomes part of the system instruction:

```text
Translate the input to de.
```

The text itself remains alone in the user message. Both values are JSON-encoded before being placed in the request.

Unlike the other filters, `translate.sh` explicitly rejects empty or whitespace-only input. It writes a diagnostic to standard error and exits with status `1`. Invalid argument counts produce a usage message and exit status `2`.

Its strict schema requires one string named `translation`. The final `jq` filter extracts that field as plain text.

## 3. `classify.sh` — choosing from a fixed vocabulary

`classify.sh` maps input text to exactly one category:

```sh
echo 'The application crashes during startup.' | ./classify.sh
```

Possible output:

```text
bug
```

The schema restricts `category` with an enumeration:

```json
{
  "category": {
    "type": "string",
    "enum": ["bug", "feature", "question", "other"]
  }
}
```

The possible output values are therefore:

- `bug` for defect reports;
- `feature` for requested capabilities;
- `question` for requests for information; and
- `other` when none of the first three categories applies.

The model returns an object such as `{"category":"bug"}` in the message content. The script parses it, selects `.category`, and uses `jq -r` to print only the unquoted label.

A stable label is easy to use in shell control flow:

```sh
category=$(echo 'Please add a dark mode.' | ./classify.sh)

case "$category" in
  bug)      echo 'Send to the defect queue' ;;
  feature)  echo 'Send to product planning' ;;
  question) echo 'Send to support' ;;
  other)    echo 'Review manually' ;;
esac
```

This filter demonstrates why schema constraints matter: downstream code can compare a small known set of values instead of trying to interpret free-form prose.

## 4. `extract.sh` — converting text into a data structure

`extract.sh` turns unstructured invoice text into a structured JSON object:

```sh
echo 'Invoice RE-2026-017 from Example GmbH: 149.90€.' | ./extract.sh
```

A possible result is:

```json
{
  "sender": "Example GmbH",
  "invoice_number": "RE-2026-017",
  "amount": 149.9,
  "currency": "EUR"
}
```

The schema defines four properties:

| Property | Allowed types |
|---|---|
| `sender` | string or null |
| `invoice_number` | string or null |
| `amount` | number or null |
| `currency` | string or null |

All four properties are required, but each may be `null`. This distinction is useful: the output shape remains stable even when the input does not contain every value.

The schema also sets:

```json
"additionalProperties": false
```

The response may therefore contain only the four documented fields. Unlike the preceding filters, `extract.sh` does not select one property after `fromjson`. It prints the complete parsed object, preserving JSON for subsequent processing.

For example, `jq` can select the invoice amount:

```sh
echo 'Invoice RE-2026-017 from Example GmbH: 149.90€.' \
  | ./extract.sh \
  | jq '.amount'
```

## Shell safety and failure behavior

Every script starts with:

```sh
set -euo pipefail
```

This enables three Bash safety options:

- `-e` stops the script when a command fails;
- `-u` treats an unset variable as an error; and
- `pipefail` makes a pipeline fail when any command in it fails.

The API calls use `curl -fSs`:

- `-f` reports HTTP error responses as failures;
- `-S` displays an error message when a request fails; and
- `-s` hides normal progress output.

Together with `jq -e`, these settings help prevent an HTTP failure, malformed response, or missing result from being mistaken for successful filter output.

## Comparing the filters

| Script | Input | Argument | Output |
|---|---|---|---|
| `summarize.sh` | text on `stdin` | none | plain text wrapped at 75 characters |
| `translate.sh` | text on `stdin` | target language | plain translated text |
| `classify.sh` | text on `stdin` | none | one category label |
| `extract.sh` | invoice text on `stdin` | none | one JSON object |

The internal response format is structured in every case. The public filter output, however, is chosen for its next consumer: text for people and text pipelines, a single label for branching, and JSON for structured data processing.

## Limits of these examples

Each filter performs exactly one model request. The scripts do not call tools selected by the model, modify files, execute external actions, retain conversation history, or manage a multi-step agent loop.

Those limitations are intentional. A small input/output contract makes each cognitive operation easier to inspect, test, and combine with other Unix programs.
