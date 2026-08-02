# simple chat request, no streaming
# usage: python3 chat.py

import os, json
from urllib.request import Request, urlopen

env = os.environ
data = json.dumps({
    "model": env["OPENAI_MODEL"], "temperature": float(env["OPENAI_TEMPERATURE"]),
    "reasoning_effort": env["OPENAI_REASONING_EFFORT"], "stream": False,
    "messages": [
        {"role": "user", "content":
        "Explain the Unix-Pipe in one single sentence with less than 16 words."}],
}).encode()

request = Request(f'{env["OPENAI_BASE_URL"]}/v1/chat/completions', data, {
    "Authorization": f'Bearer {env["OPENAI_API_KEY"]}',
    "Content-Type": "application/json"})

with urlopen(request) as response:
    print(json.dumps(json.load(response), indent=2, ensure_ascii=False))
