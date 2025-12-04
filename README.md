# Automated Unit Test Generation CLI with AI

Unittest AI Agent is a Python tool that automatically generates comprehensive unit tests for your Python functions and classes using OpenAI's GPT models. It analyzes your source code, prepares context-rich prompts, and writes robust pytest-based test suites.

## Features

- **Automatic Source Analysis:** Extracts imports, functions, and class context from your Python files.
- **Prompt Engineering:** Uses customizable prompt templates for both standalone functions and class methods.
- **LLM Integration:** Sends code context to OpenAI GPT-4o to generate high-quality unit tests.
- **Test Postprocessing:** Cleans and adapts generated code for your project structure.
- **Test Writing:** Saves generated tests to the appropriate directory.

## Setup

0. **Requirements:**
   - Python 3.9 or higher
   - OpenAI API key
   - Poetry `curl -sSL https://install.python-poetry.org | python3`

1. **Install dependencies:**
   ```sh
   poetry install
   ```

2. **Setup llm to use TAMUS AI Chat:**
   - Save your API key
     ```sh
     llm keys set chat.tamu.ai <key>
     ```
   - ```source llm_setup_model.sh```

3. **Build the Docker image for the code under evaluation**
   - If copying the code to test directly into the container image: ```docker build -t unittest:example -f eval_dockerfiles/Dockerfile .```
   - If using a volume mount:

4.  **Start the VLLM server**

Simple sequential version:
```sh
vllm serve Qwen/Qwen2.5-Coder-32B-Instruct
```
Fully parallel version utilizing multiple GPUs (hardcoded to use Qwen/Qwen2.5-Coder-32B-Instruct):
```sh
bash start_vllm_servers.sh <num_GPUS>
```
## Generating tests

**Run the test generator:**
Inside the unittest-ai-agent directory:
```sh
poetry run ut generate example/converter.py
```

This will analyze `ut/example/converter.py` and generate tests in `ut/example/tests/`.

## Executing tests
```sh
python src/ut/test_runner.py
```

### Customization

- **Prompt Templates:** Edit files in `ut/prompts/` to change how prompts are constructed for the LLM.

### Example

Given a function like:

```python
def convert_date_to_iso(date_str: str, format: str = "%d/%m/%Y") -> str:
    ...
```

The agent will generate a suite of pytest tests covering various edge cases and save them to `ut_output/test_convert.py`.

