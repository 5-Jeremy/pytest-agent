"""Parser for pytest output to extract test results."""

import re
from typing import Dict


def parse_pytest_output(pytest_output: str) -> Dict[str, str]:
    """
    Parse pytest output and return a dictionary mapping test function names to results.
    
    Args:
        pytest_output: String output from pytest command
        
    Returns:
        Dictionary mapping test function names to their results ('PASSED' or 'FAILED')
        
    Example:
        >>> output = '''
        ... tests/test_convert_date_to_iso.py::test_convert_date_to_iso PASSED       [ 11%]
        ... tests/test_convert_date_to_iso.py::test_convert_date_to_iso_different_format PASSED [ 22%]
        ... '''
        >>> parse_pytest_output(output)
        {'test_convert_date_to_iso': 'PASSED', 'test_convert_date_to_iso_different_format': 'PASSED'}
    """
    results = {}
    feedback = {}

    # Check for an error preventing the tests from running; if this happens, nothing can be extracted
    # on a per-test basis (the error that caused this could be used as feedback but currently is not)
    if "__________________ ERROR collecting" in pytest_output:
        return results, feedback

    pass_fail_part = pytest_output.split('=================================== FAILURES ===================================')[0]
    error_summary_part = pytest_output.split('=================================== FAILURES ===================================')[1].split('=============================== warnings summary ===============================')[0]

    # Pattern to match test result lines
    # Format: path/to/file.py::test_function_name PASSED/FAILED [percentage]
    pass_fail_pattern = r'^(.+?)::(\w+)\s+(PASSED|FAILED)'
    
    for line in pass_fail_part.split('\n'):
        match = re.match(pass_fail_pattern, line.strip())
        if match:
            # Extract test function name and result
            test_function = match.group(2)
            result = match.group(3)
            results[test_function] = result

    # Pattern to match error summary lines
    # Each summary begins with _____________________ test_xxx ______________________
    summary_header_pattern = r"_{5,}\s*(.*?)\s*_{5,}"

    # Find all section headers and their positions
    matches = list(re.finditer(summary_header_pattern, error_summary_part))

    for i, m in enumerate(matches):
        name = m.group(1).strip()             # the captured name
        start = m.end()                       # start of this section's text
        end = matches[i+1].start() if i+1 < len(matches) else len(error_summary_part)
        text = error_summary_part[start:end].strip()
        feedback[name] = text
    
    return results, feedback
