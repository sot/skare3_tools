from skare3_tools.dashboard import get_template
from skare3_tools import test_results as tr


def test_stream():
    test_runs = tr.get()[-10:]

    for tests in test_runs:
        for ts in tests["test_suites"]:
            ts["test_cases"] = {t["name"]: t for t in ts["test_cases"]}
        tests["test_suites"] = {t["name"]: t for t in tests["test_suites"]}

    test_suite_names = sorted(
        set(sum([[k for k in t["test_suites"].keys()] for t in test_runs], []))
    )
    test_suites = []
    column_names = [str(i) for i in range(len(test_runs))]
    for ts_name in test_suite_names:
        test_cases = []
        test_case_names = sorted(
            set(
                sum(
                    [
                        list(t["test_suites"][ts_name]["test_cases"].keys())
                        for t in test_runs
                        if ts_name in t["test_suites"]
                    ],
                    [],
                )
            )
        )
        for tc_name in test_case_names:
            row = [("name", tc_name)]
            row += [
                (
                    n,
                    (
                        t["test_suites"][ts_name]["test_cases"][tc_name]["status"]
                        if ts_name in t["test_suites"]
                        and tc_name in t["test_suites"][ts_name]["test_cases"]
                        else "skipped"
                    ),
                )
                for n, t in zip(column_names, test_runs)
            ]
            test_cases.append(row)
        test_suites.append({"name": ts_name, "test_cases": test_cases})
    data = {"columns": column_names, "test_suites": test_suites}

    template = get_template("test-stream.html")
    return template.render(title="Skare3 Tests", data=data)
