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
    
    # Pattern to match test result lines
    # Format: path/to/file.py::test_function_name PASSED/FAILED [percentage]
    pattern = r'^(.+?)::(\w+)\s+(PASSED|FAILED)'
    
    for line in pytest_output.split('\n'):
        match = re.match(pattern, line.strip())
        if match:
            # Extract test function name and result
            test_function = match.group(2)
            result = match.group(3)
            results[test_function] = result
    
    return results
