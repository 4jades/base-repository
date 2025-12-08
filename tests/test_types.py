from __future__ import annotations

import importlib
import sys
import types
import typing


def test_repo_types_version_branch_is_covered(monkeypatch) -> None:
    """
    < Force coverage of repo_types.py's sys.version_info branch (TypeVar import path) >
    1. Remove repo_types from sys.modules to clear the import cache.
    2. Force the opposite sys.version_info branch for coverage.
    3. Provide the required TypeVar import source for that branch:
       - For 3.13+: keep real typing, inject typing.TypeVar
       - For <3.13: inject a fake typing_extensions module with TypeVar
    4. Re-import repo_types to execute the branch at import time.
    5. Sanity-check exported symbols exist.
    """
    # 1
    sys.modules.pop("base_repository.repo_types", None)
    sys.modules.pop("typing_extensions", None)

    # 2
    want_ge_313 = sys.version_info < (3, 13)

    # 3
    if want_ge_313:
        monkeypatch.setattr(sys, "version_info", (3, 13, 0))
        monkeypatch.setattr(typing, "TypeVar", lambda *args, **kwargs: object(), raising=False)
    else:
        monkeypatch.setattr(sys, "version_info", (3, 12, 0))

        fake_te = types.ModuleType("typing_extensions")
        fake_te.TypeVar = lambda *args, **kwargs: object() # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "typing_extensions", fake_te)

    # 4
    mod = importlib.import_module("base_repository.repo_types")

    # 5
    assert hasattr(mod, "TModel")
    assert hasattr(mod, "TDomain")
    assert hasattr(mod, "QueryOrStmt")
