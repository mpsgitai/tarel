"""Offline install bundles: TAREL, chosen hub packages, and their wheels for one target machine.

A bundle is a plain ZIP of wheels plus a hash-pinned ``requirements.lock``. The target installs it
with ``pip install --no-index --require-hashes``; it needs Python and pip, nothing else. No
executable, installer script, or signature tooling is shipped, so nothing in a bundle looks
unusual to a virus scanner.
"""
