import os
import sys


def test_status_prints_stub(capsys):
    # Ensure the atpctl package in the appliance scaffold is importable
    pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    from atpctl import main as atp_main

    # call function directly to avoid Typer dependency in test env
    atp_main.status()
    captured = capsys.readouterr()
    assert '{"status":"stub"}' in captured.out
