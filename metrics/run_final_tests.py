
""" This script executes the final set of tests from a workspace to confirm that they all pass. """

import os, argparse, sys
from src.ut.workspace import WorkspaceManager
from src.ut.test_runner import DockerTestRunner
from src.ut.results_parser import parse_pytest_output
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Execute the final set of tests from a workspace to confirm that they all pass.")
    parser.add_argument("dir", type=str, help="Path to a workspace.")
    return parser.parse_args()

def run_tests(test_filepath: str, test_dir: str, image_name: str) -> dict:
    # The working directory is where pytest will be run from
    # Be default we assume that the directory for tests is inside the working directory, so if no working dir is specified we derive it from test_dir
    test_runner = DockerTestRunner(image_name=image_name, 
                                    container_name="ut_generate", 
                                    test_dir_in_container=test_dir, 
                                    working_dir=Path(test_dir).parent.as_posix()
)
    test_runner.start_container()
    test_results_string = test_runner.run_pytest(test_filepath)
    test_results_dict, test_feedback = parse_pytest_output(test_results_string)
    return test_results_dict, test_feedback

if __name__ == "__main__":
    # Some of the functions called here will add unnecessary output unless we disable it
    os.environ["UT_VERBOSE"] = "0"
    os.environ["UT_LOG_FILE"] = "None"
    args = parse_args()
    directory_path = args.dir
    try:
        workspace = WorkspaceManager(base_dir=directory_path, fresh_start=False)
        # Get the config
        config = workspace.get_config()
    except FileNotFoundError as e:
        print(f"Invalid workspace: {e}")
        exit(1)

    test_filepath = os.path.join(workspace.get_final_output_dir(), "final_tests.py")
    image_name = config['project'].get('docker_image_name', None)

    test_results, test_feedback = run_tests(
        test_filepath=test_filepath,
        test_dir=config['project'].get('test_dir_in_container', None),
        image_name=image_name
    )

    print("Number of tests run:", len(test_results))
    assert all(result == "PASSED" for result in test_results.values()), "Found a test which failed."