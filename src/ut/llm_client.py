"""Functions for getting output from LLMs and processing it."""

from dotenv import load_dotenv
import subprocess, requests
import llm
from openai import OpenAI

from ut.cli.commands.helper import verbose_log
import json
from typing import Iterator, Tuple, Any

import math, asyncio, httpx

load_dotenv()

# Function used to do inference with the planner model
def generate_test_plan(prompt: str) -> str:
    """Generate test plan for a python project.

    Args:
        prompt (str): The prompt constructed.

    Returns:
        str: The generated test code.
    """
    model = llm.get_model("TAMUS AI Chat (chat.tamu.ai): protected.gpt-4.1") # TODO: This assumes that TAMU AI is used
    try:
        response = model.prompt(prompt).text()
    except Exception as e:
        print(f"Error occurred: {e}")
        return None

    return response

# Function used to do inference with the planner model (outdated)
def generate_test_plan_cli(prompt: str) -> str:
    """Generate test plan for a python project.

    Args:
        prompt (str): The prompt constructed.

    Returns:
        str: The generated test code.
    """
    # TODO: Add error handling, including timeout, connection errors, bad API key, etc.
    response = subprocess.run(f"llm $\'{prompt}\'", shell=True, capture_output=True, text=True)
    assert response.returncode == 0, f"LLM query failed: {response.stderr}"
    # Example error: response.stdout looks like 🚫 **Unexpected Error**\n\nAn unexpected error occurred: 400: 🚫 **None**\n\n{'error': '/chat/completions: Invalid model name passed in model=gpt-4o. Call `/v1/models` to view available models for your key.'}\n\n*Error Code: 400*
    # The previous assert does not seem to trigger for this error, so we check manually
    assert "Error Code: 400" not in response.stdout, f"LLM query failed: {response.stdout}"
    return response.stdout

def is_vllm_running(host="http://127.0.0.1", port=8000):
    url = f"{host}:{port}/health"  # vLLM exposes /health or /version endpoints
    try:
        response = requests.get(url, timeout=1)
        return response.status_code == 200
    except requests.ConnectionError:
        return False
    except requests.Timeout:
        return False

SERVERS = [
    "http://localhost:8000",
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003",
]
MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
MAX_CONCURRENT_PER_SERVER = 8
TIMEOUT_SECONDS = 60.0

async def send_one(client: httpx.AsyncClient, server_url: str, prompt: str, temperature: float = 0.0) -> str:
        url = f"{server_url}/v1/chat/completions"
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 1024,
        }
        resp = await client.post(url, json=payload, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

async def generate_test_cases_batched(prompts: dict, temperature: float = 0.0) -> dict:
    # TODO: These are hardcoded for now, make them configurable later
    num_servers = 4
    n = len(prompts)
    chunk_size = math.ceil(n / num_servers)
    results = [None] * n

    prompts_batch = list(prompts.values())

    async with httpx.AsyncClient() as client:
        async def run_on_one_server(server_idx: int, start: int, end: int):
            sem = asyncio.Semaphore(MAX_CONCURRENT_PER_SERVER)
            tasks = []
            for i in range(start, end):
                async def worker(i=i):
                    async with sem:
                        try:
                            text = await send_one(client, SERVERS[server_idx], prompts_batch[i], temperature=temperature)
                        except Exception as e:
                            text = f"ERROR: {e!r}"
                        results[i] = text
                tasks.append(asyncio.create_task(worker()))
            await asyncio.gather(*tasks)

        all_tasks = []
        for server_idx in range(num_servers):
            start = server_idx * chunk_size
            end = min(start + chunk_size, n)
            if start >= n:
                break
            all_tasks.append(run_on_one_server(server_idx, start, end))

        await asyncio.gather(*all_tasks)

    # Map back to test names
    results_dict = {}
    for test_name, result in zip(prompts.keys(), results):
        results_dict[test_name] = result

    return results_dict

# Function used to do inference with the test case generator model (hosted locally using vllm)
def generate_test_case(prompt: str, port: int = 8000, model: str = "Qwen/Qwen2.5-Coder-32B-Instruct") -> str:
    """Generate test cases for a given function.

    Args:
        prompt (str): The prompt containing the function code and context.

    Returns:
        str: The generated test cases.
    """
    if not is_vllm_running(port=port):
        raise RuntimeError(f"vLLM server is not running on port {port}. Please start the server before generating test cases.")
    client = OpenAI(
        # defaults to os.environ.get("OPENAI_API_KEY")
        api_key="EMPTY",
        base_url=f"http://localhost:{port}/v1",
    )
    completion = client.completions.create(
        model=model,
        prompt=prompt,
        echo=False,
        stream=False,
        max_tokens=512,
    )
    return completion.choices[0].text

def parse_test_case_plan_old(raw_plan: str):
    # Parse the response to get test plans for each function
    # Assume the response contains sections like:
    # **Test Case: `test_name`**
    #     - *Functions required:* function_a, function_b, ...
    #     - *Description:*
    # We want to extract the test case name, functions required, and description for each test case, and turn it into a dictionary where the key is the test case name and the value contains the other elements
    test_case_plans = {}
    
    # Parse the raw response to extract test case plans
    import re
    
    # Split by test case headers (numbered list with "Test Case:" pattern)
    test_case_pattern = r'\d+\.\s+\*\*Test Case:\s+`([^`]+)`\*\*'
    description_pattern = r'-\s+\*Description:\*\s+(.+?)$'
    
    test_cases = re.finditer(test_case_pattern, raw_plan)
    
    for match in test_cases:
        test_name = match.group(1)
        start_pos = match.end()
        
        # Find the description for this test case (single line only)
        desc_match = re.search(description_pattern, raw_plan[start_pos:], re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()
            test_case_plans[test_name] = description
            # verbose_log(f"  → Extracted test plan: {test_name}")

    return test_case_plans

def extract_json_objects(text: str, *, only_objects: bool = True
                        ) -> Iterator[Tuple[Any, Tuple[int, int]]]:
    """
    Scan `text` and yield (parsed_json, (start, end)) for each valid JSON value found.
    If only_objects=True, restrict to JSON objects (i.e., {...}) and skip arrays, strings, etc.
    """
    dec = json.JSONDecoder()
    i, n = 0, len(text)

    # Pre-scan to candidate starts for speed ( '{' if only_objects else any JSON starter )
    starters = ('{',) if only_objects else ('{', '[', '"', 't', 'f', 'n') + tuple('0123456789-')
    next_candidate = lambda s, idx: min((s.find(c, idx) for c in starters if s.find(c, idx) != -1), default=-1)

    while i < n:
        i = next_candidate(text, i)
        if i == -1:
            break
        try:
            value, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue

        # Enforce object-only if requested
        if not only_objects or isinstance(value, dict):
            yield value, (i, end)

        i = end  # continue scanning after this parsed value

def parse_test_case_plan_json(raw_plan: str):
    # Parse the response to get test plans for each function
    # The raw plan should contain at least one JSON object

    json_objects = list(extract_json_objects(raw_plan))

    if not json_objects:
        return {}

    test_case_plans = {}
    for obj, (start, end) in json_objects:
        for test_case_name in obj:
            test_case_plans[test_case_name] = obj[test_case_name]
            # verbose_log(f"  → Extracted test plan: {test_case_name}")

    return test_case_plans
