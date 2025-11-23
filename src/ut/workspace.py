import os

class WorkspaceManager:
    def __init__(self, base_dir: str, fresh_start: bool = False) -> None:
        self.base_dir = base_dir
        self.planner_dir = self.create_subdirectory("planner")
        self.coder_dir = self.create_subdirectory("coder")
        self.resume_dir = self.create_subdirectory("resume")
        if fresh_start:
            self.set_status("START")
            self.coder_iteration = 0
        else:
            assert os.path.exists(self.get_planner_output_dir()), "Workspace does not contain planner output directory."
            self.coder_iteration = 0 # TODO: Make this dynamic based on existing iterations
            assert os.path.exists(self.get_coder_output_dir()), "Workspace does not contain coder output directory for iteration 0."

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
        
    # def get_coder_iteration_from_(self) -> int:

    def get_coder_output_dir(self) -> str:
        return os.path.join(self.coder_dir, f"iteration_{self.coder_iteration}")
    
    def get_planner_output_dir(self) -> str:
        return self.get_path("planner")
    
    def get_resume_dir(self) -> str:
        return self.get_path("resume")

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