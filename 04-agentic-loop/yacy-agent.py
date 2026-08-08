#!/usr/bin/env python3
"""Interactive RAG chat backed by a local YaCy search engine."""

import http.client
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


MAX_ITERATIONS = 10
YACY_SEARCH_URL = os.environ.get(
    "YACY_SEARCH_URL", "http://127.0.0.1:8090/yacysearch.json"
)

SYSTEM_PROMPT = """Answer questions using documents from a local YaCy search
engine. The yacy_search tool is available to you. Use it for questions that
require knowledge from documents or current sources. You may and should search
more than once when the results are insufficient. Use different, more suitable,
or more specific search terms for subsequent searches. Base factual claims on
the returned results and cite their URLs. Do not claim that a source says
anything not supported by its title and description. If YaCy returns no useful
results, state clearly that the local data is insufficient for a reliable
answer. When using search results, end the answer with a "Sources" heading and
list the URLs actually used from the tool results. Never invent URLs. Once you
have enough information, answer without another tool call."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "yacy_search",
            "description": (
                "Search the local YaCy index for keywords. "
                "Separate multiple keywords with spaces."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": (
                            "Space-separated search query, for example "
                            "web server security guidance"
                        ),
                    }
                },
                "required": ["q"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]


def yacy_search(q):
    """Search only the local YaCy index."""
    q = q.strip()
    if not q:
        return json.dumps(
            {"error": "The search query q must not be empty.", "results": []}
        )

    parameters = {
        "query": q,
        "resource": "local",
        "maximumRecords": 5,
        "verify": "cacheonly",
        "contentdom": "text",
        "nav": "none",
    }
    url = f"{YACY_SEARCH_URL}?{urlencode(parameters)}"
    try:
        with urlopen(url, timeout=30) as response:
            yacy_response = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            yacy_error = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            yacy_error = None
        message = f"YaCy returned HTTP {error.code}."
        if isinstance(yacy_error, dict) and yacy_error.get("error"):
            message = yacy_error["error"]
        content = {"error": message, "results": []}
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        content = {"error": f"YaCy is unavailable: {error}", "results": []}
    else:
        channels = yacy_response.get("channels") or []
        items = channels[0].get("items", []) if channels else []
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "description": item.get("description", ""),
            }
            for item in items[:5]
        ]
        content = {"q": q, "result_count": len(results), "results": results}

    results = content.get("results", [])
    print(f"YaCy results: {len(results)}")
    for result in results:
        print(f"- {result.get('title') or '(untitled)'}")
        print(f"  {result.get('url')}")
    print(flush=True)

    return json.dumps(content, ensure_ascii=False)


def chat_request(messages):
    base_url = urlsplit(os.environ["OPENAI_BASE_URL"])
    if base_url.scheme not in {"http", "https"} or not base_url.hostname:
        raise RuntimeError("OPENAI_BASE_URL is not a valid HTTP(S) URL.")

    payload = {
        "model": os.environ["OPENAI_MODEL"],
        "temperature": float(os.environ["OPENAI_TEMPERATURE"]),
        "reasoning_effort": os.environ["OPENAI_REASONING_EFFORT"],
        "max_tokens": 2048,
        "stream": False,
        "messages": messages,
        "tools": TOOLS,
    }
    path = f"{base_url.path.rstrip('/')}/v1/chat/completions"
    connection_class = (
        http.client.HTTPSConnection
        if base_url.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_class(base_url.hostname, base_url.port, timeout=600)
    try:
        connection.request(
            "POST",
            path,
            json.dumps(payload),
            {
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        response_text = response.read().decode()
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}: {response_text}")
        return json.loads(response_text)["choices"][0]["message"]
    finally:
        connection.close()


def agentic_loop(conversation, prompt):
    working_context = conversation + [{"role": "user", "content": prompt}]

    for _ in range(MAX_ITERATIONS):
        answer = chat_request(working_context)
        tool_calls = answer.get("tool_calls") or []
        if not tool_calls:
            return answer.get("content") or ""
        if answer.get("content"):
            print(answer["content"], flush=True)
        working_context.append(answer)

        for tool_call in tool_calls:
            name = tool_call.get("function", {}).get("name")
            try:
                arguments = json.loads(
                    tool_call.get("function", {}).get("arguments", "{}")
                )
                if name != "yacy_search":
                    result = json.dumps(
                        {"error": f"Unknown tool: {name}"}, ensure_ascii=False
                    )
                else:
                    q = arguments.get("q", "")
                    print(f"\nSearching for: {q}", flush=True)
                    result = yacy_search(q)
            except (json.JSONDecodeError, TypeError) as error:
                result = json.dumps(
                    {"error": f"Invalid tool arguments: {error}"},
                    ensure_ascii=False,
                )

            working_context.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": name,
                    "content": result,
                }
            )

    raise RuntimeError(
        f"The agentic loop stopped after {MAX_ITERATIONS} iterations."
    )


def main():
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            prompt = input("Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt:
            continue
        if prompt.casefold() in {"exit", "quit"}:
            break

        try:
            answer = agentic_loop(conversation, prompt)
            print(f"\n{answer}\n")
            # Keep only the question and final answer for the next turn.
            # Tool calls and results remain in the temporary working context.
            conversation.extend(
                [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": answer},
                ]
            )
        except (
            OSError,
            RuntimeError,
            KeyError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"\nError: {error}\n")


if __name__ == "__main__":
    main()
