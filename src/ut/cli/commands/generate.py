"""Automated Unit Test Generation CLI with AI."""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ut.cli.commands.file_processor import process_file, process_project
from ut.cli.commands.helper import clean_temp_files, verbose_log
from ut.llm_client import is_vllm_running
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
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
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
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Do not warn about overwriting existing files in the output directory",
    )
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
    if workspace.get_status() not in ["CODE_GENERATED", "CODE_TESTED"]:
        if path.is_file():
            console.print(f"[bold blue]Processing single file: {path.name}[/bold blue]")
            if no_collab:
                console.print(
                    "[bold red]Error: Non-collaborative mode has not been fixed yet; logging is not correctly set up.[/bold red]"
                )
                raise typer.Exit(1)
                # process_file(path, output_base, mirror_structure, dry_run)
            else:
                process_project(path, output_base, mirror_structure, dry_run, conf, workspace)

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
                process_project(path, output_base, mirror_structure, dry_run, conf, workspace)

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
    else:
        console.print(f"[bold blue]Test code is already generated. Running tests...[/bold blue]")

    # Save test_cases to a file in case we need to resume later; note that test_case_plans can be extracted
    # from the logged files
    # log_dir = workspace.get_resume_dir()
    # pickle.dump(test_cases, open(os.path.join(log_dir, "test_cases.pkl"), "wb"))

    ### Run the generated tests inside a Docker container
    test_report_save_dir = workspace.get_coder_output_dir()
    image_name = conf.get('project', {}).get('docker_image_name', None)
    if image_name is not None:
        assert 'test_dir_in_container' in conf['project']
        test_dir = conf['project']['test_dir_in_container']
        console.print(f"\n[bold blue]Running generated tests in Docker container '{image_name}'[/bold blue]")
        # The working directory is where pytest will be run from
        # Be default we assume that the directory for tests is inside the working directory, so if no working dir is specified we derive it from test_dir
        test_runner = DockerTestRunner(image_name=image_name, container_name="ut_generate", test_dir_in_container=test_dir, working_dir=conf['project'].get('working_dir', Path(test_dir).parent.as_posix()))
        test_runner.start_container()
        test_results_string = test_runner.run_pytest(os.path.join(output_base, f"test_{path.stem}.py"))
        test_results_dict = parse_pytest_output(test_results_string)
        # Save the test results to a json file
        json.dump(test_results_dict, open(os.path.join(test_report_save_dir, "test_results.json"), "w"))
        print(test_results_dict)
    else:
        console.print(f"\n[bold yellow]Skipping test execution: No Docker image specified in configuration.[/bold yellow]")
        console.print(f"[dim]Stopping here.[/dim]")
        return
    
    if len(test_results_dict) == 0:
        console.print(f"\n[bold red]No test results were parsed. Something went wrong.[/bold red]")
        console.print(f"[dim]Stopping here.[/dim]")
        return
    

