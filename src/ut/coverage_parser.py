import json
from pathlib import Path
from typing import Dict, List


def parse_coverage_missing_lines(json_path: str) -> Dict[str, List[int]]:
    """
    Parse a coverage JSON file and identify which functions have missing lines.
    
    Args:
        json_path: Path to the coverage JSON file
        
    Returns:
        A dictionary where keys are function names (in format "file::function")
        and values are lists of missing line numbers
    """
    with open(json_path, 'r') as f:
        coverage_data = json.load(f)
    
    result = {}
    
    # Iterate through all files in the coverage report
    files = coverage_data.get('files', {})
    for file_path, file_data in files.items():
        functions = file_data.get('functions', {})
        
        # Iterate through all functions in each file
        for function_name, function_data in functions.items():
            missing_lines = function_data.get('missing_lines', [])
            
            # Only include functions that have missing lines
            if missing_lines:
                # Create a qualified name for the function
                if function_name:  # Non-empty function name
                    qualified_name = f"{file_path}::{function_name}"
                else:  # Empty string means module-level code
                    qualified_name = f"{file_path}::<module>"
                
                result[qualified_name] = missing_lines
    
    return result


if __name__ == "__main__":
    # Example usage
    json_path = "/data1/jcarleton/unittest-ai-agent/agent_workspace/cov.json"
    missing_lines = parse_coverage_missing_lines(json_path)
    
    print("Functions with missing coverage:")
    print("=" * 80)
    for function, lines in missing_lines.items():
        print(f"\n{function}")
        print(f"  Missing lines: {lines}")
    
    if not missing_lines:
        print("\nNo functions with missing lines found!")
