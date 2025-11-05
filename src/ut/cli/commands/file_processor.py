"""Automated Unit Test Generation CLI with AI."""
from pathlib import Path
from typing import Optional
from datetime import datetime

from rich.console import Console

from ut.cli.commands.constants import DEF_TEST_STRING
from ut.cli.commands.helper import verbose_log, verbose_print
from ut.llm_client import generate_test_plan, generate_test_case
from ut.parser import calculate_import_path_simple, source_code_analysis
from ut.prompts.prompt_builder import (
    generate_class_method_prompt,
    generate_standalone_prompt,
    generate_planner_prompt,
    generate_coder_prompt,
)
from ut.test_writer import (
    combine_test_code,
    extract_imports_and_functions,
    postprocess_test_code_enhanced,
)

console = Console()

# This function assumes no collaboration
def process_file(
    file_path: Path,
    output_base: Path,
    mirror_structure: bool,
    verbose: bool,
    dry_run: bool,
    base_path: Optional[Path] = None,
):
    """Process a single Python file to generate tests.

    Args:
        file_path (Path): The path to the Python file to process.
        output_base (Path): The base directory for output files.
        mirror_structure (bool): Whether to mirror the source directory structure.
        verbose (bool): Whether to print verbose output.
        dry_run (bool): Whether to perform a dry run (no file modifications).
        base_path (Optional[Path], optional): The base directory for the source files.
        Defaults to None.
    """
    verbose_log(f"Extracting imports and functions from {file_path.name}", verbose)

    with console.status(
        f"[bold green]Generating tests for {file_path.name}...[/bold green]",
        spinner="dots",
    ):
        try:
            imports_code, functions_data = source_code_analysis(str(file_path))
        except Exception as e:
            console.print(f"[red]Failed to analyze {file_path.name}: {e}[/red]")
            return

        if not functions_data:
            if verbose:
                console.print(
                    f"[yellow]No functions found in {file_path.name}[/yellow]"
                )
            return

        # Determine output directory
        if mirror_structure and base_path:
            # Mirror the source structure in output
            rel_path = file_path.relative_to(base_path)
            test_dir = output_base / rel_path.parent
        else:
            # Flat structure - all tests in output_base
            test_dir = output_base

        if not dry_run:
            test_dir.mkdir(parents=True, exist_ok=True)

        verbose_print(f"[dim]Test output directory: {test_dir}[/dim]", verbose)

        module_import_path = calculate_import_path_simple(file_path)

        all_test_functions = []
        all_imports = set()

        # Process each function in the file
        for i, func_data in enumerate(functions_data):
            function_name = func_data["function_name"]

            verbose_log(
                f"\n  → Processing function {i + 1}/{len(functions_data)}: \
                            [cyan]{function_name}[/cyan]",
                verbose,
            )

            # Generate prompt based on whether it's a class method
            # or standalone function
            if func_data["parent_class_code"]:
                verbose_log("    Class method detected", verbose)

                prompt = generate_class_method_prompt(
                    imports_code, function_name, func_data["parent_class_code"]
                )
            else:
                verbose_log("    Standalone function detected", verbose)

                prompt = generate_standalone_prompt(
                    imports_code, func_data["function_code"]
                )

            verbose_log("    Sending to LLM...", verbose)

            if not dry_run:
                raw_response = generate_test_plan(prompt)

                clean_code = postprocess_test_code_enhanced(
                    raw_response, function_name, module_import_path, file_path.stem
                )

                test_imports, test_functions = extract_imports_and_functions(clean_code)

                valid_functions = [
                    f for f in test_functions if f.strip() and DEF_TEST_STRING in f
                ]

                if valid_functions:
                    all_imports.update(test_imports)
                    all_test_functions.extend(valid_functions)
                    console.print(
                        f"    ✓ Generated {len(valid_functions)} \
                            test(s) for [green]{function_name}[/green]"
                    )
                else:
                    console.print(
                        f"    ⚠️ No valid tests generated for \
                                  [yellow]{function_name}[/yellow]"
                    )
            else:
                console.print(f"    [dim]Would generate test for {function_name}[/dim]")

        if not dry_run and all_test_functions:
            # Combine all tests into a single file
            combined_test_code = combine_test_code(
                all_imports, all_test_functions, file_path.stem, module_import_path
            )

            # Write the combined test file
            test_file_name = f"test_{file_path.stem}.py"
            test_file_path = test_dir / test_file_name

            with open(test_file_path, "w", encoding="utf-8") as f:
                f.write(combined_test_code)

            rel_test_path = test_file_path.relative_to(output_base)
            console.print(
                f"\n  📄 Test file created: [bold green]\
                {output_base}/{rel_test_path}[/bold green]"
            )
            console.print(f"     Contains {len(all_test_functions)} test functions")

def extract_code(file_path: Path, ignore_list: list[str], verbose: Optional[bool] = False):
    # Determine which files contain python source code (assume there is no existing directory for pytest tests)
    python_files = list(file_path.rglob("*.py")) if file_path.is_dir() else ([file_path] if file_path.suffix == ".py" else [])
    if len(python_files) == 0:
        console.print(f"[bold red]Error: No Python files found in {file_path}[/bold red]")
        return
    # Build an index for which functions and classes are defined in which files
    function_locs = {}
    class_locs = {}
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
    return function_locs, class_locs, files_for_planner, functions_data

# This function assumes collaboration
def process_project(
    file_path: Path,
    output_base: Path,
    mirror_structure: bool,
    verbose: bool,
    dry_run: bool,
    conf: dict,
    base_path: Optional[Path] = None,
    ignore_list: Optional[list[str]] = ['__init__.py', 'tests'],
    log_folder: Optional[str] = None,
):
    """
    Process a Python project directory to generate unit tests.

    Args:
        file_path (Path): The path to the source file or directory.
        output_base (Path): The base output directory for generated tests.
        mirror_structure (bool): Whether to mirror the source directory structure.
        verbose (bool): Whether to enable verbose output.
        dry_run (bool): Whether to perform a dry run without creating files.
        base_path (Optional[Path]): The base path for relative imports.
    """
    verbose_log(f"Preparing planner prompt for {file_path.name}", verbose)
    
    if log_folder is None:
        log_folder = datetime.now().strftime("%Y%m%d_%H%M%S")

    # TODO: Instead of returning functions_data directly, it should be processed further first
    function_locs, class_locs, files_for_planner, functions_data = extract_code(file_path, ignore_list, verbose)

    console.print(f"[bold blue]Planning test generation[/bold blue]")

    """# # Determine output directory
    # if mirror_structure and base_path:
    #     # Mirror the source structure in output
    #     rel_path = file_path.relative_to(base_path)
    #     test_dir = output_base / rel_path.parent
    # else:
    #     # Flat structure - all tests in output_base
    #     test_dir = output_base
    """
    # Flat structure - all tests in output_base
    test_dir = output_base

    if not dry_run:
        test_dir.mkdir(parents=True, exist_ok=True)

    verbose_log(f"[dim]Test output directory: {test_dir}[/dim]", verbose)

    module_import_path = calculate_import_path_simple(file_path)
    function_imports = []
    # Right now we assume that the directory on which generate is called is the top-level module, and hence the imports should start with it
    for func_name, filename in function_locs.items():
        # import_path_start = filename.find(file_path.name) # Using this would be less elegant
        import_path = filename.relative_to(file_path)
        import_path_converted = str(import_path).replace('/', '.').replace('.py', '')
        function_imports.append("from " + import_path_converted + f" import {func_name}")

    # Concatenate the source code of all files to send to the LLM
    combined_source_code = ""
    for source_file in files_for_planner:
        try:
            with open(source_file, "r", encoding="utf-8") as f:
                combined_source_code += f"\n====== File: {source_file.name} ======\n" + f.read() + "\n"
        except Exception as e:
            console.print(f"[red]Failed to read {source_file.name}: {e} \n unit tests will not be generated for functions in this file [/red]")
            continue
    
    # Make the prompt for the planner
    prompt = generate_planner_prompt(combined_source_code, template_path=conf['planner']['prompt_file'])

    verbose_print("    Sending to LLM...", verbose)

    if not dry_run:
        raw_response = generate_test_plan(prompt)
        # Log both the prompt and the response to a subfolder of ./logs/planner/
        # The subfolder will be named based on the date and time the script was run
        log_dir = Path("./logs/planner/" + log_folder)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"planner_response_{file_path.stem}.txt"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(raw_response)
    else:
        console.print(f"    [dim]Would generate test plan for project in {file_path}[/dim]")
        return
    
    # # TODO: For testing purposes only
    # with open("/data1/jcarleton/unittest-ai-agent/logs/planner/original/planner_response_converter.txt", 'r') as file:
    #     raw_response = file.read()

    # Parse the response to get test plans for each function
    # Assume the response contains sections like:
    # **Test Case: `test_name`**
    #     - *Functions required:* function_a, function_b, ...
    #     - *Description:*
    # We want to extract the test case name, functions required, and description for each test case, and turn it into a dictionary where the key is the test case name and the value contains the other elements
    test_case_plans = {}
    
    # Parse the raw response to extract test case plans
    import re
    
    # Split by test case headers (numbered list with "Test Case:" pattern)
    test_case_pattern = r'\d+\.\s+\*\*Test Case:\s+`([^`]+)`\*\*'
    description_pattern = r'-\s+\*Description:\*\s+(.+?)$'
    
    test_cases = re.finditer(test_case_pattern, raw_response)
    
    for match in test_cases:
        test_name = match.group(1)
        start_pos = match.end()
        
        # Find the description for this test case (single line only)
        desc_match = re.search(description_pattern, raw_response[start_pos:], re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()
            test_case_plans[test_name] = description
            verbose_log(f"  → Extracted test plan: {test_name}", verbose)
    
    if not test_case_plans:
        console.print("[yellow]Warning: No test case plans extracted from planner response[/yellow]")
        return
    
    console.print(f"[bold green]Extracted {len(test_case_plans)} test case plans[/bold green]")
    
    # For each test case plan, construct a prompt for the coding LLM to generate the test code
    # For now, we process prompts one at a time; in the future, they should be batched if memory allows
    # or divided across GPUs if multiple are available
    prompts = {}
    test_cases = {}
    import_statements = set()
    for test_name, test_plan in test_case_plans.items():
        verbose_log(f"\n  → Generating test code for: [cyan]{test_name}[/cyan]", verbose)
        
        prompt = generate_coder_prompt(
            functions_data[0]['function_code'], # TODO: Replace with correct function code lookup
            f"{test_name}: {test_plan}"
        )
        prompts[test_name] = prompt
        raw_response = generate_test_case(prompt)

        if "```python" in raw_response:
            cleaned_response = raw_response.split("```python")[1].split("```")[0].strip()
        else:
            # If the model fails to follow the formatting instructions, we can still try to parse it
            if "### Import statements\n" in raw_response:
                cleaned_response = raw_response.split("### Import statements\n")[1].strip()
            elif "### Test function\n" in raw_response:
                cleaned_response = raw_response.split("### Test function\n")[1].strip()
            else:
                console.print(f"[yellow]Error: Unable to parse generated test for {test_name}.[/yellow]")
        new_imports, new_funcs = extract_imports_and_functions(cleaned_response)
        import_statements.update(new_imports)
        test_cases[test_name] = new_funcs[0]  # Assume one function per test case
        # print("Imports:\n")
        # for imp in new_imports:
        #     print(f"  - {imp}")
        # print("Functions:\n")
        # for func in new_funcs:
        #     print(func)
    
    # Make sure the functions to be tested are imported in the test file
    import_statements.update(function_imports)
    
    # Create a single file with all the test cases
    if len(test_cases) > 0:
        combined_test_code = combine_test_code(
            import_statements, list(test_cases.values()), file_path.stem, module_import_path
        )
        # Write the combined test file
        test_file_name = f"test_{file_path.stem}.py"
        test_file_path = test_dir / test_file_name

        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(combined_test_code)

        rel_test_path = test_file_path.relative_to(output_base)
        console.print(
            f"\n  📄 Test file created: [bold green]\
            {output_base}/{rel_test_path}[/bold green]"
        )
        console.print(f"     Contains {len(test_cases)} test functions")
    else:
        console.print("[red]Error: No usable test cases parsed.[/red]")