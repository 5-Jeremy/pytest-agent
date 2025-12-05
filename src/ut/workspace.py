import os, pickle, json, shutil
from omegaconf import OmegaConf
from typing import Tuple
from src.ut.llm_client import parse_test_case_plan_json

class WorkspaceManager:
    def __init__(self, base_dir: str, fresh_start: bool = False, config_path: str = None) -> None:
        self.base_dir = base_dir
        self.planner_dir = self.create_subdirectory("planner")
        self.coder_dir = self.create_subdirectory("coder")
        self.resume_dir = self.create_subdirectory("resume")
        if fresh_start:
            if config_path is not None:
                # Copy the config file into the workspace
                shutil.copy(config_path, os.path.join(self.base_dir, "config.yaml"))
            self.set_status("START")
            self.coder_iteration = 0
        else:
            if not os.path.exists(self.get_planner_output_dir()):
                raise FileNotFoundError("Workspace does not contain planner output directory.")
            # Account for any previously completed coder iterations
            self.coder_iteration = self.get_last_completed_coder_iteration() + 1
            if not os.path.exists(self.get_coder_output_dir()):
                self.create_subdirectory(f"coder/iteration_{self.coder_iteration}")
            # If the status is CODE_GENERATED but the current coder iteration directory does not have a .py 
            # file, we need to ignore the status and generate new tests
            if self.get_status() == "CODE_GENERATED" and self.coder_iteration > 0:
                if len([f for f in os.listdir(self.get_coder_output_dir()) if f.endswith(".py")]) == 0:
                    self.set_status("CODE_TESTED")
   
    def set_status(self, status: str) -> None:
        assert status in ["START", "PLANNING_DONE", "CODE_GENERATED", "CODE_TESTED"], f"Invalid status: {status}"
        status_file_path = self.get_path("status.txt")
        # Overwrite any existing status
        with open(status_file_path, "w") as status_file:
            status_file.write(status)
    
    def get_status(self) -> str:
        status_file_path = self.get_path("status.txt")
        if os.path.exists(status_file_path):
            with open(status_file_path, "r") as status_file:
                return status_file.read().strip()
        else:
            raise FileNotFoundError(f"Status file not found at {status_file_path}")
        
    def next_coder_iteration(self) -> None:
        # Add a file marking the previous iteration as complete
        with open(os.path.join(self.get_coder_output_dir(), "DONE.txt"), "w") as marker_file:
            marker_file.write("DONE")
        self.coder_iteration += 1
        self.create_subdirectory(f"coder/iteration_{self.coder_iteration}")

    def get_last_completed_coder_iteration(self) -> int:
        """ Determines the last completed coder iteration based on the subfolders of coder_dir and the 
        presence of test_results.json. This is mainly used for resuming interrupted runs."""
        # List subdirectories in coder_dir
        subdirs = [d for d in os.listdir(self.coder_dir) if os.path.isdir(os.path.join(self.coder_dir, d))]
        subdirs_with_test_results = [d for d in subdirs if "test_results.json" in os.listdir(os.path.join(self.coder_dir, d))]
        if not subdirs_with_test_results:
            return -1  # No completed iterations
        # Extract iteration numbers and return the maximum
        iteration_numbers = [int(d.split("_")[1]) for d in subdirs_with_test_results if d.startswith("iteration_")]
        try:
            max_num = max(iteration_numbers)
        except ValueError:
            return -1
        return max_num
    
    # TODO: Eventually this data structure should fully replace lint_messages.json, test_results.json, 
    # test_feedback.json, and maybe remaining_tests.json
    def save_test_context(self, test_context: dict) -> None:
        with open(os.path.join(self.get_coder_output_dir(), "test_context.json"), "w") as f:
            json.dump(test_context, f)

    def load_test_context(self) -> dict:
        # We may need to look at the previous coder iteration for test results
        if os.path.exists(os.path.join(self.get_coder_output_dir(), "test_context.json")):
            target_dir = self.get_coder_output_dir()
        elif self.coder_iteration > 0 and os.path.exists(os.path.join(self.get_path("coder", f"iteration_{self.coder_iteration - 1}"), "test_context.json")):
            target_dir = self.get_path("coder", f"iteration_{self.coder_iteration - 1}")
        else:
            raise FileNotFoundError("Test context file not found in current or previous coder iteration directories.")
        with open(os.path.join(target_dir, "test_context.json"), "r") as f:
            test_context = json.load(f)
        return test_context

    # This function saves the imports and functions used in the final test file for each iteration
    def save_cur_imports_and_functions(self, imports: set, functions: dict) -> None:
        all_imports_and_funcs = {
            "imports": imports,
            "functions": functions
        }
        with open(os.path.join(self.get_coder_output_dir(), "all_imports_and_funcs.pkl"), "wb") as f:
            pickle.dump(all_imports_and_funcs, f)

    def load_cur_imports_and_functions(self) -> dict:
        if not os.path.exists(os.path.join(self.get_coder_output_dir(), "all_imports_and_funcs.pkl")):
            return {"imports": set(), "functions": {}}
        with open(os.path.join(self.get_coder_output_dir(), "all_imports_and_funcs.pkl"), "rb") as f:
            all_imports_and_funcs = pickle.load(f)
        return all_imports_and_funcs

    # Iterate through all coder iterations and load all imports and functions used
    def load_all_imports_and_functions(self) -> dict:
        all_imports = set()
        all_functions = {}
        last_completed_iteration = self.get_last_completed_coder_iteration()
        for iteration in range(last_completed_iteration + 1):
            iteration_dir = os.path.join(self.coder_dir, f"iteration_{iteration}")
            imports_and_funcs_path = os.path.join(iteration_dir, "all_imports_and_funcs.pkl")
            if os.path.exists(imports_and_funcs_path):
                with open(imports_and_funcs_path, "rb") as f:
                    imports_and_funcs = pickle.load(f)
                all_imports.update(imports_and_funcs.get("imports", set()))
                all_functions.update(imports_and_funcs.get("functions", {}))
        return {
            "imports": all_imports,
            "functions": all_functions
        }

    def save_linter_messages(self, lint_messages: dict) -> None:
        with open(os.path.join(self.get_coder_output_dir(), "lint_messages.json"), "w") as f:
            json.dump(lint_messages, f)
    
    def load_linter_messages(self) -> dict:
        lint_messages_path = os.path.join(self.get_coder_output_dir(), "lint_messages.json")
        if not os.path.exists(lint_messages_path):
            return {}
        with open(lint_messages_path, "r") as f:
            lint_messages = json.load(f)
        return lint_messages

    def load_all_test_results(self) -> dict:
        all_test_results = {}
        last_completed_iteration = self.get_last_completed_coder_iteration()
        for iteration in range(last_completed_iteration + 1):
            iteration_dir = os.path.join(self.coder_dir, f"iteration_{iteration}")
            test_results_path = os.path.join(iteration_dir, "test_results.json")
            if os.path.exists(test_results_path):
                with open(test_results_path, "r") as f:
                    test_results = json.load(f)
                all_test_results[iteration] = test_results
        return all_test_results

    def save_func_and_class_info(self, func_and_class_info: dict) -> None:
        with open(os.path.join(self.get_resume_dir(), "func_and_class_info.pkl"), "wb") as f:
            pickle.dump(func_and_class_info, f)

    def load_func_and_class_info(self) -> dict:
        assert os.path.exists(os.path.join(self.get_resume_dir(), "func_and_class_info.pkl")), "Function and class info file not found."
        with open(os.path.join(self.get_resume_dir(), "func_and_class_info.pkl"), "rb") as f:
            func_and_class_info = pickle.load(f)
        return func_and_class_info
    
    def save_test_results(self, test_results: dict, test_feedback: dict) -> None:
        with open(os.path.join(self.get_coder_output_dir(), "test_results.json"), "w") as f:
            json.dump(test_results, f)
        with open(os.path.join(self.get_coder_output_dir(), "test_feedback.json"), "w") as f:
            json.dump(test_feedback, f)
    
    def load_test_results(self) -> Tuple[dict, dict]:
        # We may need to look at the previous coder iteration for test results
        if os.path.exists(os.path.join(self.get_coder_output_dir(), "test_results.json")):
            target_dir = self.get_coder_output_dir()
        elif self.coder_iteration > 0 and os.path.exists(os.path.join(self.get_path("coder", f"iteration_{self.coder_iteration - 1}"), "test_results.json")):
            target_dir = self.get_path("coder", f"iteration_{self.coder_iteration - 1}")
        else:
            breakpoint()
            raise FileNotFoundError("Test results file not found in current or previous coder iteration directories.")
        with open(os.path.join(target_dir, "test_results.json"), "r") as f:
            test_results = json.load(f)
        with open(os.path.join(target_dir, "test_feedback.json"), "r") as f:
            test_feedback = json.load(f)
        return test_results, test_feedback
        return test_results, test_feedback

    # Update the file used to keep track of which planned tests have not yet passed
    def update_remaining_tests(self, new_passed_tests: list) -> None:
        # NOTE: I am using a json file right now even though there are no values, just in case I need to store
        # more info later.
        # If the remaining_tests.json file does not exist, we assume all tests are remaining and create it
        remaining_tests_path = os.path.join(self.get_resume_dir(), "remaining_tests.json")
        if os.path.exists(remaining_tests_path):
            with open(remaining_tests_path, "r") as f:
                past_remaining_tests = list(json.load(f).keys())
        else:
            past_remaining_tests = list(self.get_test_case_plans().keys())
        updated_remaining_tests = set(past_remaining_tests) - {test for test in new_passed_tests if test in past_remaining_tests}
        with open(remaining_tests_path, "w") as f:
            json.dump({test: True for test in updated_remaining_tests}, f)

    def get_remaining_tests(self) -> list:
        remaining_tests_path = os.path.join(self.get_resume_dir(), "remaining_tests.json")
        if os.path.exists(remaining_tests_path):
            with open(remaining_tests_path, "r") as f:
                remaining_tests = list(json.load(f).keys())
        else:
            raise FileNotFoundError("Remaining tests file not found.")
        return remaining_tests

    # This function loads the raw planner response and then parses it so it can return 
    def get_test_case_plans(self) -> dict:
        plan_path = None
        for file in os.listdir(self.get_planner_output_dir()):
            if file.startswith("planner_response_") and file.endswith(".txt"):
                plan_path = os.path.join(self.get_planner_output_dir(), file)
                break
        if plan_path is None:
            raise FileNotFoundError("Test case plan file not found in planner output directory.")
        with open(plan_path, "r") as f:
            plan = parse_test_case_plan_json(f.read())
        return plan

    def get_config(self):
        config_path = os.path.join(self.base_dir, "config.yaml")
        if not os.path.exists(config_path):
            raise FileNotFoundError("Config file not found in workspace.")
        config = OmegaConf.load(config_path)
        return config

    def get_coder_output_dir(self) -> str:
        return os.path.join(self.coder_dir, f"iteration_{self.coder_iteration}")
    
    def get_planner_output_dir(self) -> str:
        return self.get_path("planner")
    
    def get_resume_dir(self) -> str:
        return self.get_path("resume")

    def get_final_output_dir(self) -> str:
        self.create_subdirectory("final_output")
        return self.get_path("final_output")

    def check_for_logfile(self) -> bool:
        log_file_path = self.get_path("output.log")
        return os.path.exists(log_file_path)
    
    def get_log_path(self) -> str:
        return self.get_path("output.log")

    def get_path(self, *path_segments: str) -> str:
        return os.path.join(self.base_dir, *path_segments)

    # Any path you put into create_subdirectory should be relative to base_dir
    def create_subdirectory(self, sub_dir_name: str) -> str:
        sub_dir_path = self.get_path(sub_dir_name)
        os.makedirs(sub_dir_path, exist_ok=True)
        return sub_dir_path