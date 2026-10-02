import os

import polars as pl

import cache_files
import cache_producers.network as network
from api.services.analytics import _cache


def test_network_producer_delegates_to_analytics_cache_sync(monkeypatch):
    calls = []
    monkeypatch.setattr(
        _cache,
        "sync_network",
        lambda cnpj: calls.append(cnpj),
    )

    result = network.sync_network("11222333000181", engine=object())

    assert result is None
    assert calls == ["11222333000181"]


def test_company_node_classification_uses_flags_cnae_and_accented_name():
    assert _cache._classify_company_node({"is_farmacia_fp": "sim"}) == "PJ_FARMACIA_POPULAR"
    assert _cache._classify_company_node({"id_cnae_principal": "47.717-01"}) == "PJ_OUTRAS_FARMACIAS"
    assert _cache._classify_company_node({"nome_fantasia": "Drogária São José"}) == "PJ_OUTRAS_FARMACIAS"
    assert _cache._classify_company_node({"razao_social": "Comércio Geral"}) == "PJ_DEMAIS_EMPRESAS"


def test_network_cache_directory_uses_configured_cnpj_root(tmp_path, monkeypatch):
    import data_cache

    monkeypatch.setattr(data_cache, "get_cnpj_cache_root", lambda: str(tmp_path))
    _cache._known_cnpj_dirs.discard(str(tmp_path / "123"))

    first = _cache._get_cnpj_cache_dir("123")
    second = _cache._get_cnpj_cache_dir("123")

    assert first == second == str(tmp_path / "123")
    assert (tmp_path / "123").is_dir()
    assert str(tmp_path / "123") in _cache._known_cnpj_dirs


def test_network_sync_rebuilds_stale_cache_from_parquet_sources(
    tmp_path, monkeypatch
):
    target = "11112222333344"
    owner = "12345678901"
    external = "55556666777788"
    indirect_owner = "10987654321"
    expansion = "99990000111122"
    cache_dir = tmp_path / "cnpjs" / target
    cache_dir.mkdir(parents=True)
    global_dir = tmp_path / "global"
    global_dir.mkdir()

    farmacias = pl.DataFrame(
        {
            "id_cnpj": [10],
            "cnpj": [target],
            "razao_social": ["Farmacia Alvo Ltda"],
            "nome_fantasia": ["Farmacia Alvo"],
            "id_cnae_principal": [4771701],
            "cnae_principal": ["Comercio varejista de produtos farmaceuticos"],
            "is_cnae_farmacia_ausente": [False],
            "municipio": ["Campinas"],
            "uf": ["SP"],
            "situacao_rf": ["ATIVA"],
        }
    )
    socios = pl.DataFrame(
        {
            "cnpj": [target, target, target],
            "cpf_cnpj_socio": [owner, "11111111111", "22222222222"],
            "nome_socio": ["Socio Alvo", "Socio Autorreferenciado", "Socio Representado"],
            "indicador_socio": ["PF", "PF", "PF"],
            "percentual_qualificacao": [50.0, 25.0, 25.0],
            "data_entrada_sociedade": [None, None, None],
            "data_exclusao_sociedade": [None, None, None],
            "is_falecido": [False, False, False],
            "is_cadunico": [False, False, False],
            "is_esocial": [True, False, False],
            "is_seguro_defeso": [False, False, False],
            "cpf_representante": [target, "11111111111", "33333333333"],
            "nome_representante": [None, "Ignorado", None],
        }
    )
    cnaes_secundarios = pl.DataFrame(
        {
            "id_cnpj": [10],
            "id_cnae": [4771702],
            "descricao": ["Comercio varejista de medicamentos"],
        }
    )
    par = pl.DataFrame(
        {
            "cnpj": [target],
            "is_par": [True],
            "qtd_processos_par": [2],
            "par_situacoes": ["Em andamento"],
            "par_primeira_instauracao": [None],
            "par_ultima_instauracao": [None],
            "par_ultima_conclusao": [None],
        },
        schema_overrides={
            "par_primeira_instauracao": pl.Date,
            "par_ultima_instauracao": pl.Date,
            "par_ultima_conclusao": pl.Date,
        },
    )
    nivel2 = pl.DataFrame(
        {
            "cpf_cnpj_socio": [owner],
            "cnpj_empresa": [external],
            "razao_social": ["Drogaria Irma Ltda"],
            "nome_fantasia": ["Drogaria Irma"],
            "id_cnae_principal": [None],
            "municipio": ["Santos"],
            "uf": ["SP"],
            "situacao_rf": ["ATIVA"],
            "is_farmacia_fp": [False],
            "data_entrada_sociedade": [None],
            "data_exclusao_sociedade": [None],
            "cpf_representante": [None],
            "nome_representante": [None],
        }
    )
    nivel3 = pl.DataFrame(
        {
            "cpf_cnpj_socio": [indirect_owner],
            "cnpj_empresa": [external],
            "nome_socio": ["Socio Indireto"],
            "indicador_socio": ["PF"],
            "municipio": ["Santos"],
            "uf": ["SP"],
            "is_falecido": [False],
            "is_cadunico": [True],
            "is_esocial": [False],
            "is_seguro_defeso": [False],
            "data_entrada_sociedade": [None],
            "data_exclusao_sociedade": [None],
            "cpf_representante": [None],
            "nome_representante": [None],
        }
    )
    nivel4 = pl.DataFrame(
        {
            "cpf_cnpj_socio": [indirect_owner],
            "cnpj_empresa": [expansion],
            "razao_social": ["Comercio Geral Ltda"],
            "nome_fantasia": ["Comercio Geral"],
            "id_cnae_principal": [None],
            "municipio": ["Sao Paulo"],
            "uf": ["SP"],
            "situacao_rf": ["ATIVA"],
            "is_farmacia_fp": [False],
            "data_entrada_sociedade": [None],
            "data_exclusao_sociedade": [None],
            "cpf_representante": [None],
            "nome_representante": [None],
        }
    )
    monkeypatch.setattr(_cache, "_get_cnpj_cache_dir", lambda cnpj: str(cache_dir))
    monkeypatch.setattr(_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(_cache, "get_df_dados_farmacia", lambda: farmacias)
    monkeypatch.setattr(
        _cache,
        "get_df_dados_farmacia_cnaes_secundarios",
        lambda: cnaes_secundarios,
    )
    monkeypatch.setattr(_cache, "get_df_dados_socios", lambda: socios)
    monkeypatch.setattr(_cache, "get_df_dados_par", lambda: par)
    monkeypatch.setattr(_cache, "scan_teia_fonte_nivel2", lambda: nivel2.lazy())
    monkeypatch.setattr(_cache, "scan_teia_fonte_nivel3", lambda: nivel3.lazy())
    monkeypatch.setattr(_cache, "scan_teia_fonte_nivel4", lambda: nivel4.lazy())

    source_paths = [
        global_dir / cache_files.FARMACIAS_PARQUET,
        global_dir / cache_files.FARMACIAS_CNAES_SECUNDARIOS_PARQUET,
        global_dir / cache_files.DADOS_PAR_PARQUET,
    ]
    for source_path in source_paths:
        source_path.touch()

    _cache.sync_network(target)

    n2_nodes = pl.read_parquet(cache_dir / cache_files.TEIA_GRAFO_NIVEL2_NODES_PARQUET)
    n2_edges = pl.read_parquet(cache_dir / cache_files.TEIA_GRAFO_NIVEL2_EDGES_PARQUET)
    n3_nodes = pl.read_parquet(cache_dir / cache_files.TEIA_GRAFO_NIVEL3_NODES_PARQUET)
    n3_edges = pl.read_parquet(cache_dir / cache_files.TEIA_GRAFO_NIVEL3_EDGES_PARQUET)
    n4_nodes = pl.read_parquet(cache_dir / cache_files.TEIA_GRAFO_NIVEL4_NODES_PARQUET)
    n4_edges = pl.read_parquet(cache_dir / cache_files.TEIA_GRAFO_NIVEL4_EDGES_PARQUET)

    assert n2_nodes.filter(pl.col("id") == target)["type"].item() == "PJ_ALVO"
    assert n2_nodes.filter(pl.col("id") == target)["is_par"].item() is True
    assert n2_nodes.filter(pl.col("id") == target)["qtd_processos_par"].item() == 2
    assert n2_nodes.filter(pl.col("id") == target)["cnaes_secundarios"].to_list() == [
        [{"id_cnae": 4771702, "descricao": "Comercio varejista de medicamentos"}]
    ]
    assert n2_nodes.filter(pl.col("id") == external)["type"].item() == "PJ_OUTRAS_FARMACIAS"
    assert n2_edges.filter(pl.col("target") == target).height == 3
    assert n2_nodes.filter(pl.col("id") == "33333333333")["label"].item() == "33333333333"
    assert n2_edges.filter(pl.col("id") == f"{target}->{owner}:representante").height == 1
    assert n2_edges.filter(pl.col("id") == "11111111111->11111111111:representante").is_empty()
    assert n3_nodes.filter(pl.col("id") == indirect_owner)["is_cadunico"].item() is True
    assert n3_edges.filter(pl.col("target") == external).height == 1
    assert n4_nodes.filter(pl.col("id") == expansion)["type"].item() == "PJ_DEMAIS_EMPRESAS"
    assert n4_edges.filter(pl.col("target") == expansion).height == 1

    graph_paths = [
        cache_dir / cache_files.TEIA_GRAFO_NIVEL2_NODES_PARQUET,
        cache_dir / cache_files.TEIA_GRAFO_NIVEL3_NODES_PARQUET,
        cache_dir / cache_files.TEIA_GRAFO_NIVEL4_NODES_PARQUET,
        cache_dir / cache_files.TEIA_GRAFO_NIVEL2_EDGES_PARQUET,
        cache_dir / cache_files.TEIA_GRAFO_NIVEL3_EDGES_PARQUET,
        cache_dir / cache_files.TEIA_GRAFO_NIVEL4_EDGES_PARQUET,
    ]

    def mark_sources_older_than_graph():
        graph_mtime = min(
            (cache_dir / name).stat().st_mtime
            for name in (
                cache_files.TEIA_GRAFO_NIVEL2_NODES_PARQUET,
                cache_files.TEIA_GRAFO_NIVEL3_NODES_PARQUET,
                cache_files.TEIA_GRAFO_NIVEL4_NODES_PARQUET,
            )
        )
        for source_path in source_paths:
            os.utime(source_path, (graph_mtime - 2, graph_mtime - 2))

    mark_sources_older_than_graph()
    _cache.sync_network(target)  # Os seis Parquets válidos produzem cache hit.

    for graph_path in graph_paths:
        pl.DataFrame({"schema_antigo": ["invalido"]}).write_parquet(graph_path)
        mark_sources_older_than_graph()
        _cache.sync_network(target)
        assert "id" in pl.read_parquet(graph_path).columns

    farmacias_path, cnaes_path, par_path = source_paths

    farmacias_path.unlink()
    _cache.sync_network(target)
    farmacias_path.touch()
    mark_sources_older_than_graph()

    cnaes_path.unlink()
    _cache.sync_network(target)
    cnaes_path.touch()
    mark_sources_older_than_graph()

    for stale_path in (farmacias_path, cnaes_path, par_path):
        graph_mtime = min(path.stat().st_mtime for path in graph_paths[:3])
        os.utime(stale_path, (graph_mtime + 10, graph_mtime + 10))
        _cache.sync_network(target)
        mark_sources_older_than_graph()


def test_network_sync_writes_placeholder_root_when_target_is_absent(
    tmp_path, monkeypatch
):
    target = "11112222333344"
    cache_dir = tmp_path / "cnpjs" / target
    cache_dir.mkdir(parents=True)
    monkeypatch.setattr(_cache, "_get_cnpj_cache_dir", lambda _cnpj: str(cache_dir))
    monkeypatch.setattr(
        _cache,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame(
            schema={
                "id_cnpj": pl.Int64,
                "cnpj": pl.Utf8,
                "razao_social": pl.Utf8,
                "nome_fantasia": pl.Utf8,
                "id_cnae_principal": pl.Int32,
                "cnae_principal": pl.Utf8,
                "is_cnae_farmacia_ausente": pl.Boolean,
                "municipio": pl.Utf8,
                "uf": pl.Utf8,
                "situacao_rf": pl.Utf8,
            }
        ),
    )
    monkeypatch.setattr(
        _cache,
        "get_df_dados_farmacia_cnaes_secundarios",
        lambda: pl.DataFrame(
            schema={"id_cnpj": pl.Int32, "id_cnae": pl.Int32, "descricao": pl.Utf8}
        ),
    )
    monkeypatch.setattr(
        _cache,
        "get_df_dados_socios",
        lambda: pl.DataFrame(schema={"cnpj": pl.Utf8, "cpf_cnpj_socio": pl.Utf8}),
    )
    monkeypatch.setattr(
        _cache,
        "get_df_dados_par",
        lambda: pl.DataFrame(schema={"cnpj": pl.Utf8, "is_par": pl.Boolean}),
    )

    _cache.sync_network(target)

    root = pl.read_parquet(cache_dir / cache_files.TEIA_GRAFO_NIVEL2_NODES_PARQUET)
    assert root.filter(pl.col("id") == target)["label"].item() == f"CNPJ {target}"
    assert root.filter(pl.col("id") == target)["is_par"].item() is False


def test_network_sync_logs_source_failure_without_swallowing_the_diagnostic(
    tmp_path, monkeypatch, capsys
):
    target = "11112222333344"
    cache_dir = tmp_path / "cnpjs" / target
    cache_dir.mkdir(parents=True)
    monkeypatch.setattr(_cache, "_get_cnpj_cache_dir", lambda _cnpj: str(cache_dir))
    monkeypatch.setattr(
        _cache,
        "get_df_dados_farmacia",
        lambda: (_ for _ in ()).throw(RuntimeError("fonte indisponivel")),
    )

    _cache.sync_network(target)

    output = capsys.readouterr().out
    assert "Erro ao gerar Teia Societaria" in output
    assert "fonte indisponivel" in output
    assert "Traceback (most recent call last)" in output
