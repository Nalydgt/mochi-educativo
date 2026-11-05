"""Persistent catalog startup entry: install only the reviewed Hermes API loader."""
try:
    from runtime_hook import install
    install()
except Exception as error:
    # Python normally prints and ignores sitecustomize failures. Refuse to
    # silently serve the old cancellation behavior after a broken deployment.
    import os
    import sys
    print('Mochi Hermes HTTP cancellation startup guard failed: '+type(error).__name__,file=sys.stderr,flush=True)
    os._exit(78)
