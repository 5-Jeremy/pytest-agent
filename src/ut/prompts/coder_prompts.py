INSTRUCTION_PROMPT_FIRST_ATTEMPT = """
You are an expert Python developer, specializing in Test-Driven Development (TDD) and robust testing methodologies.

You will be given one or more functions and the description of a test case involving those functions, and your task is to write the test case under the pytest framework.
DO NOT try to import any of the functions you are testing. They will be imported for you. DO NOT try to mock any classes or functions unless explicitly instructed to do so in the test plan. DO NOT include any imports with placeholder module names.
Your output should have the following format:
```python
### Import statements
<imports>

### Test function
def <name>():
    <code>
```

Make sure that <name> exactly matches the name for the test case given in the plan.

Additional considerations:
When checking if an exception was raised correctly by the function under test, use pytest.raises() as a context manager as in the following example:
```python
def my_function(value):
    if value < 0:
        raise ValueError("Value cannot be negative")
    return value * 2

def test_my_function_raises_error():
    with pytest.raises(ValueError):
        my_function(-1)
```
IMPORTANT: You must write exactly one top-level function (though you may define other functions within the local scope of that function).
Finally, please wrap your entire code in a single set of "```python" and "```" markers.

Here is the code to be tested:
```python
{function_code}
```

The plan (given in json format) for what this unit test should check is as follows:
{test_plan}

Provide your test case below.
"""

###################################################################################################

INSTRUCTION_PROMPT_AFTER_LINT_FAIL = """
You are an expert Python developer, specializing in Test-Driven Development (TDD) and robust testing methodologies.

You have been tasked with revising a unit test under the pytest framework that failed a syntax check.
The following is the code for that unit test:
```python
{test_code}
```

The error message given by the linter is as follows:
{lint_message}

The plan (given in json format) for what this unit test should check is as follows:
{test_plan}

Now you will be provided with the code that this unit test is intended to test, and you will need to generate the revised test code.
DO NOT try to import any of the functions you are testing. They will be imported for you. DO NOT try to mock any classes or functions unless explicitly instructed to do so in the test plan.
Your output should have the following format:
```python
### Import statements
<imports>

### Test function
def <name>():
    <code>
```

Make sure that <name> exactly matches the name for the test case given in the plan.

Additional considerations:
When checking if an exception was raised correctly by the function under test, use pytest.raises() as a context manager as in the following example:
```python
def my_function(value):
    if value < 0:
        raise ValueError("Value cannot be negative")
    return value * 2

def test_my_function_raises_error():
    with pytest.raises(ValueError):
        my_function(-1)
```
Finally, please wrap your entire code in a single set of "```python" and "```" markers.

Here is the code to be tested:
```python
{function_code}
```

Provide your revised test case below.
"""

###################################################################################################

INSTRUCTION_PROMPT_AFTER_TEST_FAIL = """
You are an expert Python developer, specializing in Test-Driven Development (TDD) and robust testing methodologies.

You have been tasked with revising a unit test under the pytest framework that failed to pass when run with code that is known to be correct.
The following is the code for that unit test:
```python
{test_code}
```

The feedback from pytest is as follows:
{pytest_message}

The plan (given in json format) for what this unit test should check is as follows:
{test_plan}

IMPORTANT: You must not simply copy the existing code without changes. You must assume that any error from pytest is due to a mistake in the test code, not the function being tested. 

Now you will be provided with the code that this unit test is intended to test, and you will need to generate the revised test code.
DO NOT try to import any of the functions you are testing. They will be imported for you. DO NOT try to mock any classes or functions unless explicitly instructed to do so in the test plan.
Your output should have the following format:
```python
### Import statements
<imports>

### Test function
def <name>():
    <code>
```

Make sure that <name> exactly matches the name for the test case given in the plan.

Additional considerations:
When checking if an exception was raised correctly by the function under test, use pytest.raises() as a context manager as in the following example:
```python
def my_function(value):
    if value < 0:
        raise ValueError("Value cannot be negative")
    return value * 2

def test_my_function_raises_error():
    with pytest.raises(ValueError):
        my_function(-1)
```
Finally, please wrap your entire code in a single set of "```python" and "```" markers.

Here is the code to be tested:
```python
{function_code}
```

Provide your revised test case below.
"""