"""Call a running flowgraph's XML-RPC Server block from a terminal.

    python rpc.py set_cutoff 1000
    python rpc.py get_cutoff

Every GRC variable has a set_<name> and get_<name>.
"""

import argparse
import ast
import sys
from xmlrpc.client import Fault, ServerProxy

URL = "http://127.0.0.1:8080"   # the XML-RPC Server block's addr:port


def parse_value(text: str):
    """
    Turn a command-line argument into a number when it looks like one.

    Args:
        text (str): the argument, e.g. "1000", "1.5e3", "usb"

    Returns:
        int | float | str: the parsed value
    """
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def main():
    """Parse options, make the call and print what comes back."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("method", help="e.g. set_cutoff, get_cutoff")
    ap.add_argument("args", nargs="*", help="arguments to the method")
    ap.add_argument("--url", default=URL)
    args = ap.parse_args()

    fg = ServerProxy(args.url, allow_none=True)
    try:
        result = getattr(fg, args.method)(*map(parse_value, args.args))
    except ConnectionRefusedError:
        sys.exit(f"nothing listening on {args.url}; is the flowgraph running?")
    except Fault as e:
        sys.exit(f"{args.method}: {e.faultString}")
    if result is not None:
        print(result)


if __name__ == "__main__":
    sys.exit(main())
