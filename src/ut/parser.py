"""Automated Unit Test Generation CLI with AI."""
import ast
from pathlib import Path
from typing import Optional
from ut.cli.commands.helper import verbose_log
from rich.console import Console

console = Console()

def source_code_analysis(file_path: str) -> tuple[str, list[dict]]:
    """Analyze a Python source file and extract import statements \
    and detailed information about each function.

    Args:
        file_path: The path to the .py file to analyze.

    Returns:
        A tuple containing:
        - A string with all the import statements found.
        - A list of dictionaries, where each dictionary represents a function
        and contains its name, full source code,
        and the code of its parent class (if it exists).
    """

    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    tree = ast.parse(source_code)

    # --- Step 1: Extract all imports ---
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # ast.unparse converts a node back to source code.
            # This is much more robust than handling line numbers.
            imports.append(ast.unparse(node))

    imports_code = "\n".join(imports)

    # --- Preparation for finding parent classes ---
    # ast does not keep references to parent nodes, so we create them ourselves
    # to be able to look up the tree from a function.
    parent_map = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    # --- Step 2 and 3: Extract functions, docstrings, type hints and parent classes ---
    functions_analysis = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # ast.unparse(node) gives us the COMPLETE code of the function,
            # including the `def` signature, the arguments with their type hints,
            # the return type hint, and the docstring.
            function_code = ast.unparse(node)

            parent_class_code = None
            parent = parent_map.get(node)
            if parent and isinstance(parent, ast.ClassDef):
                parent_class_code = ast.unparse(parent)

            analysis = {
                "function_name": node.name,
                "function_code": function_code,
                "parent_class_code": parent_class_code,
            }
            functions_analysis.append(analysis)

    return imports_code, functions_analysis


def calculate_import_path_simple(file_path: Path) -> str:
    """Generate a reasonable import path for the module.

    Users will need to adjust this in their actual test files.

    Args:
        file_path (Path): The path to the file for which to generate the import path.

    Returns:
        str: The calculated import path.
    """

    # Try to make a reasonable guess at the import path
    parts: list[str] = []
    current = file_path.parent

    # Walk up until we find a reasonable root (has __init__.py or is a common root)
    while current.name and (current / "__init__.py").exists():
        parts.insert(0, current.name)
        current = current.parent

    # Add the module name
    parts.append(file_path.stem)

    # If we found no package structure, just use the module name
    if len(parts) == 1:
        return file_path.stem

    return ".".join(parts)

def extract_code(file_path: Path, ignore_list: list[str], verbose: Optional[bool] = False):
    # Determine which files contain python source code (assume there is no existing directory for pytest tests)
    python_files = list(file_path.rglob("*.py")) if file_path.is_dir() else ([file_path] if file_path.suffix == ".py" else [])
    if len(python_files) == 0:
        console.print(f"[bold red]Error: No Python files found in {file_path}[/bold red]")
        return
    # Build an index for which functions and classes are defined in which files
    function_locs = {}
    class_locs = {}
    # Build a dictionary matching function names to their definitions
    function_dict = {}
    # Determine which files to pass to the planner
    files_for_planner = []
    for file in python_files:
        if file.name in ignore_list or any([dir in ignore_list for dir in file.parent.__str__().split('/')]):
            verbose_log(f"  → Ignoring {file.name}", verbose)
            continue
        # source_code_analysis returns a string with all the import statements and a list of dictionaries (one for each function)
        # Each dictionary contains the function_name, function_code, and parent_class_code (if it exists)
        try:
            imports_code, functions_data = source_code_analysis(str(file))
            for data in functions_data:
                function_locs[data["function_name"]] = file
                if "class_name" in data:
                    class_locs[data["class_name"]] = file
                # TODO: May need to extract the parent class info as well
                function_dict[data["function_name"]] = data["function_code"]
            if len(functions_data) > 0:
                files_for_planner.append(file)
        except Exception as e:
            console.print(f"[red]Failed to analyze {file.name}: {e} \n unit tests will not be generated for functions in this file [/red]")
            continue

    # Make sure there are no duplicate function/class names across files
    all_function_names = list(function_locs.keys())
    all_class_names = list(class_locs.keys())
    if len(all_function_names) != len(set(all_function_names)):
        console.print(f"[bold red]Error: Duplicate function names found across files. Please ensure all function names are unique for collaboration mode.[/bold red]")
        return
    if len(all_class_names) != len(set(all_class_names)):
        console.print(f"[bold red]Error: Duplicate class names found across files. Please ensure all class names are unique for collaboration mode.[/bold red]")
        return

    if len(all_function_names) == 0 and len(all_class_names) == 0:
        if verbose:
            console.print(
                f"[bold red]Error: No functions or classes found in {file_path.name}, so no tests can be generated.[/bold red]"
            )
        return
    
    console.print(f"[bold blue]Using code from {len(files_for_planner)} files with {len(all_function_names)} functions and {len(all_class_names)} classes[/bold blue]")
    return function_locs, class_locs, files_for_planner, function_dict