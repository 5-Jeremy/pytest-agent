"""
Module for running pytest tests in a Docker container sandbox using Docker SDK.
"""

import docker
from docker.errors import DockerException, NotFound, APIError
import os
import tarfile
import io
from typing import Optional, Dict, Any
from pathlib import Path

from rich.console import Console
console = Console()

from ut.results_parser import parse_pytest_output

class DockerTestRunner:
    """
    Manages a persistent Docker container for running pytest tests.
    
    The container is started once and remains running, allowing multiple
    test runs without the overhead of container startup/teardown.
    """
    
    def __init__(
        self,
        image_name: str,
        container_name: str = "pytest-runner",
        test_dir_in_container: str = "/tmp/tests",
        working_dir: Optional[str] = None
    ):
        """
        Initialize the Docker test runner.
        
        Args:
            image_name: Name of the Docker image to use
            container_name: Name for the running container (default: "pytest-runner")
            test_dir_in_container: Directory path inside container where tests will be copied
            working_dir: Working directory inside container where pytest will run (defaults to test_dir_in_container)
        """
        self.image_name = image_name
        self.container_name = container_name
        self.test_dir_in_container = test_dir_in_container
        self.working_dir = working_dir or test_dir_in_container
        self.client = docker.from_env()
        self.container = None
        self._is_running = False
    
    def start_container(self, **kwargs) -> bool:
        """
        Start the Docker container and keep it running.
        
        Args:
            **kwargs: Additional keyword arguments for docker.containers.run()
                     (e.g., volumes={'/host/path': {'bind': '/container/path', 'mode': 'rw'}})
        
        Returns:
            True if container started successfully, False otherwise
        """
        if self._is_running and self.container:
            print(f"Container {self.container_name} is already running")
            return True
        
        try:
            # Check if container already exists
            try:
                self.container = self.client.containers.get(self.container_name)
                
                # If container exists but is not running, start it
                if self.container.status != 'running':
                    print(f"Container {self.container_name} exists, attempting to start...")
                    self.container.start()
                    self._is_running = True
                    self._create_test_directory()
                    print(f"Container {self.container_name} started successfully")
                    return True
                else:
                    self._is_running = True
                    print(f"Container {self.container_name} is already running")
                    return True
                    
            except NotFound:
                # Container doesn't exist, create a new one
                print(f"Creating new container {self.container_name}...")
                
                # Default parameters
                run_params = {
                    'image': self.image_name,
                    'name': self.container_name,
                    'detach': True,
                    'command': ['tail', '-f', '/dev/null'],  # Keep container running
                    'remove': False,  # Don't auto-remove so we can restart it
                }
                
                # Merge with user-provided kwargs
                run_params.update(kwargs)
                
                self.container = self.client.containers.run(**run_params)
                self._is_running = True
                
                # Create the test directory inside the container
                self._create_test_directory()
                
                print(f"Container {self.container_name} started successfully")
                return True
                
        except DockerException as e:
            print(f"Failed to start container: {e}")
            return False
    
    def _create_test_directory(self):
        """Create the test directory inside the container."""
        if self.container:
            self.container.exec_run(f"mkdir -p {self.test_dir_in_container}")
    
    def stop_container(self, remove: bool = True) -> bool:
        """
        Stop and optionally remove the Docker container.
        
        Args:
            remove: Whether to remove the container after stopping (default: True)
        
        Returns:
            True if container stopped successfully, False otherwise
        """
        if not self._is_running or not self.container:
            return True
        
        try:
            self.container.stop(timeout=10)
            
            if remove:
                self.container.remove()
            
            self._is_running = False
            self.container = None
            print(f"Container {self.container_name} stopped successfully")
            return True
            
        except Exception as e:
            print(f"Error stopping container: {e}")
            # Force remove if normal stop fails
            try:
                if self.container:
                    self.container.remove(force=True)
            except:
                pass
            self._is_running = False
            self.container = None
            return False
    
    def _exec_command(self, command: str) -> tuple[int, str]:
        """
        Execute a command inside the running container.
        
        Args:
            command: Command to execute
        
        Returns:
            Tuple of (exit_code, output) where output combines stdout and stderr
        """
        if not self._is_running or not self.container:
            raise RuntimeError("Container is not running. Call start_container() first.")
        
        exec_result = self.container.exec_run(
            command,
            workdir=self.working_dir,
            demux=False  # Combine stdout and stderr
        )
        
        exit_code = exec_result.exit_code
        output = exec_result.output.decode('utf-8') if exec_result.output else ""
        
        return exit_code, output
    
    def copy_tests_to_container(self, test_file_path: str) -> bool:
        """
        Copy a test file into the container.
        
        Args:
            test_file_path: Path to the test file on the host system
        
        Returns:
            True if copy was successful, False otherwise
        """
        if not self._is_running or not self.container:
            raise RuntimeError("Container is not running. Call start_container() first.")
        
        if not os.path.exists(test_file_path):
            raise FileNotFoundError(f"Test file not found: {test_file_path}")
        
        try:
            # Read the test file
            with open(test_file_path, 'rb') as f:
                file_data = f.read()
            
            # Create a tar archive in memory
            tar_stream = io.BytesIO()
            tar = tarfile.open(fileobj=tar_stream, mode='w')
            
            # Add file to tar archive
            tarinfo = tarfile.TarInfo(name=os.path.basename(test_file_path))
            tarinfo.size = len(file_data)
            tarinfo.mode = 0o644
            tar.addfile(tarinfo, io.BytesIO(file_data))
            tar.close()
            
            # Put the tar archive into the container
            tar_stream.seek(0)
            self.container.put_archive(self.test_dir_in_container, tar_stream)
            
            return True
            
        except Exception as e:
            print(f"Failed to copy test file: {e}")
            return False
    
    def copy_file_from_container(self, container_file_path: str, host_destination: str) -> bool:
        """
        Copy a file from the container to the host system.
        
        Args:
            container_file_path: Full path to the file inside the container
            host_destination: Path on the host where the file should be saved (can be a directory or file path)
        
        Returns:
            True if copy was successful, False otherwise
        """
        if not self._is_running or not self.container:
            raise RuntimeError("Container is not running. Call start_container() first.")
        
        try:
            # Get the file as a tar archive from the container
            bits, stat = self.container.get_archive(container_file_path)
            
            # Read the tar archive
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            # Extract the file from tar
            tar = tarfile.open(fileobj=tar_stream)
            
            # Determine output path
            if os.path.isdir(host_destination):
                # If destination is a directory, use the original filename
                filename = os.path.basename(container_file_path)
                output_path = os.path.join(host_destination, filename)
            else:
                # If destination is a file path, use it directly
                output_path = host_destination
                # Create parent directory if it doesn't exist
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Extract and save the file
            member = tar.getmembers()[0]
            file_obj = tar.extractfile(member)
            
            if file_obj:
                with open(output_path, 'wb') as f:
                    f.write(file_obj.read())
                return True
            else:
                raise Exception(f"File {container_file_path} not found in container archive")
            
        except NotFound:
            print(f"File not found in container: {container_file_path}")
            return False
        except Exception as e:
            print(f"Failed to copy file from container: {e}")
            return False
    
    def run_pytest(
        self,
        test_file_path: Optional[str] = None,
        pytest_args: Optional[list] = None,
        copy_first: bool = True
    ) -> str:
        """
        Run pytest in the container and return the results as a string.
        
        Args:
            test_file_path: Path to test file on host (will be copied if copy_first=True)
            pytest_args: Additional pytest arguments (e.g., ["-v", "-s"])
            copy_first: Whether to copy the test file before running (default: True)
        
        Returns:
            String containing pytest output (stdout and stderr combined)
        """
        if not self._is_running or not self.container:
            raise RuntimeError("Container is not running. Call start_container() first.")
        
        # Copy test file if requested
        if copy_first and test_file_path:
            if not self.copy_tests_to_container(test_file_path):
                return "Error: Failed to copy test file to container"
        
        # Build pytest command
        pytest_cmd_parts = ["python", "-m", "pytest"]
        
        if pytest_args:
            pytest_cmd_parts.extend(pytest_args)
        else:
            # Default arguments for clear output
            pytest_cmd_parts.extend(["--cov", "--cov-report", "json:cov.json", "-v", "--tb=short"])
        
        # Add specific test file if provided
        if test_file_path:
            test_filename = os.path.basename(test_file_path)
            # Use the full path in the container (test_dir_in_container + filename)
            container_test_path = f"{self.test_dir_in_container}/{test_filename}"
            pytest_cmd_parts.append(container_test_path)
        
        pytest_cmd = " ".join(pytest_cmd_parts)
        
        # Execute pytest
        exit_code, output = self._exec_command(pytest_cmd)

        # Copy the cov.json file back to host if it exists
        if exit_code in [0, 1] and test_file_path:
            cov_file_in_container = f"{self.working_dir}/cov.json"
            cov_report_host_path = os.path.join(Path(test_file_path).parent, "cov.json")
            if self.copy_file_from_container(cov_file_in_container, cov_report_host_path):
                print(f"Coverage report copied to {cov_report_host_path}")

        # Delete the test file if it was copied in
        if copy_first and test_file_path:
            test_filename = os.path.basename(test_file_path)
            container_tests_file = f"{self.test_dir_in_container}/{test_filename}"
            self._exec_command(f"rm -f {container_tests_file}")
        
        return output if output else "No output from pytest"
    
    def is_running(self) -> bool:
        """Check if the container is currently running."""
        if not self.container:
            self._is_running = False
            return False
        
        try:
            # Refresh container state
            self.container.reload()
            is_running = self.container.status == 'running'
            self._is_running = is_running
            return is_running
        except NotFound:
            self._is_running = False
            self.container = None
            return False
        except Exception:
            return False
    
    def get_container_logs(self, tail: Optional[int] = None) -> str:
        """
        Get logs from the container.
        
        Args:
            tail: Number of lines from the end of logs to show (default: all logs)
        
        Returns:
            Container logs as a string
        """
        if not self.container:
            return "No container available"
        
        try:
            logs = self.container.logs(tail=tail).decode('utf-8')
            return logs
        except Exception as e:
            return f"Error getting logs: {e}"
    
    def __enter__(self):
        """Context manager entry - starts the container."""
        self.start_container()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stops the container."""
        self.stop_container()
        return False
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            if self._is_running and self.container:
                self.stop_container()
        except:
            pass

def run_tests(test_filepath: str, test_dir: str, image_name: str, verbose: bool = False) -> dict:
    # The working directory is where pytest will be run from
    # Be default we assume that the directory for tests is inside the working directory, so if no working dir is specified we derive it from test_dir
    test_runner = DockerTestRunner(image_name=image_name, 
                                    container_name="ut_generate", 
                                    test_dir_in_container=test_dir, 
                                    working_dir=Path(test_dir).parent.as_posix()
    )
    test_runner.start_container()
    test_results_string = test_runner.run_pytest(test_filepath)
    if verbose:
        console.print(f"\n[bold green]Test output:[/bold green]\n{test_results_string}\n")
    test_results_dict, test_feedback = parse_pytest_output(test_results_string)
    return test_results_dict, test_feedback

def remove_error_source(test_filepath: str, source, type: str):
    # Remove the line that caused the error from the test file
    with open(test_filepath, "r") as f:
        lines = f.readlines()

    if type == "line":
        line_num = source
        if line_num < 1 or line_num > len(lines):
            raise ValueError(f"Line number {line_num} is out of range for file with {len(lines)} lines.")
        # If there is a line which comes before line_num that starts with "def test_", remove everything 
        # from that line to the next line that starts with "def test_" or the end of the file
        start_index = None
        for i in range(line_num-1, -1, -1):
            if lines[i].startswith("def test_"):
                start_index = i
                break
        if start_index is None:
            # The error was probably caused by a malformed import; just remove line_num
            del lines[line_num-1]
        else:
            end_index = None
        for j in range(line_num, len(lines)):
            if lines[j].startswith("def test_"):
                end_index = j
                break
        if end_index is None:
            del lines[start_index:]
        else:
            # We delete all lines up to but not including end_index (which is the start of the next test)
            del lines[start_index:end_index]
    elif type == "import":
        module_name = source
        # Only consider lines before the first "def test_" statement
        first_test_index = None
        for i, line in enumerate(lines):
            if line.startswith("def test_"):
                first_test_index = i
                break
        if first_test_index is not None:
            # Find and remove any import statements that reference the module_name
            lines = [line for line in lines[:first_test_index] if module_name not in line] + lines[first_test_index:]

    with open(test_filepath, "w") as f:
        f.writelines(lines)

def run_tests_with_error_removal(test_filepath: str, config: dict):
    """
    Repeatedly attempts to run the given test file in the Docker container. If an error occurs which prevents
    the tests from running (e.g., syntax error ir ImportError), it removes the offending test or import 
    statement and retries until the tests run or no tests remain.
    """
    test_dir = config['project'].get('test_dir_in_container', None)
    image_name = config['project'].get('docker_image_name', None)
    test_results_dict, test_feedback = run_tests(test_filepath, test_dir, image_name)
    #####################################################################
    """ Try to fix errors; TODO: make it a repeated cycle """
    while test_results_dict is None:
        console.print(f"\n[bold red]Error detected that prevented tests from running.[/bold red]")
        try:
            if type(test_feedback) == int:
                line_num = test_feedback
                console.print(f"\n[bold blue]Attempting to remove source of error on line {line_num}.[/bold blue]")
                remove_error_source(test_filepath, line_num, type="line")
            elif type(test_feedback) == str:
                module_name = test_feedback
                console.print(f"\n[bold blue]Attempting to remove invalid import '{module_name}'.[/bold blue]")
                remove_error_source(test_filepath, module_name, type="import")
            test_results_dict, test_feedback = run_tests(test_filepath, test_dir, image_name)
        except:
            console.print(f"[bold red]Attempt to fix error failed.[/bold red]")
            return None, None
    return test_results_dict, test_feedback

# Example usage
if __name__ == "__main__":
    # Example 1: Basic usage
    runner = DockerTestRunner(
        image_name="unittest:example",
        container_name="test-runner",
        test_dir_in_container="/code/example/tests",
        working_dir="/code/example"
    )
    
    try:
        # Start container once
        runner.start_container()
        
        # Test
        result1 = runner.run_pytest("example/tests/test_example.py")
        print("Test Run 1 Results:")
        print(result1)
        breakpoint()
        print("\n" + "="*80 + "\n")
        
        # result2 = runner.run_pytest("/path/to/test_file2.py")
        # print("Test Run 2 Results:")
        # print(result2)
        
    finally:
        # Clean up
        runner.stop_container()
    
    # # Example 2: Using context manager
    # print("\n" + "="*80 + "\n")
    # print("Using context manager:")
    
    # with DockerTestRunner("your-docker-image:latest", "test-runner-2") as runner:
    #     result = runner.run_pytest("/path/to/test_file.py")
    #     print(result)
    
    # # Example 3: With volume mounting
    # print("\n" + "="*80 + "\n")
    # print("With volume mounting:")
    
    # runner3 = DockerTestRunner("your-docker-image:latest", "test-runner-3")
    # runner3.start_container(
    #     volumes={
    #         '/host/data': {'bind': '/container/data', 'mode': 'ro'}
    #     }
    # )
    # result = runner3.run_pytest("/path/to/test_file.py", pytest_args=["-v", "-s", "--maxfail=1"])
    # print(result)
    # runner3.stop_container()
