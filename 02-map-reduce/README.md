# 02 — Map, Filter, and Reduce

This chapter demonstrates how the map–reduce pattern can organize language-model pipelines. The scripts use JSON Lines as a stable interface between stages:

```text
text → map → JSONL records → filter → JSONL records → reduce → one JSON object
```

Each stage has one responsibility:

- **Map** turns one input into a sequence of independent records.
- **Filter** processes records one at a time. It may enrich every record or retain only matching records.
- **Reduce** combines the complete sequence into one result.

The examples deliberately mix ordinary Unix processing with cognitive processing. Exact operations use Bash and `jq`; operations that require interpretation use a language model with a strict JSON Schema.

## Learning objectives

After working through this chapter, you should understand how to:

- distinguish JSONL from a JSON array;
- map lines and paragraphs to JSONL records;
- validate and process one record at a time;
- call an existing cognitive filter inside a loop;
- pass a JSON object to a schema-constrained model request;
- select records deterministically;
- reduce a sequence with `jq`; and
- reduce a sequence semantically with an LLM.

## Requirements

You need Bash, `curl`, `jq`, and a configured OpenAI-compatible API. Load the repository configuration, then enter this directory:

```sh
source ../configure.sh
cd 02-map-reduce
```

The cognitive examples also use `classify.sh` and `summarize.sh` from `../01-cognitive-filters`.

## Included files

| File | Kind | Purpose |
|---|---|---|
| `article.txt` | Example data | Five paragraphs used by the document examples. |
| `map-lines.sh` | Map | Turns nonempty lines into JSONL records. |
| `map-paragraphs.sh` | Map | Turns paragraphs into JSONL records. |
| `filter-classify.sh` | Filter | Adds a category by calling the chapter 01 classifier. |
| `filter-category.sh` | Filter | Retains records with one selected category. |
| `filter-triage.sh` | Filter | Adds category, priority, summary, and route. |
| `reduce-category-counts.sh` | Reduce | Counts classified records by category. |
| `reduce-report.sh` | Reduce | Synthesizes all records into one report. |

The scripts are explained below in the order in which their concepts build on one another.

## JSON Lines as the pipeline interface

JSON Lines, usually abbreviated as JSONL, contains one complete JSON value per physical line:

```jsonl
{"id":1,"text":"The server is unavailable."}
{"id":2,"text":"Please add dark mode."}
{"id":3,"text":"How do I reset my password?"}
```

This is a sequence of three values, not one JSON array. A JSON array containing similar data would look like this:

```json
[
  {"id": 1, "text": "The server is unavailable."},
  {"id": 2, "text": "Please add dark mode."},
  {"id": 3, "text": "How do I reset my password?"}
]
```

JSONL works naturally with shell loops because a filter can read, validate, and emit one record at a time. Every mapper and filter in this directory emits compact JSONL. Both reducers emit one ordinary JSON object.

## 1. `map-lines.sh` — one record per line

`map-lines.sh` is the simplest mapper. It reads standard input line by line, ignores empty or whitespace-only lines, and assigns a sequential `id` to every remaining line.

```sh
printf 'The server is unavailable.\nPlease add dark mode.\nHow do I reset my password?\n' \
  | ./map-lines.sh
```

Output:

```jsonl
{"id":1,"text":"The server is unavailable."}
{"id":2,"text":"Please add dark mode."}
{"id":3,"text":"How do I reset my password?"}
```

The loop uses:

```sh
while IFS= read -r line || [[ -n "$line" ]]; do
```

`IFS=` preserves leading and trailing spaces, `-r` prevents backslash interpretation, and the final condition also processes a last line that does not end with a newline.

Each output object is constructed with `jq -cn`. Passing the line through `--arg` safely escapes characters that have a special meaning in JSON.

Use this mapper when each physical input line already represents one independent item, such as an issue, log entry, or survey response.

## 2. `map-paragraphs.sh` — one record per paragraph

Documents often contain ideas that span several lines. `map-paragraphs.sh` therefore splits its input at blank lines instead of at every line.

The included [article.txt](article.txt) contains five paragraphs and can be mapped directly:

```sh
./map-paragraphs.sh < article.txt
```

The result contains five JSONL records. The first begins like this:

```jsonl
{"id":1,"text":"Map and reduce are useful patterns for processing collections of information. A map operation transforms one input into a sequence of independent records. Each record can then be inspected, enriched, or processed without changing the other records."}
```

The mapper uses `jq` in raw, slurp, and compact modes:

- `-R` reads the document as raw text;
- `-s` reads the complete document as one value; and
- `-c` prints every resulting object on one compact line.

It normalizes Windows line endings, splits at blank lines, trims surrounding whitespace, removes empty paragraphs, and numbers the remaining records. Newlines inside a paragraph are JSON-escaped, so every record still occupies one physical output line.

## 3. `filter-classify.sh` — call a cognitive filter for every record

The first sequence filter reuses `../01-cognitive-filters/classify.sh`. It expects every input line to be an object with a string field named `text`.

Run a complete map-and-classify pipeline:

```sh
printf 'The server is unavailable.\nPlease add dark mode.\nHow do I reset my password?\n' \
  | ./map-lines.sh \
  | ./filter-classify.sh
```

A possible result is:

```jsonl
{"id":1,"text":"The server is unavailable.","category":"bug"}
{"id":2,"text":"Please add dark mode.","category":"feature"}
{"id":3,"text":"How do I reset my password?","category":"question"}
```

For each line, the script:

1. validates and compacts the JSON object with `jq -ce`;
2. extracts its `.text` field;
3. pipes the text to `classify.sh`;
4. receives one category label; and
5. merges the category into the original object.

This is a **one-record-in, one-record-out** operation. The original fields and ordering are preserved. Processing ten records causes ten classifier calls.

The script determines its own directory before locating `classify.sh`. It can therefore be invoked from another working directory without breaking the relative dependency.

## 4. `filter-category.sh` — retain a subset

Once records have stable categories, selecting a category is an exact operation. No additional model call is necessary.

`filter-category.sh` accepts one category argument and emits only matching records:

```sh
printf 'The server is unavailable.\nPlease add dark mode.\nThe login page crashes.\n' \
  | ./map-lines.sh \
  | ./filter-classify.sh \
  | ./filter-category.sh bug
```

For every input record, the output cardinality is either zero or one:

```text
matching record     → one output record
nonmatching record  → no output record
```

The script validates that every input value is an object with a string-valued `.category`. A malformed record causes `jq` and the pipeline to fail rather than silently disappearing.

This example illustrates an important design principle: use the model for semantic classification, then use conventional code for exact selection.

## 5. `filter-triage.sh` — a cognitive filter for JSON objects

`filter-triage.sh` demonstrates a filter whose model input is the complete JSON record. It validates each line, JSON-encodes the compact record, and puts it alone in the user message. The system message contains the triage instruction.

```sh
printf 'Login fails for every user.\nPlease add keyboard shortcuts.\n' \
  | ./map-lines.sh \
  | ./filter-triage.sh
```

The strict schema requires four fields from the model:

| Field | Allowed value |
|---|---|
| `category` | `bug`, `feature`, `question`, or `other` |
| `priority` | `low`, `medium`, or `high` |
| `summary` | string |
| `route` | `engineering`, `product`, `support`, or `manual-review` |

The result is merged into the original record:

```jsonl
{"id":1,"text":"Login fails for every user.","category":"bug","priority":"high","summary":"All users are unable to log in.","route":"engineering"}
```

This is also a one-record-in, one-record-out operation and makes one API request per record. Unlike `filter-classify.sh`, it shows the complete schema-constrained request directly in the loop.

## 6. `reduce-category-counts.sh` — deterministic reduction

A reducer consumes the complete JSONL sequence and emits one result. `reduce-category-counts.sh` calculates an exact aggregate, so it uses only `jq`.

```sh
printf 'The server is unavailable.\nPlease add dark mode.\nThe login page crashes.\n' \
  | ./map-lines.sh \
  | ./filter-classify.sh \
  | ./reduce-category-counts.sh
```

A possible result is:

```json
{
  "total": 3,
  "categories": {
    "bug": 2,
    "feature": 1
  }
}
```

`jq -s` slurps the individual input values into an array. The reducer validates that every item has a string-valued category, groups equal categories, and counts the members of each group.

Empty input has a well-defined result:

```json
{
  "total": 0,
  "categories": {}
}
```

Counting has one objectively correct answer. Using a language model for this reduction would add uncertainty without providing a benefit.

## 7. `reduce-report.sh` — cognitive reduction

Semantic reduction is different: identifying shared themes and proposing actions requires interpretation across records. `reduce-report.sh` therefore makes one schema-constrained model request for the entire sequence.

The included article provides a runnable example without additional data files:

```sh
./map-paragraphs.sh < article.txt \
  | ./reduce-report.sh
```

The reducer first uses `jq -s` to turn the JSONL sequence into one array. Empty input is rejected, and every array member must be an object. The array is then encoded as the user message.

The model response must contain:

- one `overall_summary` string;
- between one and five `common_themes`; and
- between one and five `recommended_actions`.

The script calculates `input_count` itself instead of asking the model to count. It then merges that deterministic value with the semantic result:

```json
{
  "input_count": 5,
  "overall_summary": "The records explain how map, filter, and reduce form composable JSONL pipelines.",
  "common_themes": [
    "Structured sequence processing",
    "Choosing deterministic or cognitive operations"
  ],
  "recommended_actions": [
    "Use JSONL as the interface between sequence stages",
    "Reserve model calls for semantic decisions"
  ]
}
```

The complete input must fit into memory and into the model context. This reducer is therefore intended for bounded teaching examples, not unlimited streams.

## An explicit loop with `summarize.sh`

`filter-classify.sh` hides its per-record orchestration inside a script. The following example exposes the same pattern and calls the chapter 01 summarizer for every paragraph in `article.txt`:

```sh
./map-paragraphs.sh < article.txt \
  | while IFS= read -r record; do
      id=$(jq '.id' <<<"$record")
      text=$(jq -r '.text' <<<"$record")
      summary=$(printf '%s\n' "$text" | ../01-cognitive-filters/summarize.sh)

      jq -cn --argjson id "$id" --arg summary "$summary" \
        '{id: $id, summary: $summary}'
    done
```

This loop performs the essential sequence-filter steps:

1. read one JSONL record;
2. extract the field needed by another cognitive filter;
3. call that filter;
4. construct one schema-shaped record; and
5. continue with the next line.

The result is another JSONL sequence, now containing paragraph summaries.

## Complete patterns

### Map → filter → reduce

```sh
printf 'Server unavailable.\nAdd dark mode.\nLogin crashes.\n' \
  | ./map-lines.sh \
  | ./filter-classify.sh \
  | ./reduce-category-counts.sh
```

### Map → cognitive filter → select → cognitive reduce

```sh
printf 'Server unavailable.\nAdd dark mode.\nLogin crashes.\n' \
  | ./map-lines.sh \
  | ./filter-triage.sh \
  | ./filter-category.sh bug \
  | ./reduce-report.sh
```

### Map → cognitive reduce

```sh
./map-paragraphs.sh < article.txt \
  | ./reduce-report.sh
```

## Choosing an operation

| Requirement | Appropriate stage |
|---|---|
| Split one input into independent records | Map |
| Add information to every record | Filter |
| Retain records matching an exact condition | Filter |
| Calculate one exact aggregate | Deterministic reduce |
| Synthesize meaning across all records | Cognitive reduce |

Use Bash and `jq` when the rule is exact. Use a language model when the operation depends on meaning or judgment. Keeping that boundary explicit makes a pipeline easier to understand, test, and reuse.

## Limits of the examples

The filters run sequentially and make one request at a time. The scripts do not implement parallel processing, retry policies, resumable jobs, or an agentic loop. The shell fixes the stages in advance; the model never chooses which script runs next.
