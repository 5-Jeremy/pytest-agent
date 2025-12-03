""" These functions are used to screen generated tests to avoid instant crashes when running the test suite. """

import subprocess
from ut.cli.commands.helper import verbose_log

def lint_test_case(test_code: str) -> bool:
    """Lint the given test code using ruff (see pyproject.toml for configuration).
    
    Args:
        test_code (str): The test code to lint. This will be written to a temporary file.
    Returns:
        bool: True if the test code passes linting, False otherwise.
        str: The linter error message if any.
    """
    with open("temp_test_case.py", "w") as f:
        f.write(test_code)
    try:
        result = subprocess.run(
            ["ruff", "check", "temp_test_case.py"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, None
        else:
            return False, result.stdout + result.stderr
    finally:
        rm_result = subprocess.run(["rm", "temp_test_case.py"])
        if rm_result.returncode != 0:
            verbose_log("Warning: Failed to remove temporary test case file.")