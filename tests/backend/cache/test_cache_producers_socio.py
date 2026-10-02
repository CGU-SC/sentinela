from types import SimpleNamespace

import pandas as pd
import polars as pl

import data_cache
from cache_producers import socios


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Engine:
    def connect(self):
        return _Connection()


def test_socios_loader_falls_through_corrupt_parquet_to_database(monkeypatch, tmp_path):
    expected_path = tmp_path / socios.SOCIOS_PARQUET
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(socios.os.path, "exists", lambda path: path == str(expected_path))
    monkeypatch.setattr(
        socios.pl,
        "read_parquet",
        lambda _path: (_ for _ in ()).throw(ValueError("corrupt parquet")),
    )
    sql_calls = []

    def read_sql(query, connection, *, params):
        sql_calls.append((str(query), connection, params))
        return pd.DataFrame({"cnpj": ["12345678000190"], "cpf_cnpj_socio": ["12345678901"]})

    monkeypatch.setattr(socios.pd, "read_sql", read_sql)
    monkeypatch.setitem(__import__("sys").modules, "database", SimpleNamespace(engine=_Engine()))

    result = socios.load_socios("12345678000190")

    assert result.from_cache is False
    assert result.error is None
    assert result.df.equals(pl.DataFrame({"cnpj": ["12345678000190"], "cpf_cnpj_socio": ["12345678901"]}))
    assert len(sql_calls) == 1
    assert "WHERE cnpj = :cnpj" in sql_calls[0][0]
    assert sql_calls[0][2] == {"cnpj": "12345678000190"}
