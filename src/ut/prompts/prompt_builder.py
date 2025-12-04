"""Automated Unit Test Generation CLI with AI."""
from ut.constants import FILE_PATH_PROMPT
from ut.prompts.coder_prompts import INSTRUCTION_PROMPT_FIRST_ATTEMPT, INSTRUCTION_PROMPT_AFTER_LINT_FAIL, INSTRUCTION_PROMPT_AFTER_TEST_FAIL

def _load_prompt(prompt_file):
    try:
        full_path = f"{FILE_PATH_PROMPT}/{prompt_file}"
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Prompt file not found: {full_path}")
        exit(1)

def generate_planner_prompt(package_code: str, template_path: str) -> str:
    instructions_prompt = _load_prompt(template_path)
    prompt = instructions_prompt + "\nFull code:\n" + package_code
    return prompt

def generate_coder_prompt(
    function_code: str,
    test_plan: str,
) -> str:
    prompt = INSTRUCTION_PROMPT_FIRST_ATTEMPT.format(
        function_code=function_code,
        test_plan=test_plan,
    )
    return prompt

def generate_coder_revision_prompt(
    function_code: str,
    test_plan: str,
    prev_attempt_code: str,
    type_of_revision: str,
    feedback_message: str,
) -> str:
    if type_of_revision == "lint":
        prompt = INSTRUCTION_PROMPT_AFTER_LINT_FAIL.format(
            test_code=prev_attempt_code,
            lint_message=feedback_message,
            test_plan=test_plan,
            function_code=function_code,)
    elif type_of_revision == "test_fail":
        prompt = INSTRUCTION_PROMPT_AFTER_TEST_FAIL.format(
            test_code=prev_attempt_code,
            pytest_message=feedback_message,
            test_plan=test_plan,
            function_code=function_code,)
    else:
        raise ValueError(f"Unknown type of revision: {type_of_revision}")
    return prompt

### Old prompts from the original repository
def generate_class_method_prompt(
    imports_code: str,
    function_name: str,
    parent_class_code: str,
) -> str:
    """Generate prompt for class method testing."""

    prompt_template = _load_prompt("generate_unittest_class.txt")
    prompt = prompt_template.replace("{{imports_code}}", imports_code)
    prompt = prompt.replace("{{function_name}}", function_name)
    prompt = prompt.replace("{{parent_class_code}}", parent_class_code)
    return prompt

def generate_standalone_prompt(imports_code: str, function_code: str) -> str:
    """Generate prompt for standalone function testing."""

    prompt_template = _load_prompt("generate_unittest_standalone.txt")
    prompt = prompt_template.replace("{{imports_code}}", imports_code)
    prompt = prompt_template.replace("{{function_code}}", function_code)
    return prompt
