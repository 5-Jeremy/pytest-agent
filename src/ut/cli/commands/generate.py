"""Automated Unit Test Generation CLI with AI."""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ut.cli.commands.file_processor import process_file, process_project
from ut.cli.commands.helper import clean_temp_files
from ut.llm_client import is_vllm_running
from omegaconf import OmegaConf
import os

console = Console()


def generate(
    file_path: str = typer.Argument(
        ".", help="Path to source file or directory. Use '.' for current directory"
    ),
    output_dir: Optional[str] = typer.Option(
        "ut_output",
        "--output",
        "-o",
        help="Output directory for generated tests (default: ut_output/)",
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
        "old_prompt",
        "--config",
        "-c",
        help="Configuration name for prompt templates and settings",
    ),
    plan_path: Optional[str] = typer.Option(
        None,
        "--plan-path",
        help="Path to a predefined test plan file (overrides initial planning step)",
        metavar="FILE_PATH"
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

    # Clean up temporary files
    clean_temp_files(verbose=False)

    # Get config
    if ".yaml" not in config_name:
        config_name += ".yaml"
    conf = OmegaConf.load(os.path.join("configs", config_name))
    if plan_path is not None:
        conf['predefined_plan_path'] = plan_path
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

    if not output_dir:
        console.print(
            "[bold red]Error: The output directory cannot be empty.[/bold red]"
        )
        raise typer.Exit(code=1)

    path = Path(file_path).resolve()
    output_base = Path(output_dir).resolve()

    if not dry_run:
        console.print(f"[bold cyan]📁 Output directory: {output_base}/[/bold cyan]")
        if output_base.exists() and any(output_base.iterdir()):
            console.print(
                "[yellow]⚠️  Output directory exists and contains files[/yellow]"
            )
            if not typer.confirm("Continue and potentially overwrite existing files?"):
                raise typer.Exit(0)

    is_not_python_file = path.is_file() and not path.suffix == ".py"

    if is_not_python_file:
        console.print(f"[bold red]Error: {path} is not a Python file[/bold red]")
        raise typer.Exit(1)

    if path.is_file():
        console.print(f"[bold blue]Processing single file: {path.name}[/bold blue]")
        if no_collab:
            process_file(path, output_base, mirror_structure, verbose, dry_run)
        else:
            process_project(path, output_base, mirror_structure, verbose, dry_run, conf)

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
            process_project(path, output_base, mirror_structure, verbose, dry_run, conf)

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
        console.print("\n[bold cyan]Next steps:[/bold cyan]")
        console.print("1. Review generated tests in the output directory")
        console.print("2. Copy relevant tests to your project's test directory")
        console.print("3. Adjust import paths if necessary")
        console.print(f"4. Run: [dim]pytest {output_dir}/[/dim] to test them")
    else:
        console.print("\n[yellow]Dry run completed. No files were created.[/yellow]")
