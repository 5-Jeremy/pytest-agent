
""" This script calculates the pass rate for each iteration of the coder agent based on the planned tests and
    the test_results.json files. """

from ast import arg
import os, argparse, sys
from src.ut.workspace import WorkspaceManager

# Assume matplotlib is available
import matplotlib.pyplot as plt

def parse_args():
    parser = argparse.ArgumentParser(description="Calculate pass rates from test results.")
    parser.add_argument("dir", type=str, help="Path to a workspace.")
    parser.add_argument("-o", "--output", type=str, default="pass_rates.png",
                        help="Output image file to save the plot (default: pass_rates.png)")
    parser.add_argument("-T", "--title", type=str, default="Test Pass Rates by Iteration",
                        help="Title of the plot (default: 'Test Pass Rates by Iteration')")
    parser.add_argument("--no-save", action="store_true", help="Do not save the plot to a file, just display it.")
    return parser.parse_args()

if __name__ == "__main__":
    # Some of the functions called here will add unnecessary output unless we disable it
    os.environ["UT_VERBOSE"] = "0"
    os.environ["UT_LOG_FILE"] = "None"
    args = parse_args()
    directory_path = args.dir
    try:
        workspace = WorkspaceManager(base_dir=directory_path, fresh_start=False)
        # Get the number of planned tests
        # TODO: Adjust to the plan format if it is not JSON; for now we assume JSON
        test_case_plans = workspace.get_test_case_plans()
        all_test_results = workspace.load_all_test_results()
    except FileNotFoundError as e:
        print(f"Invalid workspace: {e}")
        exit(1)

    all_planned_tests = list(test_case_plans.keys())
    num_planned_tests = len(all_planned_tests)
    print(f"Total planned tests: {num_planned_tests}")
    
    # Get the set of passed tests for each iteration 
    all_passed_tests = []
    iterations = []
    per_iteration_rates = []
    cumulative_percentages = []
    for iteration in sorted(all_test_results.keys()):
        test_results = all_test_results[iteration]
        total_tests = len(test_results)
        all_test_names = list(test_results.keys())
        # Check for tests that were already passed being redone
        for name in all_test_names:
            if name in all_passed_tests:
                print(f"Warning: Test {name} reused in iteration {iteration} but was already passed.")
        passed_test_names = [name for name, result in test_results.items() if result == "PASSED"]
        for name in passed_test_names:
            if name not in all_passed_tests:
                all_passed_tests.append(name)
        passed_tests = sum(1 for result in test_results.values() if result == "PASSED")
        pass_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0.0
        print(f"Iteration {iteration}: {passed_tests}/{total_tests} tests passed ({pass_rate:.2f}%)")
        cumulative_pct = (len(all_passed_tests) / num_planned_tests) * 100 if num_planned_tests > 0 else 0.0
        print(f"  → Cumulative passed tests: {len(all_passed_tests)}/{num_planned_tests} ({cumulative_pct:.2f}%)")

        # Collect data for plotting
        iterations.append(str(iteration))
        per_iteration_rates.append(pass_rate)
        cumulative_percentages.append(cumulative_pct)

    # Plot results
    if len(iterations) == 0:
        print("No iterations to plot.")
    else:
        fig, ax = plt.subplots(figsize=(7, 5))
        font_size = 18  # Increased font size
        ax.plot(iterations, per_iteration_rates, marker='o', label='Per-iteration pass rate (%)')
        ax.plot(iterations, cumulative_percentages, marker='s', label='Cumulative passed planned tests (%)')
        ax.set_xlabel('Iteration', fontsize=font_size)
        ax.set_ylabel('Percentage', fontsize=font_size)
        ax.set_title(args.title, fontsize=font_size+2)
        ax.set_ylim(0, 100)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.legend(loc='upper left', fontsize=font_size-4)
        ax.tick_params(axis='both', which='major', labelsize=font_size)
        plt.tight_layout()

        out_path = args.output if args and getattr(args, 'output', None) else 'pass_rates.png'
        
        if not getattr(args, 'no_save', False):
            try:
                plt.savefig(out_path)
                print(f"Saved plot to {out_path}")
            except Exception as e:
                print(f"Failed to save plot: {e}")

