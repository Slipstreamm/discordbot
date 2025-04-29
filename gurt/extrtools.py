#!/usr/bin/env python3
"""
extract_tools.py

Usage:
    python extract_tools.py path/to/your_module.py > tools.json

Parses the given Python file for calls to:
    tool_declarations.append(
        generative_models.FunctionDeclaration(...)
    )
and outputs a JSON list of the kwargs passed to each FunctionDeclaration.
"""

import ast
import json
import sys

def extract_function_declarations(source: str):
    tree = ast.parse(source)
    tools = []

    for node in ast.walk(tree):
        # look for expressions like: tool_declarations.append( generative_models.FunctionDeclaration(...) )
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "append"
            # ensure it's tool_declarations.append
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "tool_declarations"
            and node.value.args
            and isinstance(node.value.args[0], ast.Call)
        ):
            decl_call = node.value.args[0]
            # ensure it's generative_models.FunctionDeclaration(...)
            if (
                isinstance(decl_call.func, ast.Attribute)
                and decl_call.func.attr == "FunctionDeclaration"
            ):
                tool_obj = {}
                for kw in decl_call.keywords:
                    # use ast.literal_eval to turn the AST node into a Python object
                    try:
                        value = ast.literal_eval(kw.value)
                    except ValueError:
                        # if something non-literal sneaks in, fallback to the raw source
                        value = ast.get_source_segment(source, kw.value)
                    tool_obj[kw.arg] = value
                tools.append(tool_obj)

    return tools

def main():
    if len(sys.argv) != 2:
        print("Usage: python extract_tools.py path/to/your_module.py", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    tools = extract_function_declarations(source)
    json.dump(tools, sys.stdout, indent=2)
    sys.stdout.write("\n")

if __name__ == "__main__":
    main()
