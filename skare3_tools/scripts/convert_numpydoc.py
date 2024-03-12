# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""Convert docstrings from reST to numpydoc format."""

import ast
import re
from pathlib import Path

REST_MARKERS_RETURNS = [":returns:", ":return:", ":rtype:"]
REST_MARKERS_PARAMS = [":param "]


def get_function_docstrings(module_file: str) -> list[dict]:
    """
    Get the docstring for each function in the given module file.

    Parameters
    ----------
    module_file : str
        The path to the module file.

    Returns
    -------
    list of dict
        A list of dicts of function names and docstring information.
    """
    with open(module_file, "r") as f:
        module_source = f.read()

    module_ast = ast.parse(module_source)

    function_docstrings = []

    function_nodes = []
    for node in module_ast.body:
        if isinstance(node, ast.FunctionDef):
            function_nodes.append(node)
        elif isinstance(node, ast.ClassDef):
            for method_node in node.body:
                if isinstance(method_node, ast.FunctionDef):
                    function_nodes.append(method_node)  # noqa: PERF401

    for node in function_nodes:
        function_name = node.name
        function_docstring = ast.get_docstring(node, clean=False)
        if function_docstring:
            function_docstrings.append(
                {
                    "name": function_name,
                    "text": function_docstring,
                    "idx_func_start": node.lineno - 1,
                    "idx_func_stop": node.end_lineno - 1,
                }
            )

    return function_docstrings


def find_quote_style(lines: list):
    """Find the quote style used for a docstring.

    Parameters
    ----------
    lines : list
        A list of strings representing the lines of code.

    Returns
    -------
    str
        The quote style used for the docstring (either triple single or triple double
        quotes).

    Notes
    -----
    This function assumes that the lines are part of a function definition and that the
    docstring is the first thing in the function definition.
    """
    for line in lines:
        for quotes in ['"""', "'''"]:
            if quotes in line:
                return quotes


def get_docstring_blocks(module_file: str) -> list[dict]:
    """Get all the docstrings that look like reST format in the list of lines.

    Returns a list of dict with keys:
    - ``idx0``: (int) Index of start of docstring text
    - ``idx1``: (int) Index of end of docstring text
    - ``indent``: (int) Number of spaces to indent docstring text
    - ``lines``: (list) Lines of docstring

    Parameters
    ----------
    module_file : str
        Path to module file.

    Returns
    -------
    list of dict
    """
    # Use ast to get information about all functions/methods that have a docstring.
    # This conventiently gives us the line numbers for the start and end of the
    # function definition. We can then use this to find the docstring in the list of
    # lines for the module and extract it.
    docstrings_ast = get_function_docstrings(module_file)

    lines = Path(module_file).read_text().splitlines()

    docstring_blocks = []

    for docstring_ast in docstrings_ast:
        # Skip functions without any reST markers in the docstring
        if not any(
            marker in docstring_ast["text"]
            for marker in REST_MARKERS_RETURNS + REST_MARKERS_PARAMS
        ):
            continue

        idx0 = None
        idx1 = None

        # Line range for this function including docstring
        idx0_func = docstring_ast["idx_func_start"]
        idx1_func = docstring_ast["idx_func_stop"]

        quotes = find_quote_style(lines[idx0_func:idx1_func])

        for idx in range(idx0_func, idx1_func):
            line = lines[idx].strip()
            if re.match(f"^{quotes}.*{quotes}$", line):
                # Single-line docstring, ignore it since it can't have reST markers.
                # And we shouldn't be here anyway since we already checked for reST
                # markers.
                break
            if idx0 is None and line.startswith(quotes):
                idx0 = idx
            elif idx0 is not None and line.endswith(quotes):
                if line.strip() != quotes:
                    # Docstring with text and final """ on same line caused some trouble
                    # so just tell the user to fix it by hand.
                    raise ValueError(
                        f"docstring {quotes} must be on separate line (fix by hand)\n"
                        f"line: {line}\n"
                        f"line number: {idx + 1}\n"
                    )
                # Don't include final quotes in this processing, it makes things easier.
                idx1 = idx
                break

        if idx0 is not None and idx1 is not None:
            lines_out = lines[idx0:idx1]
            indent = len(lines_out[0]) - len(lines_out[0].lstrip())
            lines_out = [line[indent:] for line in lines_out]

            docstring_block = {
                "idx0": idx0,
                "idx1": idx1,
                "indent": indent,
                "lines": lines_out,
            }
            docstring_blocks.append(docstring_block)

    return docstring_blocks


def get_first_marker_index(lines: list, markers: list):
    """
    Get the index of the first line that starts with a given marker.

    Parameters
    ----------
    lines : list
        A list of strings representing the lines of text to search.
    markers : list
        A list of strings representing the markers to search for.

    Returns
    -------
    int
        The index of the first line that starts with one of the given markers.
        If no such line is found, returns the length of the ``lines`` list.
    """
    for idx, line in enumerate(lines):
        if any(line.startswith(marker) for marker in markers):
            return idx
    return len(lines)


def get_marker_idxs(lines: list[str], markers_rest: list[str]):
    """
    Get the indices of all lines that start with a given marker.

    Parameters
    ----------
    lines : list
        A list of strings representing the lines of text to search.
    markers : list
        A list of strings representing the markers to search for.

    Returns
    -------
    idxs : list
        A list of integers representing the indices of all lines that start with
        one of the given markers. If no such lines are found, returns an empty list.
    markers : list
        A list of strings representing the markers that were found.
    """
    idxs = []
    markers = []
    for idx, line in enumerate(lines):
        for marker in markers_rest:
            if line.startswith(marker):
                idxs.append(idx)
                markers.append(marker)
                break
    idxs.append(len(lines))
    return idxs, markers


def params_to_numpydoc(lines: list) -> list:
    """
    Convert lines of reST parameters to numpydoc format.

    Parameters
    ----------
    lines : list
        List of lines of reST parameters.

    Returns
    -------
    list
        List of lines of numpydoc parameters.

    Raises
    ------
    ValueError
        If the lines cannot be parsed.
    """
    if not lines:
        return []

    idxs, _ = get_marker_idxs(lines, [":param "])
    lines_out = [
        "Parameters",
        "----------",
    ]

    for idx0, idx1 in zip(idxs[:-1], idxs[1:]):
        lines_param = lines[idx0:idx1]
        line_param = lines_param[0]
        match = re.match(r":param \s+ (\w+) \s* : \s* (.*)", line_param, re.VERBOSE)
        if match:
            name = match.group(1)
            desc = match.group(2)
        else:
            raise ValueError(f"Could not parse line: {line_param}")

        if idx1 - idx0 == 1:
            # Single line param, no type(s) given
            lines_out.append(name)
            lines_out.append("    " + desc.strip())
        else:
            # Multiline, so assume the first line is the type(s)
            lines_out.append(f"{name} : {desc}")
            for line in lines_param[1:]:
                lines_out.append("    " + line.strip())  # noqa: PERF401

    return lines_out


def returns_to_numpydoc(lines: list) -> list:
    """
    Convert lines of reST returns section to numpydoc format.

    Parameters
    ----------
    lines : list
        List of lines of reST returns.

    Returns
    -------
    list
        List of lines of numpydoc returns.
    """
    if not lines:
        return []

    idxs, markers = get_marker_idxs(lines, REST_MARKERS_RETURNS)

    return_type = None
    return_desc_lines = []

    for idx0, idx1, marker in zip(idxs[:-1], idxs[1:], markers):
        if marker == ":rtype:":
            return_type = " ".join(lines[idx0:idx1])
            return_type = return_type[len(marker) :].strip()

        elif marker in [":return:", ":returns:"]:
            return_desc_lines = [lines[idx0][len(marker) :]] + lines[idx0 + 1 : idx1]

    lines_out = [
        "Returns",
        "-------",
    ]

    if return_type is None:
        # No explicit return type.
        if len(return_desc_lines) == 1:
            # Single line return description, so assume it is the return type.
            return_type = return_desc_lines[0].strip()
            return_desc_lines = []
        else:
            # Multiline return description, so use "out" as the thing being returned.
            return_type = "out"

    lines_out.append(return_type)
    for line in return_desc_lines:
        lines_out.append("    " + line.strip())  # noqa: PERF401

    return lines_out


def convert_lines_to_numpydoc(lines):
    """Convert docstring lines to numpydoc format.

    Parameters
    ----------
    lines : list
        List of lines of docstring text.

    Returns
    -------
    list
        List of lines of docstring text in numpydoc format.
    """
    lines_out = None

    idx_any = get_first_marker_index(lines, REST_MARKERS_RETURNS + REST_MARKERS_PARAMS)
    idx_params = get_first_marker_index(lines, REST_MARKERS_PARAMS)
    idx_returns = get_first_marker_index(lines, REST_MARKERS_RETURNS)

    # Start out with the original lines up to the first marker (i.e. the start of
    # existing parameters or returns sections).
    lines_out = lines[:idx_any]

    # Cut lines_out at the end if they are blank
    while lines_out[-1].strip() == "":
        lines_out = lines_out[:-1]

    # This assumes that params are before returns. We always adhere to this convention.
    lines_params = [line for line in lines[idx_params:idx_returns] if line.strip()]
    lines_returns = [line for line in lines[idx_returns:] if line.strip()]

    lines_params_out = params_to_numpydoc(lines_params)
    lines_returns_out = returns_to_numpydoc(lines_returns)

    if lines_params_out:
        lines_out.append("")
        lines_out.extend(lines_params_out)

    if lines_returns_out:
        lines_out.append("")
        lines_out.extend(lines_returns_out)

    return lines_out


def indent_lines(lines: list, indent: str) -> list:
    """Indent lines of text.

    Parameters
    ----------
    lines : list
        List of lines of text.
    indent : str
        String to use for indentation.

    Returns
    -------
    list
        List of lines of text with indentation added.
    """
    out_lines = []
    for line in lines:
        if line:
            out_lines.append(indent + line)
        else:
            out_lines.append(line)
    return out_lines


def convert_module_to_numpydoc(module_file_in, module_file_out=None):
    """Convert module docstrings to numpydoc format.

    Parameters
    ----------
    module_file_in : str
        Path to module file.
    module_file_out : str
        Path to output module file. If None, overwrite module_file_in.

    Returns
    -------
    list
    List of lines of docstring text in numpydoc format.
    """
    if module_file_out is None:
        module_file_out = module_file_in

    lines = Path(module_file_in).read_text().splitlines()
    lines_orig = lines.copy()

    docstring_blocks = get_docstring_blocks(module_file_in)

    # Go through existing docstrings in reverse order so that we can modify the lines
    # list in-place without messing up the line numbers.
    for docstring_block in reversed(docstring_blocks):
        idx0 = docstring_block["idx0"]
        idx1 = docstring_block["idx1"]
        lines_out = convert_lines_to_numpydoc(docstring_block["lines"])
        lines_out = indent_lines(lines_out, " " * docstring_block["indent"])
        lines = lines[:idx0] + lines_out + lines[idx1:]

    if module_file_in == module_file_out and lines == lines_orig:
        # Don't bother rewriting unchanged file
        return

    print(f"Writing {module_file_out}")
    file_end = "\n" if lines else ""
    Path(module_file_out).write_text("\n".join(lines) + file_end)


def convert_directory_to_numpydoc(dir_file):
    """Walk through a directory and convert all docstrings to numpydoc format.

    This function will overwrite the original files so be sure they are in version
    control or backed up.

    Parameters
    ----------
    dir_file : str
        Path to directory.
    """
    for path in Path(dir_file).glob("**/*.py"):
        convert_module_to_numpydoc(path, path)
