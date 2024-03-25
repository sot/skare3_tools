#!/usr/bin/env python3

import os
import re

from skare3_tools import config, dashboard
from skare3_tools import test_results as tr


def html(text):
    """
    Convert colorized text to html.

    This assumes an input from the terminal and replaces some standard characters so they are
    interpreted in html:
     - some ANSI escape codes (https://en.wikipedia.org/wiki/ANSI_escape_code#Colors)
     - new lines

    :param text:
    :return:
    """
    span = {
        "\x1b[1m": '<span style="font-weight: bold;">',
        "\x1b[4m": '<span style="text-decoration: underline">',
        # '\x1b[7m': '<span>',  # reverse
        "\x1b[30m": '<span style="color:black">',
        "\x1b[31m": '<span style="color:red">',
        "\x1b[32m": '<span style="color:green">',
        "\x1b[33m": '<span style="color:yellow">',
        "\x1b[34m": '<span style="color:blue">',
        "\x1b[35m": '<span style="color:magenta">',
        "\x1b[36m": '<span style="color:cyan">',
        "\x1b[37m": '<span style="color:white">',
        "\x1b[30;1m": '<span style="font-weight: bold; color:black">',
        "\x1b[31;1m": '<span style="font-weight: bold; color:red">',
        "\x1b[32;1m": '<span style="font-weight: bold; color:green">',
        "\x1b[33;1m": '<span style="font-weight: bold; color:yellow">',
        "\x1b[34;1m": '<span style="font-weight: bold; color:blue">',
        "\x1b[35;1m": '<span style="font-weight: bold; color:magenta">',
        "\x1b[36;1m": '<span style="font-weight: bold; color:cyan">',
        "\x1b[37;1m": '<span style="font-weight: bold; color:white">',
        "\x1b[40m": '<span style="background-color:black">',
        "\x1b[41m": '<span style="background-color:red">',
        "\x1b[42m": '<span style="background-color:green">',
        "\x1b[43m": '<span style="background-color:yellow">',
        "\x1b[44m": '<span style="background-color:blue">',
        "\x1b[45m": '<span style="background-color:magenta">',
        "\x1b[46m": '<span style="background-color:cyan">',
        "\x1b[47m": '<span style="background-color:white">',
        "\x1b[40;1m": '<span style="font-weight: bold; background-color:black">',
        "\x1b[41;1m": '<span style="font-weight: bold; background-color:red">',
        "\x1b[42;1m": '<span style="font-weight: bold; background-color:green">',
        "\x1b[43;1m": '<span style="font-weight: bold; background-color:yellow">',
        "\x1b[44;1m": '<span style="font-weight: bold; background-color:blue">',
        "\x1b[45;1m": '<span style="font-weight: bold; background-color:magenta">',
        "\x1b[46;1m": '<span style="font-weight: bold; background-color:cyan">',
        "\x1b[47;1m": '<span style="font-weight: bold; background-color:white">',
    }

    text = text.replace("\n", "<br/>\n")

    reset = "\x1b[0m"
    result = ""
    depth = 0
    i = 0
    matches = list(re.finditer(r"\x1b\[[0-9;]+m", text))
    for m in matches:
        s, e = m.span()
        c = text[s:e]
        result += text[i:s]
        if c == reset:
            result += "</span>" * depth
            depth = 0
        elif c in span:
            depth += 1
            result += span[c]
        i = e
    result += text[i:]
    return result


def test_log(path):
    params = {
        "static_dir": "static",
    }
    run_id = path.split("/")[0]
    filename = "/".join(path.split("/")[1:])
    test_runs = [r for r in tr.get() if r["run_info"]["uid"] == run_id]
    if not test_runs:
        return dashboard.get_template("error.html").render(
            title="404 Error", message="Run {run_id} not found".format(run_id=run_id)
        )
    filename = os.path.join(
        config.CONFIG["data_dir"],
        "test_logs",
        test_runs[0]["run_info"]["destination"],
        filename,
    )
    if not os.path.exists(filename) or not os.path.isfile(filename):
        return dashboard.get_template("error.html").render(
            title="404 Error", message="File {path} not found".format(path=path)
        )

    with open(filename) as f:
        contents = html(f.read())

    template = dashboard.get_template("test-log.html")
    return template.render(title="Skare3 Test Log", contents=contents, config=params)
