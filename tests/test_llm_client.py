from ut.llm_client import generate_test_plan, generate_test_case

# Test local inference with vllm
def test_generate_test_case():
    prompt = "Generate unit tests for the add function:\n```python\ndef add(a, b):\n    return a + b\n```"
    try:
        result = generate_test_case(prompt)
    except RuntimeError as e:
        print(f"Test failed: {e}")
        return
    print(result)


if __name__ == "__main__":
    test_generate_test_case()