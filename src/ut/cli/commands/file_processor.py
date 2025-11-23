"""Automated Unit Test Generation CLI with AI."""
from pathlib import Path
from typing import Optional
from datetime import datetime
import os

from rich.console import Console

from ut.cli.commands.constants import DEF_TEST_STRING
from ut.cli.commands.helper import verbose_log, verbose_print
from ut.workspace import WorkspaceManager
from ut.llm_client import generate_test_plan, parse_test_case_plan_old, parse_test_case_plan_json
from ut.parser import calculate_import_path_simple, source_code_analysis, extract_code, get_function_imports, get_context_for_test_gen
from ut.prompts.prompt_builder import (
    generate_class_method_prompt,
    generate_standalone_prompt,
    generate_planner_prompt,
    generate_coder_prompt,
)
from ut.test_writer import (
    generate_test_from_prompt,
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
    dry_run: bool,
    base_path: Optional[Path] = None,
):
    """Process a single Python file to generate tests.

    Args:
        file_path (Path): The path to the Python file to process.
        output_base (Path): The base directory for output files.
        mirror_structure (bool): Whether to mirror the source directory structure.
        dry_run (bool): Whether to perform a dry run (no file modifications).
        base_path (Optional[Path], optional): The base directory for the source files.
        Defaults to None.
    """
    verbose_log(f"Extracting imports and functions from {file_path.name}")

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
            if "UT_VERBOSE" in os.environ:
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

        verbose_print(f"[dim]Test output directory: {test_dir}[/dim]")

        module_import_path = calculate_import_path_simple(file_path)

        all_test_functions = []
        all_imports = set()

        # Process each function in the file
        for i, func_data in enumerate(functions_data):
            function_name = func_data["function_name"]

            verbose_log(
                f"\n  → Processing function {i + 1}/{len(functions_data)}: \
                            [cyan]{function_name}[/cyan]",
            )

            # Generate prompt based on whether it's a class method
            # or standalone function
            if func_data["parent_class_code"]:
                verbose_log("    Class method detected")

                prompt = generate_class_method_prompt(
                    imports_code, function_name, func_data["parent_class_code"]
                )
            else:
                verbose_log("    Standalone function detected")

                prompt = generate_standalone_prompt(
                    imports_code, func_data["function_code"]
                )

            verbose_log("    Sending to LLM...")

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


# This function assumes collaboration
def process_project(
    file_path: Path,
    output_base: Path,
    mirror_structure: bool,
    dry_run: bool,
    conf: dict,
    workspace: WorkspaceManager,
    base_path: Optional[Path] = None,
    ignore_list: Optional[list[str]] = ['__init__.py', 'tests', 'test'],
):
    """
    Process a Python project directory to generate unit tests.

    Args:
        file_path (Path): The path to the source file or directory.
        output_base (Path): The base output directory for generated tests.
        mirror_structure (bool): Whether to mirror the source directory structure.
        dry_run (bool): Whether to perform a dry run without creating files.
        base_path (Optional[Path]): The base path for relative imports.
    """
    verbose_log(f"Preparing planner prompt for {file_path.name}")

    if conf['project'].get('include_init_files', False) and '__init__.py' in ignore_list:
        ignore_list.remove('__init__.py')
    function_locs, class_locs, files_for_planner, function_dict, class_dict = extract_code(file_path, ignore_list)

    console.print(f"[bold blue]Planning test generation[/bold blue]")

    # Flat structure - all tests in output_base
    test_dir = workspace.get_coder_output_dir()
    os.makedirs(test_dir, exist_ok=True)

    # if not dry_run:
    #     test_dir.mkdir(parents=True, exist_ok=True)

    verbose_log(f"[dim]Test output directory: {test_dir}[/dim]")

    module_import_path = calculate_import_path_simple(file_path)
    function_imports = get_function_imports(file_path, function_locs, class_locs)

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

    if dry_run:
        console.print(f"    [dim]Would generate test plan for project in {file_path}[/dim]")
        return
    elif 'predefined_plan_path' in conf and conf['predefined_plan_path'] is not None:
        predefined_plan_path = conf['predefined_plan_path']
        verbose_log(f"Using predefined test plan from {predefined_plan_path}")
        with open(predefined_plan_path, "r") as f:
            raw_response = f.read()
    else:
        verbose_print("    Sending to LLM...")
        raw_response = generate_test_plan(prompt)
        if raw_response is None:
            console.print(f"[red]Error occured during plan generation[/red]")
            return
        # Log both the prompt and the response to a subfolder of ./logs/planner/
        # The subfolder will be named based on the date and time the script was run
        log_dir = Path(workspace.get_planner_output_dir())
        log_file_prompt = log_dir / f"planner_prompt_{file_path.stem}.txt"
        with open(log_file_prompt, "w", encoding="utf-8") as f:
            f.write(prompt)
    # Even if we use a predefined plan, we still log it so that we can resume later (this may be redundant
    # if the config is reused, but it's safer this way)
    log_file_response = Path(workspace.get_planner_output_dir()) / f"planner_response_{file_path.stem}.txt"
    with open(log_file_response, "w", encoding="utf-8") as f:
        f.write(raw_response)
    workspace.set_status("PLANNING_DONE")

    if conf['planner']['plan_format'] == 'basic':
        test_case_plans = parse_test_case_plan_old(raw_response)
    elif conf['planner']['plan_format'] == 'json':
        test_case_plans = parse_test_case_plan_json(raw_response)
    else:
        raise ValueError(f"Unsupported plan format: {conf['planner']['plan_format']}")
    
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
        verbose_log(f"\n  → Generating test code for: [cyan]{test_name}[/cyan]")

        function_code_context = get_context_for_test_gen(
            test_plan, function_dict, class_dict
        )
        
        prompt = generate_coder_prompt(
            function_code_context,
            f"{test_name}: {test_plan}"
        )
        prompts[test_name] = prompt

        cleaned_response = generate_test_from_prompt(prompt, test_name, os.path.join(test_dir, "raw_outputs"))
                
        if cleaned_response is None:
            console.print(f"[yellow]Error: Unable to parse generated test for {test_name}.[/yellow]")
            # breakpoint()
            continue

        new_imports, new_funcs = extract_imports_and_functions(cleaned_response)
        if len(new_funcs) > 0:
            import_statements.update(new_imports)
            test_cases[test_name] = new_funcs[0]  # Assume one function per test case
        else:
            console.print(f"[yellow]Warning: No test functions extracted for {test_name}.[/yellow]")
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
        test_file_path = Path(os.path.join(test_dir, test_file_name))

        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(combined_test_code)

        console.print(
            f"\n  📄 Test file created: [bold green]\
            {test_file_path}[/bold green]"
        )
        console.print(f"     Contains {len(test_cases)} test functions")
    else:
        console.print("[red]Error: No usable test cases parsed.[/red]")

    # To enable iterative refinement, we retain this information
    return test_cases, test_case_plans