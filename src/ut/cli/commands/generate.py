"""Automated Unit Test Generation CLI with AI."""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ut.cli.commands.file_processor import process_file, process_project, combine_and_write_tests
from ut.cli.commands.helper import clean_temp_files, verbose_log
from ut.llm_client import is_vllm_running, parse_test_case_plan_old, parse_test_case_plan_json
from ut.parser import get_context_for_test_gen, calculate_import_path_simple, get_function_imports
from ut.prompts.prompt_builder import generate_coder_prompt
from ut.test_writer import generate_test_from_prompt, extract_imports_and_functions
from ut.test_runner import DockerTestRunner
from ut.results_parser import parse_pytest_output
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
    ### Setup WorkspaceManager
    if resume_from is not None:
        workspace = WorkspaceManager(base_dir=resume_from)
    else:
        name = "Workspaces/" + file_path.strip('/').split('/')[-1] + "_" + datetime.now().strftime("%m-%d_%H:%M:%S")
        workspace = WorkspaceManager(base_dir=name, fresh_start=True)
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
    if ".yaml" not in config_name:
        config_name += ".yaml"
    conf = OmegaConf.load(os.path.join("configs", config_name))
    if plan_path is not None:
        conf['predefined_plan_path'] = plan_path
    elif workspace.get_status() not in ["START"]:
        conf['predefined_plan_path'] = Path(workspace.get_planner_output_dir()) / f"planner_response_{Path(file_path).stem}.txt"
        assert os.path.exists(conf['predefined_plan_path']), f"Tried to resume but existing plan path {conf['predefined_plan_path']} could not be found."
    if not no_collab:
        if not is_vllm_running():
            console.print(
                "[bold red]Error: vLLM server is not running on port 8000. \
                    Please start the server before generating tests.[/bold red]"
            )
            raise typer.Exit(code=1)

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
        log_dir = workspace.get_resume_dir()
        pickle.dump(test_cases, open(os.path.join(log_dir, "test_cases.pkl"), "wb"))
        workspace.set_status("CODE_GENERATED")
    else:
        console.print(f"[bold blue]Loading data from previous runs...[/bold blue]")
        # Load test_cases from the resume directory
        log_dir = workspace.get_resume_dir()
        test_cases = pickle.load(open(os.path.join(log_dir, "test_cases.pkl"), "rb"))
        # Load existing plan
        with open(Path(workspace.get_planner_output_dir()) / f"planner_response_{Path(file_path).stem}.txt", "r") as f:
            full_plan = f.read()
        if conf['planner']['plan_format'] == 'basic':
            test_case_plans = parse_test_case_plan_old(full_plan)
        elif conf['planner']['plan_format'] == 'json':
            test_case_plans = parse_test_case_plan_json(full_plan)
        else:
            raise ValueError(f"Unsupported plan format: {conf['planner']['plan_format']}")
        console.print(f"[bold blue]Test code is already generated. Running tests...[/bold blue]")

    assert 'test_dir_in_container' in conf['project']
    test_dir = conf['project'].get('test_dir_in_container', None)
    image_name = conf['project'].get('docker_image_name', None)
    if test_dir is None or image_name is None:
        console.print(f"\n[bold yellow]Skipping test execution: Docker image name or test directory in container not specified in configuration.[/bold yellow]")
        console.print(f"[dim]Stopping here.[/dim]")
        return
    def run_tests(test_filepath: str) -> dict:
        # The working directory is where pytest will be run from
        # Be default we assume that the directory for tests is inside the working directory, so if no working dir is specified we derive it from test_dir
        test_runner = DockerTestRunner(image_name=image_name, 
                                       container_name="ut_generate", 
                                       test_dir_in_container=test_dir, 
                                       working_dir=conf['project'].get('working_dir', Path(test_dir).parent.as_posix()))
        test_runner.start_container()
        test_results_string = test_runner.run_pytest(test_filepath)
        test_results_dict = parse_pytest_output(test_results_string)
        return test_results_dict

    ### Run the generated tests inside a Docker container (This is only for the first iteration)
    if workspace.get_status() == "CODE_GENERATED" and workspace.coder_iteration == 0:
        test_filepath = os.path.join(output_base, f"test_{path.stem}.py")
        console.print(f"\n[bold blue]Running generated tests in Docker container '{image_name}'[/bold blue]")
        test_results_dict = run_tests(test_filepath)
        # Save the test results to a json file
        workspace.save_test_results(test_results_dict)
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
        
        workspace.set_status("CODE_TESTED")
        workspace.next_coder_iteration()
    else:
        test_results_dict = workspace.load_test_results()

    ### Enter a loop for refining the tests until all planned tests either pass or have been reached the max
        # number of attempts
    assert 'max_attempts' in conf['coder'], "Configuration must specify 'max_attempts' in the 'coder' section."
    max_attempts = conf['coder']['max_attempts']
    curr_attempts = 1 if workspace.coder_iteration == 0 else workspace.coder_iteration

    # If resuming, check if we have already reached max attempts. If so, only consider if the user desires to exceed it
    if curr_attempts >= max_attempts:
        console.print(f"\n[bold yellow]Maximum number of attempts ({max_attempts}) already reached. Continue anyways?[/bold yellow]")
        typer.confirm("Do you want to continue generating tests?", abort=True)
        max_attempts = curr_attempts + 1  # Allow one more attempt

    while curr_attempts < max_attempts:
        # From now on, the status will only ever be "CODE_TESTED" or "CODE_GENERATED"
        # If the status is "CODE_TESTED", that means it is time to refine the tests
        if workspace.get_status() == "CODE_TESTED":
            console.print(f"\n[bold blue]Begin test gen iteration {curr_attempts+1} of {max_attempts}[/bold blue]")
            # Determine which test plan items have been satisfied and which need to be retried
            remaining_tests = workspace.get_remaining_tests()
            if len(remaining_tests) == 0:
                console.print(f"\n[bold green]All planned tests have passed![/bold green]")
                break
            prev_iter_test_names = test_cases.keys()
            # For any test that is in all_planned_tests but not in prev_iter_test_names, we need to retry from scratch
            # For any test that is in both, we check if it passed or failed. failed tests are retried with a 
            # modified prompt
            retry_from_scratch = list(set(remaining_tests) - set(prev_iter_test_names))
            passed_tests = [test_name for test_name in prev_iter_test_names if test_results_dict.get(test_name, 'FAILED') == 'PASSED']
            failed_tests = [test_name for test_name in prev_iter_test_names if test_name not in passed_tests]
            # First get the prompt for each test we will be retrying. For tests that we retry fron scratch, the
            # existing prompt can be reused. For failed tests, we need to modify the prompt to include
            # information about the failure
            prompts = {}
            test_cases = {}
            import_statements = set()
            func_and_class_info = workspace.load_func_and_class_info()
            function_dict = {name: func_and_class_info['functions'][name]["code"] for name in func_and_class_info['functions'].keys()}
            # Note that each key in class_dict is expected to be a dict, rather than a string as in function_dict
            class_dict = {name: func_and_class_info['classes'][name]for name in func_and_class_info['classes'].keys()}
            function_locs = {name: func_and_class_info['functions'][name]["location"] for name in func_and_class_info['functions'].keys()}
            class_locs = {name: func_and_class_info['classes'][name]["location"] for name in func_and_class_info['classes'].keys()}
            if len(retry_from_scratch) > 0:
                for test_name in retry_from_scratch:
                    verbose_log(f"\n  → Will re-use code generation prompt for test: [cyan]{test_name}[/cyan]")
                    # Re-create the prompt using the previously generated plan and the saved function and class dicts
                    test_plan = test_case_plans[test_name]

                    function_code_context = get_context_for_test_gen(
                        test_plan, function_dict, class_dict
                    )
                    prompt = generate_coder_prompt(
                        function_code_context,
                        f"{test_name}: {test_plan}"
                    )
                    prompts[test_name] = prompt
            if len(failed_tests) > 0:
                for test_name in failed_tests:
                    verbose_log(f"\n  → Generating refined prompt for failed test: [cyan]{test_name}[/cyan]")
                    # Get the original plan and the test result details
                    test_plan = test_case_plans[test_name]
                    # Note: currently the only detail we have is whether the test passed or failed
                    test_result_details = test_results_dict.get(test_name, None)
                    function_code_context = get_context_for_test_gen(
                        test_plan, function_dict, class_dict
                    )
                    # Create a refined prompt that includes information about the failure
                    # prompt = generate_coder_prompt(
                    #     function_code_context,
                    #     f"{test_name}: {test_plan}",
                    #     previous_test_result=test_result_details
                    # )
                    prompts[test_name] = prompt
            
            # for test_name, test_plan in test_case_plans.items():
            for test_name in retry_from_scratch + failed_tests:
                verbose_log(f"\n  → Generating test code for: [cyan]{test_name}[/cyan]")

                cleaned_response = generate_test_from_prompt(prompts[test_name], test_name, workspace.get_coder_output_dir())
                        
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
            
            # Make sure the functions to be tested are imported in the test file
            function_imports = get_function_imports(path, function_locs, class_locs)
            import_statements.update(function_imports)
            
            # Create a single file with all the test cases
            module_import_path = calculate_import_path_simple(path)
            combine_and_write_tests(test_cases, import_statements, Path(file_path), workspace.get_coder_output_dir(), module_import_path)

            workspace.set_status("CODE_GENERATED")

        test_filepath = os.path.join(workspace.get_coder_output_dir(), f"test_{path.stem}.py")
        console.print(f"\n[bold blue]Running generated tests in Docker container '{image_name}'[/bold blue]")
        test_results_dict = run_tests(test_filepath)
        # Save the test results to a json file
        workspace.save_test_results(test_results_dict)
        print(test_results_dict)
        workspace.update_remaining_tests([test for test in test_case_plans.keys() if test_results_dict.get(test, 'FAILED') == 'PASSED'])
        
        if len(test_results_dict) == 0:
            verbose_log(f"\n[bold red]No test results were parsed. Something went wrong.[/bold red]")
            breakpoint()
            verbose_log(f"[dim]Stopping here.[/dim]")
            return

        workspace.set_status("CODE_TESTED")
        workspace.next_coder_iteration()
        curr_attempts += 1

    
    

