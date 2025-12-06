"""Automated Unit Test Generation CLI with AI."""
import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ut.cli.commands.file_processor import process_file, process_project, combine_and_write_tests
from ut.cli.commands.helper import clean_temp_files, verbose_log
from ut.llm_client import is_vllm_running, parse_test_case_plan_old, parse_test_case_plan_json, generate_test_cases_batched
from ut.parser import get_context_for_test_gen, calculate_import_path_simple, get_function_imports, clean_imports_for_file
from ut.prompts.prompt_builder import generate_coder_prompt, generate_coder_revision_prompt
from ut.test_writer import extract_imports_and_functions, combine_test_code, clean_coder_response
from ut.test_checker import lint_test_case
from ut.test_runner import run_tests_with_error_removal
from ut.workspace import WorkspaceManager
from omegaconf import OmegaConf
import os, shutil, pickle, json
from datetime import datetime

console = Console()


def generate(
    file_path: str = typer.Argument(
        None, help="Path to source file or directory."
    ),
    verbose: bool = typer.Option(True, "--verbose", "-v", help="Show detailed output"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be generated without creating files"
    ),
    mirror_structure: bool = typer.Option(
        True,
        "--mirror/--flat",
        help="Mirror source directory structure in output (default: mirror)",
    ),
    no_collab: bool = typer.Option(
        False,
        "--no-collab",
        help="Use the API model to directly generate tests rather than planning for a local LLM.",
    ),
    config_name: Optional[str] = typer.Option(
        "json_format_DottedDict",
        "--config",
        "-c",
        help="Configuration name for prompt templates and settings",
    ),
    plan_path: Optional[str] = typer.Option(
        None,
        "--plan_path",
        help="Path to a predefined test plan file (overrides initial planning step)",
        metavar="FILE_PATH"
    ),
    resume_from: Optional[str] = typer.Option(
        None,
        "--resume_from",
        help="Path to a workspace directory to resume from.",
        metavar="FILE_PATH"
    ),
) -> None:
    """
    Generate unit tests for Python files in any Python project.

    Works with Django, FastAPI, Flask, or any Python codebase.
    Tests are generated in 'ut_output/' directory by default, preserving \
        the source project structure for easy review and manual integration.

    Examples:
        ut generate  # Current directory -> ut_output/
        ut generate my_module.py  # Single file -> ut_output/test_my_module.py
        ut generate src/  # All files in src/ -> ut_output/src/...
        ut generate . --output tests/  # Custom output directory
        ut generate src/ --flat  # All tests in ut_output/ without subdirs

    After generation, review the tests in ut_output/ and move them to your
    project's test directory as needed.
    """

    if not no_collab:
        if not is_vllm_running():
            console.print(
                "[bold red]Error: vLLM server is not running on port 8000. \
                    Please start the server before generating tests.[/bold red]"
            )
            raise typer.Exit(code=1)

    if ".yaml" not in config_name:
            config_name += ".yaml"
            
    ### Setup WorkspaceManager
    if resume_from is not None:
        workspace = WorkspaceManager(base_dir=resume_from)
    else:
        name = "Workspaces/" + file_path.strip('/').split('/')[-1] + "_" + datetime.now().strftime("%m-%d_%H:%M:%S")
        workspace = WorkspaceManager(base_dir=name, fresh_start=True, config_path=os.path.join("configs", config_name))
    # If we are resuming, there will already be an output.log file. Otherwise, create one
    if not workspace.check_for_logfile():
        with open(workspace.get_path("output.log"), "w") as log_file:
            log_file.write(f"Log created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    ### Set environment variables
    # If verbose output is requested, set the appropriate environment variable
    if verbose:
        os.environ["UT_VERBOSE"] = "1"
    # Save the name for the log directory to an environment variable
    if "UT_LOG_FILE" not in os.environ:
        os.environ["UT_LOG_FILE"] = workspace.get_log_path()

    # Mention in the log if we are resuming
    if resume_from is not None:
        verbose_log(f"Resuming from workspace at {resume_from}")

    # Clean up temporary files
    clean_temp_files()

    # Get config
    if resume_from is not None:
        conf = workspace.get_config()
    else:
        conf = OmegaConf.load(os.path.join("configs", config_name))
    if plan_path is not None:
        conf['predefined_plan_path'] = plan_path
    elif workspace.get_status() not in ["START"]:
        conf['predefined_plan_path'] = Path(workspace.get_planner_output_dir()) / f"planner_response_{Path(file_path).stem}.txt"
        assert os.path.exists(conf['predefined_plan_path']), f"Tried to resume but existing plan path {conf['predefined_plan_path']} could not be found."

    if not file_path:
        console.print("[bold red]Error: The file path cannot be empty.[/bold red]")
        raise typer.Exit(code=1)

    path = Path(file_path).resolve()
    output_base = Path(workspace.get_coder_output_dir()).resolve()

    is_not_python_file = path.is_file() and not path.suffix == ".py"

    if is_not_python_file:
        console.print(f"[bold red]Error: {path} is not a Python file[/bold red]")
        raise typer.Exit(1)

    # TODO: This solution will not work permanently, but for now we only try to resume after the initial 
    # tests have been generated
    if workspace.get_status() not in ["CODE_GENERATED", "CODE_TESTED"] and workspace.coder_iteration == 0:
        if path.is_file():
            console.print(f"[bold blue]Processing single file: {path.name}[/bold blue]")
            if no_collab:
                console.print(
                    "[bold red]Error: Non-collaborative mode has not been fixed yet; logging is not correctly set up.[/bold red]"
                )
                raise typer.Exit(1)
                # process_file(path, output_base, mirror_structure, dry_run)
            else:
                test_cases, test_case_plans = process_project(path, output_base, mirror_structure, dry_run, conf, workspace)

        elif path.is_dir():
            if no_collab:
                console.print(
                    "[bold red]Warning: Directory processing is not implemented for non-collaborative mode.[/bold red]"
                )
                raise typer.Exit(1)
            else:
                console.print(
                    f"[bold blue]Processing directory: {path}[/bold blue]"
                )
                test_cases, test_case_plans = process_project(path, output_base, mirror_structure, dry_run, conf, workspace)

        else:
            msg_sufix = "is neither a file nor a directory"
            console.print(f"[bold red]Error: '{file_path}' {msg_sufix}[/bold red]")
            raise typer.Exit(1)

        # Clean up temporary files
        clean_temp_files()

        if not dry_run:
            console.print(
                f"\n✅ [bold green]Tests generated successfully in \
                    {output_base}/[/bold green]"
            )
        else:
            console.print("\n[yellow]Dry run completed. No files were created.[/yellow]")
            return
        # Save test_cases to a file in case we need to resume later; note that test_case_plans can be extracted
        # from the logged files
        verbose_log("Saving generated test cases to resume directory.")
        # pickle.dump(test_cases, open(os.path.join(workspace.get_resume_dir(), "test_cases.pkl"), "wb"))
        workspace.set_status("CODE_GENERATED")
    else:
        console.print(f"[bold blue]Loading data from previous runs...[/bold blue]")
        # Load test_cases from the resume directory
        # test_cases = pickle.load(open(os.path.join(workspace.get_resume_dir(), "test_cases.pkl"), "rb"))
        # Load existing plan
        with open(Path(workspace.get_planner_output_dir()) / f"planner_response_{Path(file_path).stem}.txt", "r") as f:
            full_plan = f.read()
        if conf['planner']['plan_format'] == 'basic':
            test_case_plans = parse_test_case_plan_old(full_plan)
        elif conf['planner']['plan_format'] == 'json':
            test_case_plans = parse_test_case_plan_json(full_plan)
        else:
            raise ValueError(f"Unsupported plan format: {conf['planner']['plan_format']}")
        # Load the import statements that went into the test file
        all_imports_and_functions = workspace.load_cur_imports_and_functions()
        test_cases = all_imports_and_functions.get('functions', {})
        console.print(f"[bold blue]Test code is already generated. Running tests...[/bold blue]")

    assert 'test_dir_in_container' in conf['project']
    test_dir = conf['project'].get('test_dir_in_container', None)
    image_name = conf['project'].get('docker_image_name', None)
    if test_dir is None or image_name is None:
        console.print(f"\n[bold yellow]Skipping test execution: Docker image name or test directory in container not specified in configuration.[/bold yellow]")
        console.print(f"[dim]Stopping here.[/dim]")
        return
    
    ### Run the generated tests inside a Docker container (This is only for the first iteration)
    if workspace.get_status() == "CODE_GENERATED" and workspace.coder_iteration == 0:
        test_filepath = os.path.join(output_base, f"test_{path.stem}.py")
        if os.path.exists(test_filepath):
            console.print(f"\n[bold blue]Running generated tests in Docker container '{image_name}'[/bold blue]")
            test_results_dict, test_feedback = run_tests_with_error_removal(test_filepath, conf)
            # If still None, give up and mark all tests as failed
            if test_results_dict is None:
                console.print(f"\n[bold red]Unable to run tests after attempting to fix error. Marking all tests as FAILED.[/bold red]")
                test_results_dict = {test_name: 'FAILED' for test_name in test_case_plans.keys()}
                test_feedback = {test_name: "Test could not be run" for test_name in test_case_plans.keys()}
            # Save the test results to a json file
            workspace.save_test_results(test_results_dict, test_feedback)
            print(test_results_dict)
            workspace.update_remaining_tests([test for test in test_case_plans.keys() if test_results_dict.get(test, 'FAILED') == 'PASSED'])
            
            if len(test_results_dict) == 0:
                console.print(f"\n[bold red]No test results were parsed. Something went wrong.[/bold red]")
                breakpoint()
                console.print(f"[dim]Stopping here.[/dim]")
                return

            if test_case_plans is None:
                verbose_log("No test case plans could be extracted from the workspace; cannot determine which tests need to be retried.")
                console.print(f"[dim]Stopping here.[/dim]")
                return
        else:
            console.print(f"\n[bold red]Test file {test_filepath} not found in coder output directory. This means no valid tests were generated.[/bold red]")
            console.print(f"[dim]Skipping testing.[/dim]")
            test_results_dict = {}
        
        workspace.set_status("CODE_TESTED")
        workspace.next_coder_iteration()
    else:
        test_results_dict, test_feedback = workspace.load_test_results()

    # From here on, the coder prompts may require additional context such as previously generated code and 
    # failure feedback. Here we set up a data structure to hold that info
    test_context = {}
    linter_messages = workspace.load_linter_messages()
    for test_name in test_case_plans.keys():
        # TODO: Consider adding the "function_code_context" to this
        test_context[test_name] = {
            "previous_code": test_cases.get(test_name, None),
            "test_plan": test_case_plans[test_name],
            "linter_message": linter_messages.get(test_name, None),
            "test_result": test_results_dict.get(test_name, None), # Note that this will be None for tests which passed on previous iterations AND for tests which did not make it past the linter
            "test_feedback": test_feedback.get(test_name, None)
        }
    workspace.save_test_context(test_context)

    ### Enter a loop for refining the tests until all planned tests either pass or have been reached the max
        # number of attempts
    assert 'max_attempts' in conf['coder'], "Configuration must specify 'max_attempts' in the 'coder' section."
    max_attempts = conf['coder']['max_attempts']
    curr_attempts = 1 if workspace.coder_iteration == 0 else workspace.coder_iteration

    # If resuming, check if we have already reached max attempts. If so, only consider if the user desires to exceed it
    if curr_attempts >= max_attempts:
        console.print(f"\n[bold yellow]Maximum number of attempts ({max_attempts}) already reached. Continue anyways?[/bold yellow]")
        continue_generating = typer.confirm("Do you want to continue generating tests?")
        if continue_generating:
            max_attempts = curr_attempts + 1  # Allow one more attempt

    while curr_attempts < max_attempts:
        # From now on, the status will only ever be "CODE_TESTED" or "CODE_GENERATED"
        # If the status is "CODE_TESTED", that means it is time to refine the tests
        if workspace.get_status() == "CODE_TESTED":
            console.print(f"\n[bold blue]Begin test gen iteration {curr_attempts+1} of {max_attempts}[/bold blue]")
            test_context = workspace.load_test_context()
            
            # Determine which test plan items have been satisfied and which need to be retried
            remaining_tests = workspace.get_remaining_tests()
            if len(remaining_tests) == 0:
                console.print(f"\n[bold green]All planned tests have passed![/bold green]")
                break
            prev_iter_test_names = test_cases.keys()
            # For any test that is in all_planned_tests but not in prev_iter_test_names, we either need 
            # to retry from scratch or apply the linter feedback to revise the test
            # For any test that is in both, we check if it passed or failed. failed tests are retried with a 
            # modified prompt
            untested = list(set(remaining_tests) - set(prev_iter_test_names))
            lint_messages = workspace.load_linter_messages()
            revise_with_linter_feedback = [test_name for test_name in lint_messages]
            retry_from_scratch = [test_name for test_name in untested if test_name not in lint_messages]
            passed_tests = [test_name for test_name in prev_iter_test_names if test_results_dict.get(test_name, 'FAILED') == 'PASSED']
            failed_tests = [test_name for test_name in prev_iter_test_names if test_name not in passed_tests]
            # First get the prompt for each test we will be retrying. For tests that we retry fron scratch, the
            # existing prompt can be reused. For failed tests, we need to modify the prompt to include
            # information about the failure
            prompts = {}
            test_cases = {}
            func_and_class_info = workspace.load_func_and_class_info()
            function_dict = {name: func_and_class_info['functions'][name]["code"] for name in func_and_class_info['functions'].keys()}
            # Note that each key in class_dict is expected to be a dict, rather than a string as in function_dict
            class_dict = {name: func_and_class_info['classes'][name]for name in func_and_class_info['classes'].keys()}
            function_locs = {name: func_and_class_info['functions'][name]["location"] for name in func_and_class_info['functions'].keys()}
            class_locs = {name: func_and_class_info['classes'][name]["location"] for name in func_and_class_info['classes'].keys()}
            import_statements = set()
            # Make sure the functions to be tested are imported in the test file
            # function_imports = get_function_imports(path, function_locs, class_locs)
            function_imports = [f"from {conf['project']['module_name'].replace('-', '_')} import {name}" for name in conf['project']['names_to_test']]
            import_statements.update(function_imports)
            module_import_path = calculate_import_path_simple(path)
            for test_name in retry_from_scratch:
                verbose_log(f"\n  → Will re-use code generation prompt for test: [cyan]{test_name}[/cyan]")
                # Re-create the prompt using the previously generated plan and the saved function and class dicts
                test_plan = test_case_plans[test_name]

                # NOTE: These are the imports which actually matter
                allowed_imports = "\n".join(function_imports) + "\nimport pytest\n" + "\n".join([f"import {module}" for module in test_plan.get("external_imports", [])])

                function_code_context = get_context_for_test_gen(
                    test_plan, function_dict, class_dict
                )
                prompt = generate_coder_prompt(
                    function_code_context,
                    f"{test_name}: {test_plan}",
                    allowed_imports=allowed_imports,
                )
                prompts[test_name] = prompt
            
            for test_name in revise_with_linter_feedback:
                verbose_log(f"\n  → Generating refined prompt for lint-failed test: [cyan]{test_name}[/cyan]")
                # Get the original plan and the test result details
                test_plan = test_context[test_name]['test_plan']
                # NOTE: These are the imports which actually matter
                allowed_imports = "\n".join(function_imports) + "\nimport pytest\n" + "\n".join([f"import {module}" for module in test_plan.get("external_imports", [])])
                function_code_context = get_context_for_test_gen(
                    test_plan, function_dict, class_dict
                )
                # Create a refined prompt that includes information about the failure
                prompt = generate_coder_revision_prompt(
                    function_code_context,
                    f"{test_name}: {test_context[test_name]['test_plan']}",
                    prev_attempt_code=test_context[test_name]["previous_code"],
                    type_of_revision="lint",
                    feedback_message=test_context[test_name]["linter_message"],
                    allowed_imports=allowed_imports,
                )
                prompts[test_name] = prompt

            for test_name in failed_tests:
                verbose_log(f"\n  → Generating refined prompt for failed test: [cyan]{test_name}[/cyan]")
                # Get the original plan and the test result details
                test_plan = test_context[test_name]['test_plan']
                # NOTE: These are the imports which actually matter
                allowed_imports = "\n".join(function_imports) + "\nimport pytest\n" + "\n".join([f"import {module}" for module in test_plan.get("external_imports", [])])
                function_code_context = get_context_for_test_gen(
                    test_plan, function_dict, class_dict
                )
                if test_name in test_feedback.keys():
                    # Create a refined prompt that includes information about the failure
                    prompt = generate_coder_revision_prompt(
                        function_code_context,
                        f"{test_name}: {test_context[test_name]['test_plan']}",
                        prev_attempt_code=test_context[test_name]["previous_code"],
                        type_of_revision="test_fail",
                        feedback_message=test_context[test_name]["test_feedback"],
                        allowed_imports=allowed_imports,
                    )
                else:
                    prompt = generate_coder_prompt(
                        function_code_context,
                        f"{test_name}: {test_context[test_name]['test_plan']}",
                        allowed_imports=allowed_imports,
                    )
                    
                prompts[test_name] = prompt
            
            # Batched generation
            verbose_log(f"\n  → Generating test codes for {len(prompts)} test(s)...")
            responses = asyncio.run(generate_test_cases_batched(prompts, temperature=0.2))

            lint_messages = {}
            for test_name, response in responses.items():
                cleaned_response = clean_coder_response(response, test_name, workspace.get_coder_output_dir())
                        
                if cleaned_response is None:
                    console.print(f"[yellow]Error: Unable to parse generated test for {test_name}.[/yellow]")
                    # breakpoint()
                    continue

                # For convenience, we use the same function that is used to create the final test file here
                cleaned_response_with_with_function_imports = combine_test_code(
                        function_imports,
                        [cleaned_response],
                        path.stem, # This is the module name
                        module_import_path
                    )
                
                passed_lint, lint_message = lint_test_case(cleaned_response_with_with_function_imports, workspace.get_resume_dir())
                if not passed_lint:
                    console.print(f"[yellow]Linting failed for {test_name}. Will retry on next iteration.[/yellow]")
                    continue
                lint_messages[test_name] = lint_message

                new_imports, new_funcs = extract_imports_and_functions(cleaned_response, assume_single_function=True)
                if len(new_funcs) > 0:
                    import_statements.update(new_imports)
                    test_cases[test_name] = new_funcs[0]  # Assume one function per test case
                else:
                    console.print(f"[yellow]Warning: No test functions extracted for {test_name}.[/yellow]")
            
            # Create a single file with all the test cases
            import_statements = clean_imports_for_file(import_statements, "\n".join(test_cases.values()))
            combine_and_write_tests(test_cases, import_statements, Path(file_path), workspace.get_coder_output_dir(), module_import_path)

            workspace.save_linter_messages(lint_messages)

            workspace.save_cur_imports_and_functions(import_statements, test_cases)
            workspace.set_status("CODE_GENERATED")

        test_filepath = os.path.join(workspace.get_coder_output_dir(), f"test_{path.stem}.py")
        console.print(f"\n[bold blue]Running generated tests in Docker container '{image_name}'[/bold blue]")
        test_results_dict, test_feedback = run_tests_with_error_removal(test_filepath, conf)
        # If still None, give up and mark all tests as failed
        if test_results_dict is None:
            console.print(f"\n[bold red]Unable to run tests after attempting to fix error. Marking all tests as FAILED.[/bold red]")
            test_results_dict = {test_name: 'FAILED' for test_name in test_case_plans.keys()}
            test_feedback = {test_name: "Test could not be run" for test_name in test_case_plans.keys()}
        # Save the test results to a json file
        workspace.save_test_results(test_results_dict, test_feedback)
        print(test_results_dict)
        workspace.update_remaining_tests([test for test in test_case_plans.keys() if test_results_dict.get(test, 'FAILED') == 'PASSED'])
        
        test_context = {}
        linter_messages = workspace.load_linter_messages()
        for test_name in test_case_plans.keys():
            test_context[test_name] = {
                "previous_code": test_cases.get(test_name, None),
                "test_plan": test_case_plans[test_name],
                "linter_message": linter_messages.get(test_name, None),
                "test_result": test_results_dict.get(test_name, None),
                "test_feedback": test_feedback.get(test_name, None)
            }
        workspace.save_test_context(test_context)

        if len(test_results_dict) == 0:
            verbose_log(f"\n[bold red]No test results were parsed. Something went wrong.[/bold red]")
            breakpoint()
            verbose_log(f"[dim]Stopping here.[/dim]")
            return

        workspace.set_status("CODE_TESTED")
        workspace.next_coder_iteration()
        curr_attempts += 1

    # Collect all the passed tests and write them to a final test file
    all_passed_tests = set(test_case_plans.keys()) - set(workspace.get_remaining_tests())
    passed_test_cases = {}
    all_imports_and_functions = workspace.load_all_imports_and_functions()
    for test_name in all_passed_tests:
        passed_test_cases[test_name] = all_imports_and_functions['functions'][test_name]
    # Write the final file with all passing tests
    import_statements_final = clean_imports_for_file(all_imports_and_functions['imports'], "\n".join(passed_test_cases.values()))
    combine_and_write_tests(passed_test_cases, 
                            import_statements_final, 
                            Path(file_path), 
                            workspace.get_final_output_dir(), 
                            module_import_path, 
                            "final_tests.py")
    console.print(f"\n✅ [bold green]Final test file with all passing tests written to {workspace.get_final_output_dir()}[/bold green]")

