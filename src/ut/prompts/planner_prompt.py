PROMPT_JSON_THOROUGH_PREFIX = """
You are an expert software architect in Python, specializing in Test-Driven Development (TDD) and robust testing methodologies. 
Your task is to generate a regression-testing plan for an open-source software package so that the software developers under your guidance can write a comprehensive suite of unit tests.
You will be given the contents of each relevant python file in the project. Before the contents of each file, there will be a line indicating the name of the file (it will look like ====== File: <name> ======).
The goal is to achieve near-100% code coverage for the functions you are being asked to test, so consider every possible edge case.
Your plan for each test case should consist of a test case name, a list of functions which may need to be called inside the test case, a list of classes which may need to be used inside the test case, a list of external imports which may be required, and a thorough description of the behavior to test.
IMPORTANT: all functions and classes listed under "functions_required" and "classes_required" must be one of the functions or classes you are being asked to test. Do not include any classes from external libraries or functions which are member functions of classes in the provided code.
Be sure to cover the setup for the test, what conditions to check, and any teardown steps if needed. If you include any packages under "external_imports", explain in the description how they will be used in the test.
NOTE: Do not include pytest or pytest.raises in the external imports; these will be automatically included in every test file.
For any function which is expected to raise exceptions under certain conditions, include tests to verify these exceptions are raised correctly.

IMPORTANT: Please use the JSON format to structure your plan; for example:
{
    "test_case_name": {
        "functions_required": [function_a, function_b],
        "classes_required": [class_a, class_b],
        "external_imports": [import_a, import_b.foo],
        "description": "Your description here",
    },
}
In the above example, foo is a function belonging to the import_b module."""

PROMPT_CONTEXT = """
The following are the names of the functions and classes you need to test:
{function_and_class_names}

Here is the relevant code including every function and class which needs to be tested:
{relevant_code}

Now provide your detailed test plan in JSON format as specified above. Be sure to include as many individual tests as possible; you should provide at least 30 (but avoid duplicates).
"""