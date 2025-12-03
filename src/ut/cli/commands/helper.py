"""Helper functions for CLI commands."""
from rich.console import Console
import os

def verbose_message(message: str, print_func: Console) -> None:
    """Print a message if verbose is enabled.

    Args:
        message (str): The message to print.
        print_func (Console): The print function to use
            (e.g., console.print or console.log).
    """
    if "UT_VERBOSE" in os.environ and os.environ["UT_VERBOSE"] == "1":
        print_func(message)


def verbose_print(message: str):
    """Print a message if verbose is enabled.

    Args:
        message (str): The message to print.
    """
    verbose_message(message, Console().print)


def verbose_log(message: str):
    """Print a log message if verbose is enabled.
    This also gets written to the output log file.

    Args:
        message (str): The message to log.
    """
    verbose_message(message, Console().log)
    if os.environ['UT_LOG_FILE'] == "None":
            return
    # Create log file if it doesn't exist
    if not os.path.exists(os.environ['UT_LOG_FILE']):
        try:
            logfile = open(os.environ['UT_LOG_FILE'], "w")
        except Exception as e:
            verbose_message(f"[bold red]Error creating log file: {e}[/bold red]", Console().log)
            return
    else:
        logfile = open(os.environ['UT_LOG_FILE'], "a")
    verbose_message(message, Console(file=logfile).log)

def clean_temp_files():
    """Remove temporary files and directories created during test generation.
    """
    import subprocess

    verbose_print("\n[dim]Cleaning up temporary files...[/dim]")

    # Commands to clean up common Python temporary files and directories
    commands = [
        "find . -type f -name '*.pyc' -delete",
        "find . -type d -name '__pycache__' -exec rm -rf {} +",
        "find . -type d -name '*.egg-info' -exec rm -rf {} +",
        "find . -type f -name '.coverage' -delete",
        "find . -type d -name 'htmlcov' -exec rm -rf {} +",
        "find . -type d -name '.pytest_cache' -exec rm -rf {} +",
        "find . -type d -name '.mypy_cache' -exec rm -rf {} +",
        "find . -type d -name '.ruff_cache' -exec rm -rf {} +",
    ]

    for command in commands:
        try:
            subprocess.run(
                command, shell=True, check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError:
            pass
