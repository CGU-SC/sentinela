import contextlib
import io
import runpy
import sys
import types
from pathlib import Path

import polars as pl
import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "backend" / "check_cache.py"


def _run_check_cache(monkeypatch, *, exists, frame=None):
    fake_cache = types.ModuleType("data_cache")
    fake_cache._MATRIZ_PARQUET_PATH = "fixture/matriz.smod"
    monkeypatch.setitem(sys.modules, "data_cache", fake_cache)
    monkeypatch.setattr("os.path.exists", lambda _path: exists)
    if frame is not None:
        monkeypatch.setattr(pl, "read_parquet", lambda _path: frame)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    return output.getvalue()


def test_cache_inspector_reports_missing_cache(monkeypatch):
    output = _run_check_cache(monkeypatch, exists=False)
    assert "fixture/matriz.smod não existe" in output


def test_cache_inspector_prints_scores_when_present(monkeypatch):
    frame = pl.DataFrame({"score_risco": [1.5], "label": ["alto"]})
    output = _run_check_cache(monkeypatch, exists=True, frame=frame)
    assert "Colunas encontradas" in output
    assert "Valores das colunas de score" in output
    assert "Contagem de nulos nas colunas de score" in output


def test_cache_inspector_reports_when_score_columns_are_absent(monkeypatch):
    frame = pl.DataFrame({"label": ["alto"]})
    output = _run_check_cache(monkeypatch, exists=True, frame=frame)
    assert "Nenhuma coluna com 'score'" in output
