# 00 — API Basics

This folder is an educational introduction to an OpenAI-compatible Chat Completions API. The scripts deliberately show the HTTP requests directly instead of hiding them behind a library or a larger utility.

The examples build on one another. They begin with a single chat request, add streaming and conversation context, introduce three levels of JSON output, and finish by combining image input with structured output.

## Learning objectives

After working through the scripts, you should understand:

- how to send a request to `/v1/chat/completions` with `curl`;
- how `model`, `messages`, `temperature`, `reasoning_effort`, and `stream` affect a request;
- how the `system`, `user`, and `assistant` roles form a conversation context;
- how plain prompting, JSON mode, and a strict JSON Schema differ;
- how to send a local image as a Base64 data URL;
- how vision input and structured output can be used together; and
- how `jq` can display either the complete response or only `choices[0].message`.

## Requirements

You need a POSIX-compatible shell plus these command-line programs:

- `curl`, for sending HTTP requests;
- `jq`, for formatting and selecting JSON; and
- `base64`, for encoding the image used by the vision examples.

Before running a script, define these environment variables:

```sh
export OPENAI_BASE_URL="http://localhost:11434"
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="your-model"
```

`OPENAI_BASE_URL` must be the server address without `/v1`, because every script appends `/v1/chat/completions`. The selected model must support vision for the final two examples.

Run the scripts from this directory so that the relative image path resolves correctly:

```sh
cd 00-api-basics
./chat.sh
```

## The common request structure

Every script sends an HTTP `POST` request with the same basic command:

```sh
curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @-
```

The `-d @-` option tells `curl` to read the request body from standard input. A here-document beginning with `<<EOF` supplies the JSON body directly inside each script.

All examples use the model named by `OPENAI_MODEL`, a temperature of `0.0`, and `reasoning_effort` set to `none`. These settings aim for direct, repeatable answers, provided that the chosen server and model support them.

Work through the following scripts in order.

## 1. `chat.sh` — a basic chat completion

`chat.sh` sends one fixed user message:

> Explain the Unix-Pipe in one single sentence with less than 16 words.

Its `messages` array contains one object with the `user` role. The request sets `stream` to `false`, so the server returns one complete response after generation finishes.

```sh
./chat.sh
```

The response is piped through `jq` without a filter. Consequently, this example prints the complete response object, including the generated message and any metadata supplied by the server.

## 2. `chat-stream.sh` — receiving a streamed response

`chat-stream.sh` asks the same question as `chat.sh`, but sets:

```json
"stream": true
```

```sh
./chat-stream.sh
```

Instead of waiting for one complete JSON response, a compatible server sends a sequence of streaming events as generation progresses. This script prints that stream exactly as `curl` receives it. It does not pipe the events through `jq`, join the fragments, or extract only the generated text. This makes the wire format visible for study.

## 3. `context.sh` — building conversation context

`context.sh` demonstrates how several messages provide context to a model. Its `messages` array contains, in order:

1. a `system` message requiring answers shorter than 16 words;
2. a `user` question about Unix pipes;
3. an earlier `assistant` answer; and
4. a new `user` question about a “cognitive pipe.”

```sh
./context.sh
```

The model receives the complete array with every request. The earlier assistant response is therefore part of the input, allowing the final question to refer to the preceding exchange. The API does not reconstruct this history from earlier script executions; the client must include the desired context in `messages`.

Like `chat.sh`, this script uses `jq` without a filter and displays the complete response object.

## 4. `forms-json_.sh` — requesting JSON with a prompt

`forms-json_.sh` asks the model to translate “I love programming.” into Spanish and Italian. The system message also tells the model to generate JSON.

```sh
./forms-json_.sh
```

This is prompt-only JSON generation: the request does not use `response_format`. The model is instructed to produce JSON, but the API request does not formally constrain the shape of that JSON.

The command ends with:

```sh
jq '.choices[0].message'
```

This selects the message object from the first generated choice instead of displaying the entire API response. Its `content` field still contains the model's response, commonly as JSON encoded inside a string.

## 5. `forms-json_object.sh` — enabling JSON object mode

`forms-json_object.sh` uses the same translation task and adds:

```json
"response_format": {
  "type": "json_object"
}
```

```sh
./forms-json_object.sh
```

This asks a compatible API to return a valid JSON object. It is stronger than relying only on the prompt, but it still does not define required property names or value types. The instructions in the messages remain responsible for describing the desired Spanish and Italian fields.

The script selects `.choices[0].message` with `jq`.

## 6. `forms-json_schema.sh` — defining an exact JSON shape

`forms-json_schema.sh` progresses from JSON object mode to a strict JSON Schema:

```json
{
  "type": "object",
  "properties": {
    "spanish": { "type": "string" },
    "italian": { "type": "string" }
  },
  "required": ["spanish", "italian"]
}
```

```sh
./forms-json_schema.sh
```

The root value must be an object. Both `spanish` and `italian` must be present, and both values must be strings. The surrounding `strict: true` asks the compatible API to enforce this schema during generation.

This is the most precise of the three forms examples:

```text
prompt only → valid JSON object → schema-constrained JSON
```

The script again displays `.choices[0].message`.

## 7. `vision.sh` — combining text and an image

`vision.sh` reads the local file:

```text
images/t-penguin-BJHESX8uBS8-unsplash.jpg
```

The file was taken from https://unsplash.com/de/fotos/mann-der-an-einem-uberfullten-schreibtisch-mit-einem-computer-arbeitet-BJHESX8uBS8

The shell encodes the file as Base64 and removes line breaks:

```sh
base64_image=$(base64 < "$image_path" | tr -d '\n')
```

It then embeds the result in a data URL inside an `image_url` content part. Unlike the earlier messages, this user message has an array for `content` containing two parts:

- a text instruction asking the model to explain what is in the image; and
- the Base64-encoded image.

```sh
./vision.sh
```

The system message limits the answer to fewer than 16 words. This example requires a model and API server that support image input. It displays `.choices[0].message`.

Although the source file has a `.jpg` extension, the script labels its data URL as `image/png`. The example documents the request exactly as it currently appears in the script.

## 8. `vision-forms.sh` — structured vision output

`vision-forms.sh` combines the previous two ideas: it sends the same Base64-encoded image to a vision model and constrains the response with a strict JSON Schema.

The prompt is:

> list 10 objects that are important to the man

The response schema describes a root-level array whose items are strings:

```json
{
  "type": "array",
  "items": { "type": "string" },
  "minItems": 10,
  "maxItems": 10
}
```

```sh
./vision-forms.sh
```

Because both limits are 10, a compatible API must generate exactly ten strings. The script displays the first choice's message object with `.choices[0].message`.

As in `vision.sh`, the current data URL declares `image/png` while reading the `.jpg` image in the `images` directory.

## What to compare while learning

Run the scripts in sequence and inspect their request bodies. Pay particular attention to these changes:

1. `stream` changes a single completed response into a sequence of events.
2. Additional message roles turn an isolated prompt into a conversation context.
3. `response_format` progresses from no constraint, to a JSON object, to an exact schema.
4. An array-valued message `content` can combine text and image parts.
5. Vision input and JSON Schema can coexist in one request.

These scripts favor visibility over production-level robustness. They use fixed prompts and a fixed image, and they expose API structures so students can see what is sent and returned.
