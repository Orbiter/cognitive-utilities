#!/usr/bin/env python3
# interactive terminal chat that sends the complete history with every request
# usage: python3 chat-terminal.py

import os, json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SYSTEM_PROMPT = "You are a helpful assistant. Respond with short sentences."

def chat_request(messages):
    env = os.environ
    data = json.dumps({
        "model": env["OPENAI_MODEL"], "temperature": float(env["OPENAI_TEMPERATURE"]),
        "reasoning_effort": env["OPENAI_REASONING_EFFORT"], "stream": False,
        "messages": messages,
    }).encode()
    request = Request(f'{env["OPENAI_BASE_URL"]}/v1/chat/completions', data, {
        "Authorization": f'Bearer {env["OPENAI_API_KEY"]}',
        "Content-Type": "application/json"})

    try:
        with urlopen(request) as response:
            return json.load(response)["choices"][0]["message"]["content"]
    except HTTPError as error:
        body = error.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error


def main():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("Terminal-Chat (Beenden mit 'exit', 'quit' oder 'ende')\n")

    while True:
        try:
            prompt = input("Prompt: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt: continue
        if prompt.casefold() in {"exit", "quit", "ende"}: break

        # here we extend the context
        messages.append({"role": "user", "content": prompt})
        try:
            answer = chat_request(messages)
        except (OSError, RuntimeError, KeyError, ValueError, json.JSONDecodeError) as error:
            messages.pop()
            print(f"\nFehler: {error}\n")
            continue

        print(f"\nAntwort: {answer}\n")
        messages.append({"role": "assistant", "content": answer})

if __name__ == "__main__":
    main()
