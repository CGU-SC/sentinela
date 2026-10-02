import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import farmacia


CNPJ = "12345678000190"


def test_cnpj_access_status_cleans_formatted_document_and_returns_registration(monkeypatch):
    source = pl.DataFrame(
        {
            "cnpj": [CNPJ], "razao_social": ["Farmacia Exemplo"], "nome_fantasia": ["Exemplo"],
            "municipio": ["Brasilia"], "uf": ["DF"],
        }
    )
    monkeypatch.setattr(farmacia, "get_df_dados_farmacia", lambda: source)
    result = farmacia.get_cnpj_access_status("12.345.678/0001-90")
    assert result.cnpj == CNPJ
    assert result.status == "valid"
    assert result.in_program is True
    assert result.uf == "DF"


@pytest.mark.parametrize(("cnpj", "status"), [("123", 422), ("99999999000199", 404)])
def test_cnpj_access_status_reports_invalid_and_absent_documents(monkeypatch, cnpj, status):
    monkeypatch.setattr(
        farmacia,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "razao_social": ["X"], "nome_fantasia": ["X"], "municipio": ["X"], "uf": ["DF"]}),
    )
    with pytest.raises(HTTPException) as error:
        farmacia.get_cnpj_access_status(cnpj)
    assert error.value.status_code == status


def test_secondary_cnaes_are_sorted_and_tied_to_profiled_farmacia(monkeypatch):
    monkeypatch.setattr(farmacia, "get_df_dados_farmacia", lambda: pl.DataFrame({"cnpj": [CNPJ], "id_cnpj": [8]}))
    monkeypatch.setattr(farmacia, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": [CNPJ]}))
    monkeypatch.setattr(
        farmacia,
        "get_df_dados_farmacia_cnaes_secundarios",
        lambda: pl.DataFrame({"id_cnpj": [8, 8], "id_cnae": ["4771701", "4771702"], "descricao": ["B", "A"]}),
    )
    assert farmacia.get_cnaes_secundarios_farmacia(CNPJ)[0]["id_cnae"] == "4771701"
    with pytest.raises(HTTPException) as invalid:
        farmacia.get_cnaes_secundarios_farmacia("123")
    assert invalid.value.status_code == 422


def test_secondary_cnaes_require_registration_and_profile_rows(monkeypatch):
    monkeypatch.setattr(farmacia, "get_df_dados_farmacia", lambda: pl.DataFrame({"cnpj": ["99999999000199"], "id_cnpj": [8]}))
    with pytest.raises(HTTPException) as not_registered:
        farmacia.get_cnaes_secundarios_farmacia(CNPJ)
    assert not_registered.value.status_code == 404

    monkeypatch.setattr(farmacia, "get_df_dados_farmacia", lambda: pl.DataFrame({"cnpj": [CNPJ], "id_cnpj": [8]}))
    monkeypatch.setattr(farmacia, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["99999999000199"]}))
    with pytest.raises(HTTPException) as no_profile:
        farmacia.get_cnaes_secundarios_farmacia(CNPJ)
    assert no_profile.value.status_code == 404


def test_movimentacao_response_sums_sales_rows_and_excludes_inventory_rows():
    rows = pl.DataFrame(
        {
            "tipo_linha": ["venda_normal", "venda_irregular", "estoque"],
            "gtin": ["1", "2", "3"], "medicamento": ["A", "B", "C"],
            "periodo_inicial": [None, None, None], "periodo_inicio_irregular": [None, None, None],
            "periodo_final": [None, None, None], "estoque_inicial": [0, 0, 3], "estoque_final": [0, 0, 2],
            "vendas": [10, 5, None], "vendas_irregular": [0, 5, None],
            "valor": [100.0, 50.0, None], "valor_irregular": [0.0, 50.0, None], "notas": [None, None, None],
        }
    )
    result = farmacia._build_movimentacao_response_from_df(CNPJ, rows, from_cache=True)
    assert result.summary.total_vendas == 15
    assert result.summary.total_vendas_irregular == 5
    assert result.summary.valor_total == 150.0
    assert result.summary.pct_irregular == 33.33
    assert result.from_cache is True


def test_dados_farmacia_combines_profile_flags_secondary_cnaes_and_geo_alert(monkeypatch):
    monkeypatch.setattr(
        farmacia,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "razao_social": ["Exemplo"], "is_cnae_incompativel_farmaceutico": [False], "is_cnae_farmacia_ausente": [True], "uf": ["DF"]}),
    )
    monkeypatch.setattr(
        farmacia,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "id_cnpj": [1], "uf": ["DF"], "is_cnae_incompativel_farmaceutico": [True]}),
    )
    monkeypatch.setattr(
        farmacia,
        "calcular_alerta_uf_nao_vizinha",
        lambda **kwargs: {"is_dispersao_uf_nao_vizinha": True, "pct_dispersao_uf_nao_vizinha": 12.5, "valor_dispersao_uf_nao_vizinha": 80.0},
    )
    monkeypatch.setattr(farmacia, "get_cnaes_secundarios_farmacia", lambda _cnpj: [{"id_cnae": 123, "descricao": "Comercio"}])

    result = farmacia.get_dados_farmacia(CNPJ)
    assert result.is_cnae_incompativel_farmaceutico is True
    assert result.is_cnae_farmacia_ausente is True
    assert result.is_dispersao_uf_nao_vizinha is True
    assert result.pct_dispersao_uf_nao_vizinha == 12.5
    assert result.cnaes_secundarios[0].id_cnae == 123


def test_dados_farmacia_validates_inputs_and_surfaces_missing_and_unexpected_failures(monkeypatch):
    with pytest.raises(HTTPException) as invalid:
        farmacia.get_dados_farmacia("123")
    assert invalid.value.status_code == 422

    monkeypatch.setattr(
        farmacia,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"cnpj": ["99999999000199"], "razao_social": ["Other"]}),
    )
    with pytest.raises(HTTPException) as absent:
        farmacia.get_dados_farmacia(CNPJ)
    assert absent.value.status_code == 404

    monkeypatch.setattr(
        farmacia,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "razao_social": ["Example"]}),
    )
    monkeypatch.setattr(farmacia, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["99999999000199"]}))
    with pytest.raises(HTTPException) as no_profile:
        farmacia.get_dados_farmacia(CNPJ)
    assert no_profile.value.status_code == 404

    monkeypatch.setattr(
        farmacia,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "razao_social": ["Example"]}),
    )
    monkeypatch.setattr(
        farmacia,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "id_cnpj": [1], "uf": ["SP"], "is_cnae_incompativel_farmaceutico": [False]}),
    )
    monkeypatch.setattr(
        farmacia,
        "calcular_alerta_uf_nao_vizinha",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("geo unavailable")),
    )
    with pytest.raises(HTTPException, match="Erro ao buscar dados cadastrais.*geo unavailable") as unexpected:
        farmacia.get_dados_farmacia(CNPJ)
    assert unexpected.value.status_code == 500


def test_movimentacao_data_exposes_producer_failures(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(farmacia, "load_or_sync_memoria_calculo", lambda *args, **kwargs: SimpleNamespace(error="offline", df=None))
    with pytest.raises(HTTPException) as error:
        farmacia.get_movimentacao_data(CNPJ, engine=None)
    assert error.value.status_code == 503

    monkeypatch.setattr(farmacia, "load_or_sync_memoria_calculo", lambda *args, **kwargs: SimpleNamespace(error=None, df=None))
    with pytest.raises(HTTPException) as missing:
        farmacia.get_movimentacao_data(CNPJ, engine=None)
    assert "sem dados carregados" in missing.value.detail


def test_movimentacao_data_returns_typed_response_and_producer_timings(monkeypatch):
    from types import SimpleNamespace

    source = pl.DataFrame(
        {
            "tipo_linha": ["venda_normal"],
            "vendas": [3],
            "vendas_irregular": [1],
            "valor": [25.0],
            "valor_irregular": [5.0],
        }
    )
    monkeypatch.setattr(
        farmacia,
        "load_or_sync_memoria_calculo",
        lambda *_args, **_kwargs: SimpleNamespace(
            error=None,
            df=source,
            from_cache=False,
            read_time_ms=1.2,
            query_time_ms=2.3,
            save_time_ms=3.4,
        ),
    )

    result = farmacia.get_movimentacao_data(CNPJ, engine=None)

    assert result.cnpj == CNPJ
    assert result.summary.total_vendas == 3
    assert result.summary.valor_total == 25.0
    assert result.summary.pct_irregular == 20.0
    assert result.from_cache is False
    assert (result.read_time_ms, result.query_time_ms, result.save_time_ms) == (1.2, 2.3, 3.4)
