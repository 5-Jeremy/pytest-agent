"""Automated Unit Test Generation CLI with AI."""
import os

from dotenv import load_dotenv
import subprocess

load_dotenv()


def generate_test_code(prompt: str) -> str:
    """Generate test code for a given function.

    Args:
        prompt (str): The prompt containing the function code and context.

    Returns:
        str: The generated test code.
    """
    # TODO: Add error handling, including timeout, connection errors, bad API key, etc.
    response = subprocess.run(f"llm $\'{prompt}\'", shell=True, capture_output=True, text=True)
    assert response.returncode == 0, f"LLM query failed: {response.stderr}"
    return response.stdout
