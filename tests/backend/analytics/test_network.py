from datetime import date

import polars as pl
import pytest

from api.services.analytics import network


CNPJ = "12345678000190"


def _node_row(**changes):
    row = {
        "id": CNPJ,
        "label": "Farmacia",
        "type": "PJ_FARMACIA_POPULAR",
        "is_cadunico": False,
        "is_esocial": False,
        "is_seguro_defeso": False,
        "is_cnae_farmacia_ausente": False,
    }
    row.update(changes)
    return row


def test_network_nodes_add_audit_percentage_and_criticality_from_period_movement(monkeypatch):
    monkeypatch.setattr(
        network,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1], "cnpj": [CNPJ], "is_conexao_ativa": [True]}),
    )
    monkeypatch.setattr(
        network,
        "get_df",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [1, 1], "periodo": [date(2020, 1, 1), date(2020, 2, 1)],
                "total_vendas": [100.0, 100.0], "total_sem_comprovacao": [10.0, 20.0],
            }
        ),
    )
    node = network._build_network_nodes(
        pl.DataFrame([_node_row()]), date(2020, 1, 1), date(2020, 1, 31)
    )[0]
    assert node.percentual_nao_comprovacao == 10.0
    assert node.criticidade_nao_comprovacao == "ATENÇÃO"
    assert node.conexao_ms == "Ativa"


def test_network_requires_auditable_context_for_pharmacy_nodes(monkeypatch):
    monkeypatch.setattr(
        network,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1], "cnpj": [CNPJ], "is_conexao_ativa": [True]}),
    )
    monkeypatch.setattr(
        network,
        "get_df",
        lambda: pl.DataFrame({"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [0.0], "total_sem_comprovacao": [0.0]}),
    )
    with pytest.raises(RuntimeError, match="ausentes no perfil"):
        network._build_network_nodes(pl.DataFrame([_node_row(id="99999999000199")]), None, None)

    with pytest.raises(RuntimeError, match="sem percentual"):
        network._build_network_node(_node_row(percentual_nao_comprovacao=None))

    monkeypatch.setattr(network, "_get_fp_audit_context_by_cnpj", lambda *_args: {})
    with pytest.raises(RuntimeError, match="Contexto de auditoria nao calculado"):
        network._build_network_nodes(pl.DataFrame([_node_row()]), None, None)


def test_network_normalizes_documents_and_classifies_thresholds():
    assert network._normalize_document("12.345.678/0001-90") == CNPJ
    assert network._classify_nao_comprovacao(15.0) == "CRÍTICO"
    assert network._classify_nao_comprovacao(5.0) == "ATENÇÃO"
    assert network._classify_nao_comprovacao(4.99) == "NORMAL"


def test_network_summary_counts_distinct_nodes_links_and_levels(monkeypatch):
    monkeypatch.setattr(network, "_get_cnpj_cache_dir", lambda _cnpj: "cache")
    nodes = pl.DataFrame({"id": ["n1", "n2"], "network_level": ["n1", "n1"]})
    edges = pl.DataFrame({"id": ["e1"], "network_level": ["n1"]})
    monkeypatch.setattr(
        network,
        "_read_parquet_or_empty",
        lambda path: nodes if path.endswith(network.TEIA_GRAFO_NIVEL2_NODES_PARQUET)
        else edges if path.endswith(network.TEIA_GRAFO_NIVEL2_EDGES_PARQUET)
        else pl.DataFrame(),
    )
    summary = network._build_network_summary(CNPJ)
    assert summary.total_entities == 2
    assert summary.total_links == 1
    assert summary.levels["n1"].entities == 2
    assert summary.levels["n1"].links == 1
    monkeypatch.setattr(network.os.path, "exists", lambda _path: False)
    assert network._read_parquet_or_empty("cache/missing.parquet").is_empty()


def test_network_audit_context_handles_non_pharmacy_zero_sales_and_periods(monkeypatch):
    assert network._get_fp_audit_context_by_cnpj([_node_row(type="PF")], None, None) == {}
    profile = pl.DataFrame(
        {"id_cnpj": [1, 2], "cnpj": [CNPJ, "00000000000001"], "is_conexao_ativa": [False, True]}
    )
    movement = pl.DataFrame(
        {
            "id_cnpj": [1, 1, 1],
            "periodo": [date(2020, 1, 1), date(2020, 2, 1), date(2021, 1, 1)],
            "total_vendas": [100.0, 100.0, 900.0],
            "total_sem_comprovacao": [10.0, 30.0, 900.0],
        }
    )
    monkeypatch.setattr(network, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(network, "get_df", lambda: movement)
    result = network._get_fp_audit_context_by_cnpj(
        [_node_row(id="12.345.678/0001-90"), _node_row(id="00000000000001")],
        date(2020, 2, 1),
        date(2020, 12, 31),
    )
    assert result == {
        CNPJ: {"percentual_nao_comprovacao": 30.0, "conexao_ms": "Inativa"},
        "00000000000001": {"percentual_nao_comprovacao": 0.0, "conexao_ms": "Ativa"},
    }


def test_network_audit_context_rejects_invalid_profile_and_movement_contracts(monkeypatch):
    pharmacy = [_node_row()]
    monkeypatch.setattr(
        network,
        "get_df",
        lambda: pl.DataFrame({"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [1.0], "total_sem_comprovacao": [0.0]}),
    )
    monkeypatch.setattr(network, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": [CNPJ]}))
    with pytest.raises(RuntimeError, match="perfil_estabelecimento"):
        network._get_fp_audit_context_by_cnpj(pharmacy, None, None)

    monkeypatch.setattr(
        network,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1], "cnpj": [CNPJ], "is_conexao_ativa": [True]}),
    )
    monkeypatch.setattr(network, "get_df", lambda: pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(RuntimeError, match="movimentacao"):
        network._get_fp_audit_context_by_cnpj(pharmacy, None, None)

    monkeypatch.setattr(
        network,
        "get_df",
        lambda: pl.DataFrame({"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [1.0], "total_sem_comprovacao": [0.0]}),
    )
    with pytest.raises(RuntimeError, match="ausentes no perfil"):
        network._get_fp_audit_context_by_cnpj([_node_row(id="99999999000199")], None, None)

    monkeypatch.setattr(
        network,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1], "cnpj": [CNPJ], "is_conexao_ativa": [None]}, schema_overrides={"is_conexao_ativa": pl.Boolean}),
    )
    with pytest.raises(RuntimeError, match="is_conexao_ativa invalida"):
        network._get_fp_audit_context_by_cnpj(pharmacy, None, None)


def test_network_node_and_edge_schemas_apply_person_and_edge_defaults():
    person = network._build_network_node(
        {
            "id": "12345678901", "label": None, "type": "PF", "nome_socio": "Socio",
            "razao_social": "ignored", "cnae_principal": "ignored", "cnaes_secundarios": ["ignored"],
            "is_cadunico": True, "is_esocial": True, "is_seguro_defeso": False,
            "is_cnae_farmacia_ausente": False,
        }
    )
    assert person.label == ""
    assert person.razao_social is None and person.nome_socio == "Socio"
    assert person.cnae_principal is None and person.cnaes_secundarios == []
    assert person.is_par is False and person.qtd_processos_par == 0
    assert person.par_situacoes is None

    edge = network._build_network_edge({"id": "e1", "source": "a", "target": "b", "label": "", "is_ativo": None})
    assert edge.label is None and edge.type == "socio" and edge.is_ativo is True
    assert edge.data_entrada_sociedade is None and edge.data_exclusao_sociedade is None
    assert network._level_count(pl.DataFrame(), "n1") == 0
    assert network._level_count(pl.DataFrame({"id": [1]}), "n1") == 0
    assert network._level_count(pl.DataFrame({"network_level": ["n1", "n2"]}), "n1") == 1


def test_network_pharmacy_node_requires_criticality_and_connection_fields():
    base = _node_row(percentual_nao_comprovacao=10.0, criticidade_nao_comprovacao="ATENÇÃO", conexao_ms="Ativa")
    with pytest.raises(RuntimeError, match="sem criticidade"):
        network._build_network_node({**base, "criticidade_nao_comprovacao": None})
    with pytest.raises(RuntimeError, match="sem conexao_ms valida"):
        network._build_network_node({**base, "conexao_ms": "Desconhecida"})


def test_network_parquet_reader_handles_corrupt_files_and_summary_counts_unique_ids(monkeypatch):
    monkeypatch.setattr(network.os.path, "exists", lambda _path: False)
    assert network._read_parquet_or_empty("missing.parquet").is_empty()

    monkeypatch.setattr(network.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(network.pl, "read_parquet", lambda _path: (_ for _ in ()).throw(ValueError("corrupt")))
    assert network._read_parquet_or_empty("bad.parquet").is_empty()

    monkeypatch.setattr(network, "_get_cnpj_cache_dir", lambda _cnpj: "cache")
    frames = {
        network.TEIA_GRAFO_NIVEL2_NODES_PARQUET: pl.DataFrame({"id": ["n1", None], "network_level": ["n1", "root"]}),
        network.TEIA_GRAFO_NIVEL3_NODES_PARQUET: pl.DataFrame({"id": ["n1", "n3"], "network_level": ["n2", "n3"]}),
        network.TEIA_GRAFO_NIVEL4_NODES_PARQUET: pl.DataFrame({"other": [1]}),
        network.TEIA_GRAFO_NIVEL2_EDGES_PARQUET: pl.DataFrame({"id": ["e1"], "network_level": ["n1"]}),
        network.TEIA_GRAFO_NIVEL3_EDGES_PARQUET: pl.DataFrame({"id": ["e1", "e3"], "network_level": ["n2", "n3"]}),
        network.TEIA_GRAFO_NIVEL4_EDGES_PARQUET: pl.DataFrame({"other": [1]}),
    }
    monkeypatch.setattr(network, "_read_parquet_or_empty", lambda path: next(value for name, value in frames.items() if path.endswith(name)))
    summary = network._build_network_summary(CNPJ)
    assert summary.total_entities == 2
    assert summary.total_links == 2
    assert summary.levels["n1"].entities == 1
    assert summary.levels["n1"].links == 1


def test_network_level_two_response_handles_absent_edges_and_parquet_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(network, "_get_cnpj_cache_dir", lambda _cnpj: str(tmp_path))
    monkeypatch.setattr(network, "sync_network", lambda _cnpj: None)
    monkeypatch.setattr(network, "_build_network_nodes", lambda *_args: [])
    monkeypatch.setattr(network, "_build_network_summary", lambda _cnpj: None)
    monkeypatch.setattr(network.pl, "read_parquet", lambda _path: pl.DataFrame())
    monkeypatch.setattr(network.os.path, "exists", lambda _path: False)
    response = network.get_teia_grafo_nivel2(CNPJ, engine=None)
    assert response.nodes == [] and response.edges == [] and response.summary is None

    monkeypatch.setattr(network.pl, "read_parquet", lambda _path: (_ for _ in ()).throw(ValueError("bad parquet")))
    with pytest.raises(RuntimeError, match="Erro ao ler Parquet de teia"):
        network.get_teia_grafo_nivel2(CNPJ, engine=None)


def test_network_expansion_endpoints_return_empty_when_files_or_matching_edges_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(network, "_get_cnpj_cache_dir", lambda _cnpj: str(tmp_path))
    monkeypatch.setattr(network, "sync_network", lambda _cnpj: None)
    monkeypatch.setattr(network.os.path, "exists", lambda _path: False)
    assert network.get_teia_grafo_nivel3_expansao(CNPJ, "target").nodes == []
    assert network.get_teia_grafo_nivel4_expansao(CNPJ, "12345678901").edges == []
    assert network.get_teia_grafo_nivel3_full(CNPJ).nodes == []
    assert network.get_teia_grafo_nivel4_full(CNPJ).edges == []

    monkeypatch.setattr(network.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(network.pl, "read_parquet", lambda _path: pl.DataFrame(schema={"id": pl.Utf8, "source": pl.Utf8, "target": pl.Utf8, "type": pl.Utf8, "label": pl.Utf8}))
    assert network.get_teia_grafo_nivel3_expansao(CNPJ, "target").edges == []
    assert network.get_teia_grafo_nivel4_expansao(CNPJ, "12345678901").nodes == []


def test_network_expansion_endpoints_select_related_entities_and_wrap_bad_parquets(monkeypatch, tmp_path):
    monkeypatch.setattr(network, "_get_cnpj_cache_dir", lambda _cnpj: str(tmp_path))
    monkeypatch.setattr(network, "sync_network", lambda _cnpj: None)
    monkeypatch.setattr(network, "_build_network_summary", lambda _cnpj: None)
    built_nodes = []

    def build_nodes(frame, *_args, **kwargs):
        built_nodes.append((frame.height, kwargs.get("default_type")))
        return []

    monkeypatch.setattr(network, "_build_network_nodes", build_nodes)
    monkeypatch.setattr(network.os.path, "exists", lambda _path: True)

    n3_edges = pl.DataFrame(
        {
            "id": ["e1", "e2", "ignore"],
            "source": ["12345678901", "company", "other"],
            "target": ["target", "12345678901", "not-target"],
            "type": ["socio", "representante", "socio"],
            "label": ["socio", "representante", "ignore"],
        }
    )
    n4_edges = pl.DataFrame(
        {
            "id": ["e3", "e4", "ignore"],
            "source": ["12345678901", "company", "other"],
            "target": ["company", "12345678901", "12345678901"],
            "type": ["socio", "representante", "socio"],
            "label": ["socio", "representante", "ignore"],
        }
    )
    nodes = pl.DataFrame({"id": ["12345678901", "company"], "label": ["Pessoa", "Empresa"]})

    def read(path):
        if path.endswith(network.TEIA_GRAFO_NIVEL3_EDGES_PARQUET):
            return n3_edges
        if path.endswith(network.TEIA_GRAFO_NIVEL4_EDGES_PARQUET):
            return n4_edges
        return nodes

    monkeypatch.setattr(network.pl, "read_parquet", read)
    n3 = network.get_teia_grafo_nivel3_expansao(CNPJ, "target")
    assert {edge.id for edge in n3.edges} == {"e1", "e2"}
    assert n3.nodes == [] and built_nodes[-1] == (2, "PF")
    n4 = network.get_teia_grafo_nivel4_expansao(CNPJ, "12345678901")
    assert {edge.id for edge in n4.edges} == {"e3", "e4"}
    assert n4.nodes == [] and built_nodes[-1] == (1, "PJ")

    n3_full = network.get_teia_grafo_nivel3_full(CNPJ)
    n4_full = network.get_teia_grafo_nivel4_full(CNPJ)
    assert n3_full.nodes == [] and built_nodes[-2:] == [(2, "PF"), (2, "PJ")]

    monkeypatch.setattr(network.pl, "read_parquet", lambda _path: (_ for _ in ()).throw(ValueError("broken")))
    with pytest.raises(RuntimeError, match="Erro ao expandir no target"):
        network.get_teia_grafo_nivel3_expansao(CNPJ, "target")
    with pytest.raises(RuntimeError, match="Erro ao expandir socio"):
        network.get_teia_grafo_nivel4_expansao(CNPJ, "12345678901")
    with pytest.raises(RuntimeError, match="Erro batch N3"):
        network.get_teia_grafo_nivel3_full(CNPJ)
    with pytest.raises(RuntimeError, match="Erro batch N4"):
        network.get_teia_grafo_nivel4_full(CNPJ)
