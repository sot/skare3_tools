from flask import Flask

from skare3_tools.dashboard.views.dashboard import dashboard
from skare3_tools.dashboard.views.test_log import test_log
from skare3_tools.dashboard.views.test_results import test_results
from skare3_tools.dashboard.views.test_stream import test_stream


app = Flask(__name__)


@app.route("/")
def main():
    return dashboard()


@app.route("/tests/logs/<path:text>")
def tests_logs(text):
    return test_log(text)


@app.route("/tests")
def tests():
    return test_results()


@app.route("/tests/stream")
def tests_stream():
    return test_stream()


if __name__ == "__main__":
    app.run(debug=True)
