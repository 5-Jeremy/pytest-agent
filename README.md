# Pytest Agent

Pytest Agent is a fork of [unittest-ai-agent](https://github.com/herchila/unittest-ai-agent) which aims to automatically generate a suite of test cases for the purposes of regression testing through collaboration between a highly capable LLM which is expensive to query and a smaller LLM which is cheap to query. Since the target application is regression testing, the focus is on generating tests which confirm to the behavior of the existing code (which is assumed to be correct) while maximizing the code coverage. The collaboration consists of the large LLM (called the planner) creating a list of concise plans for test cases in a single query and the small LLM (called the coder) generating a complete test case to fulfill each plan, using guidance from the large LLM as context. Since the small LLM is cheap to query, it is given multiple attempts to generate a correct test (i.e. one which the given code passes) and takes in feedback to refine its code each time it fails. This project focuses on python code and uses the [pytest](https://github.com/pytest-dev/pytest) framework.

Note that this repository is a work-in-progress, so updates are expected to come out in the future.

## Additional Info

A detailed report of the project can be found in this repo under "Project Report.pdf". Note that you may need to download the file in order to use the hyperlinks. There is also a demonstration video of how to run Pytest Agent which you can find [here](https://www.youtube.com/watch?v=urBM6bGjup0).

## Setup

1. **Environment setup:**
   To setup the virtualenv, you will need a python environment with poetry installed (version 2.3.2 is what I have used). Simply run `poetry install` and `source .venv/bin/activate`.

2. **Setup project files**
   The code you are generating tests for must have a config file and a DockerFile tailored for that particular project. Various examples can be found in the configs/ and eval_dockerfiles/ directories. If you simply want to test Pytest Agent on one of these sample projects, you can use those existing files. Otherwise, see the "Config File Structure" and "DockerFile Setup" sections below.

3. **Setup Local Copy of Code to Test**
   Under the top-level directory of this repo, you will need to create a subdirectory called `eval_repos`. If you are working with a repo hosted on GitHub, clone it within that subdirectory. Otherwise, manually copy the project's source code into a folder under the subdirectory. The context for the LLMs will be taken from this folder, and a copy of the folder will be placed inside the docker container where tests are run. Ideally the project should be installable as a python package using `pip install -e`; if it is not, you will have to be careful about making the code importable from the directory where tests are run.

4. **Build the Docker image for the code under evaluation**
   For example, to run Pytest Agent on the parse project:
   ```sh
     docker build -t unittest:parse -f eval_dockerfiles/parse/Dockerfile .
     ```

5. **Setup the LLMs**
   This project uses Simon Willison’s [llm library](https://github.com/simonw/LLM) to query the planning LLM, mainly to ensure compatibility with TAMUS AI Chat. Follow the instructions in that repo's README to register your API key with llm, and put the name of the model you will be querying under `LLM_MODEL_NAME` in your .env file. If you will be accessing the model through TAMU AI Chat, run llm_setup_model.sh beforehand to get a list of names for available models.

6.  **Start the VLLM server**
   To start a VLLM server that the program can make requests to, run
   ```sh
   bash start_vllm_servers.sh <num_GPUS>
   ```
   Since Pytest Agent generates many coder requests in parallel, it is recommended to run the server on as many GPUs as you have available to maximize throughput. Note that you need to set CODER_MODEL_NAME in your .env to match MODEL_NAME on line 11 of start_vllm_servers.sh ("Qwen/Qwen2.5-Coder-32B-Instruct" by default).

## Generating tests

**Run the test generator:**
```sh
poetry run ut generate <path_to_repo> -c <config_name>
```

The code will search for config files in the configs/ directory. All outputs will be placed in a subdirectory of Workspaces/. Each run creates its own subdirectory (referred to as its workspace).

If you wish to reuse test case plans from a previous run on the same project, simply include the `--plan_path` argument with the path to the planner_response_xxx.txt file which is located in the planner subdirectory of the workspace for the previous run.

## Executing the Final Set of Tests
This will verify that all tests pass, and also write a coverage report file to the final_output directory. 
```sh
python -m metrics.run_final_tests <path_to_workspace>
```

## Viewing Test Case Pass Rates
This will print a summary of the test case pass rates across iterations to the console, and also produce a PNG image of the plot (unless you include the --no-save flag).
```sh
python -m metrics.calc_pass_rates <path_to_workspace>
```

## Viewing Coverage Statistics
This will parse the coverage report generated by pytest-cov and print statistics to the console.
```sh
python -m metrics.calc_coverage_stats <path_to_cov.json>
```

## Config File Structure
The config file has 3 top-level keys: planner, coder, and project. 

Under planner, you can specify the format which the planner model will be prompted to output its plan in (the recommended value is 'json'). If you have a custom prompt for the planner, you can put it in a text file within the configs directory and set prompt_file to the name of that file. 

Under coder, you can also specify a custom prompt; furthermore, you can specify the maximum number of attempts for generating code under the max_attempts key. A good value to use is 3 since in my experience, there is not likely to be significant improvement in code coverage after the third attempt. 

Under project, you must provide details specific to the code that you are generating tests for.
- `module_name`: This is the name used for imports  (e.g. from *module_name* import *). This must be set correctly so that the generated pytest file can import the functions and classes to be tested.
- `docker_image_name`: The name of the docker image to use when spinning up the container that tests will be run in. Make sure this matches whatever tag you used in your docker build command.
- `test_dir_in_container`: Which directory inside the docker container tests should be run in. This can be a folder in the same directory where the folder containing the source code is located.
- `include_init_files`: Whether to provide `__init__.py` files as context to the planner. Unless this is set to True, they will be ignored by the planner (which is fine in most cases because those files usually do contain any function or class definitions).
- `extra_ignore_list`: A list of files and directories in the code under test which should not be used to extract context for the planner. Directories that do not contain any .py files will already be ignored, but in cases where there are .py files which you do not want inside the context (either because it is very long and not particularly relevant, or because it contains existing unit tests which you do not want to treat as part of the code), you should list them here.
- `names_to_test`: The list of functions and classes that you want tests generated for.

## DockerFile Setup
Your docker image should start from an image that has the right python version for the code under test installed (e.g. python:3.9-slim if you are using python 3.9). Then you should set a working directory, copy the code under test to that directory, and remove any files which you do not want to be present (mainly this applies to existing test harnesses that are present; you do not want pytest to run them in addition to the generated tests). Finally, you should install any python packages needed to run the code (including the packages provided by the code itself, if any, installed in editable mode) along with the pytest and pytest-cov packages. See the sample DockerFiles under eval_dockerfiles/ for concrete examples.

## Prompt Customization
All prompts are located in src/ut/prompts/ (only the .py files are used; the .txt files are obsolete).

