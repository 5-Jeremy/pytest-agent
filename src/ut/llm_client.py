"""Automated Unit Test Generation CLI with AI."""

from dotenv import load_dotenv
import subprocess, requests
from openai import OpenAI

load_dotenv()

# Function used to do inference with the planner model
def generate_test_plan(prompt: str) -> str:
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