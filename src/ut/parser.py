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

def source_code_analysis_adv(file_path: str) -> tuple[str, list[dict]]:
    """Analyze a Python source file and extract import statements \
    and detailed information about each class and function. The key \
    difference from source_code_analysis is that this function also \
    extracts class definitions separately.

    Args:
        file_path: The path to the .py file to analyze.

    Returns:
        A tuple containing:
        - A string with all the import statements found.
        - A list of dictionaries for functions not belonging to classes, where each dictionary represents a function
        and contains its name, full source code, and the code of its parent class (if it exists).
        - A list of dictionaries for classes, where each dictionary contains the class name, the full definition, 
        and a list of its methods
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
    functions = []
    classes = []
    processed_classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_code = ast.unparse(node)
            method_list = []
            for class_node in node.body:
                if isinstance(class_node, ast.FunctionDef):
                    method_list.append(class_node.name)
            analysis = {
                "class_name": node.name,
                "class_code": class_code,
                "methods": method_list
            }
            classes.append(analysis)
            processed_classes.append(node.name)
        if isinstance(node, ast.FunctionDef):
            # If this function belongs to a class we have already processed, skip it
            parent = parent_map.get(node)
            if parent and isinstance(parent, ast.ClassDef) and parent.name in processed_classes:
                continue
            # ast.unparse(node) gives us the COMPLETE code of the function,
            # including the `def` signature, the arguments with their type hints,
            # the return type hint, and the docstring.
            function_code = ast.unparse(node)

            parent_class_code = None
            parent = parent_map.get(node)
            if parent and isinstance(parent, ast.ClassDef):
                print("ERROR: This should not happen")
                breakpoint()
                parent_class_code = ast.unparse(parent)

            analysis = {
                "function_name": node.name,
                "function_code": function_code,
            }
            functions.append(analysis)

    return imports_code, functions, classes

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

def get_function_imports(file_path, function_locs, class_locs):
    """Get all import statements for functions that will be tested

    Args:
        file_path (Path): The path to the top-level directory of the project.
        function_locs (dict): A mapping of function names to their file locations.
        class_locs (dict): A mapping of class names to their file locations.
    """
    function_imports = []
    # Right now we assume that the directory on which generate is called is the top-level module, and hence the imports should start with it
    for func_name, filename in function_locs.items():
        # import_path_start = filename.find(file_path.name) # Using this would be less elegant
        import_path = filename.relative_to(file_path)
        import_path_converted = str(import_path).replace('/', '.').replace('.py', '')
        function_imports.append("from " + import_path_converted + f" import {func_name}")
    for class_name, filename in class_locs.items():
        import_path = filename.relative_to(file_path)
        import_path_converted = str(import_path).replace('/', '.').replace('.py', '')
        function_imports.append("from " + import_path_converted + f" import {class_name}")
    return function_imports

def get_context_for_test_gen(test_plan, function_dict, class_dict) -> str:
    # Get the code for the required functions
    required_function_names = test_plan.get('functions_required', [])
    required_function_codes = [function_dict[func_name] for func_name in required_function_names if func_name in function_dict]
    # Warn if the name of a required function is not found in function_dict
    for func_name in required_function_names:
        if func_name not in function_dict:
            console.print(f"[yellow]Warning: Required function '{func_name}' not found in source code[/yellow]")
            verbose_log(f"    (functions available: {list(function_dict.keys())})")
    function_code_context = "\n".join(required_function_codes)

    # Get the code for the required classes
    required_class_names = test_plan.get('classes_required', [])
    required_class_codes = [class_dict[class_name]['code'] for class_name in required_class_names if class_name in class_dict]
    # Warn if the name of a required class is not found in class_dict
    for class_name in required_class_names:
        if class_name not in class_dict:
            console.print(f"[yellow]Warning: Required class '{class_name}' not found in source code[/yellow]")
            verbose_log(f"    (classes available: {list(class_dict.keys())})")
    function_code_context += "\n" + "\n".join(required_class_codes)
    return function_code_context

def extract_class_name(class_code: str) -> Optional[str]:
    """Extract the class name from the given class code.

    Args:
        class_code (str): The source code of the class.

    Returns:
        Optional[str]: The name of the class if found, otherwise None.
    """
    # First remove any line which starts with @ (decorators)
    lines = class_code.splitlines()
    cleaned_lines = [line for line in lines if not line.strip().startswith("@")]
    # Now look for the class definition line
    for line in cleaned_lines:
        line = line.strip()
        if line.startswith("class "):
            # Extract the class name
            class_name = line.split("(")[0].replace("class ", "").strip()
            return class_name
    return None

def extract_code(file_path: Path, ignore_list: list[str]):
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
    # Build a dictionary matching class names to their definitions and lists of functions
    class_dict = {}
    # Determine which files to pass to the planner
    files_for_planner = []
    for file in python_files:
        if file.name in ignore_list or any([dir in ignore_list for dir in file.parent.__str__().split('/')]):
            verbose_log(f"  → Ignoring {file.name}")
            continue
        try:
            imports_code, functions_data, classes_data = source_code_analysis_adv(str(file))
            for data in functions_data:
                function_locs[data["function_name"]] = file
                # if data["parent_class_code"] and len(data["parent_class_code"].strip()) > 0:
                #     # Extract the class name from the parent_class_code
                #     class_name = extract_class_name(data["parent_class_code"])
                #     if class_name:
                #         class_dict[class_name] = data["parent_class_code"]
                #     else:
                #         verbose_log(f"  → Warning: Could not extract class name from parent class code in function {data['function_name']} in file {file.name}")
                #     class_locs[class_name] = file
                function_dict[data["function_name"]] = data["function_code"]
            for class_data in classes_data:
                class_locs[class_data["class_name"]] = file
                class_dict[class_data["class_name"]] = {
                    "code": class_data["class_code"],
                    "methods": class_data["methods"]
                }
            if len(functions_data) > 0 or len(classes_data) > 0:
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
        console.print(
            f"[bold red]Error: No functions or classes found in {file_path.name}, so no tests can be generated.[/bold red]"
        )
        return
    
    console.print(f"[bold blue]Using code from {len(files_for_planner)} files with {len(all_function_names)} functions and {len(all_class_names)} classes[/bold blue]")

    # Combine extracted info into a single compact data structure
    func_and_class_info = {
        "functions": {
            name: {
                "location": function_locs[name],
                "code": function_dict[name]
            } for name in all_function_names
        },
        "classes": {
            name: {
                "location": class_locs[name],
                "code": class_dict[name]["code"],
                "methods": class_dict[name]["methods"]
            } for name in all_class_names
        }
    }

    return function_locs, class_locs, files_for_planner, function_dict, class_dict, func_and_class_info