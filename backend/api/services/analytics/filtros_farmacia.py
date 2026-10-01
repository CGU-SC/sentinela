"""Filtros de farmacia das telas de analise, num objeto unico.

Sao os filtros que escolhem o universo de farmacias por atributo da propria
farmacia: cadastro, % e valor sem comprovacao, socios, teia, populacao do
municipio, autorizacoes em sequencia, volume atipico e UFs sem fronteira.
Territorio, periodo e lista de CNPJs ficam fora: cada endpoint os trata a seu
modo.

Criado uma vez pela dependencia dos endpoints (filtros_farmacia) e repassado
inteiro aos services e a build_perfil_filtrado. Filtro novo: campo aqui, Query
na dependencia, normalizador em indicadores._INDICADOR_SCOPE_FILTER_FIELDS e a
regra no service que o aplica (tests/test_filtros_farmacia.py confere a
cobertura).
"""

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class FiltrosFarmacia:
    """Valores neutros (None/False) = filtro desligado."""

    perc_min: Optional[float] = None
    perc_max: Optional[float] = None
    val_min: Optional[float] = None
    situacao_rf: Optional[str] = None
    conexao_ms: Optional[str] = None
    porte_empresa: Optional[str] = None
    grande_rede: Optional[str] = None
    cnpj_raiz: Optional[str] = None
    unidade_pf: Optional[str] = None
    estabelecimento: Optional[str] = None
    par_teia: Optional[str] = None
    socio_beneficio: Optional[str] = None
    socio_esocial: Optional[str] = None
    cnae_incompativel: bool = False
    socio_idade_atipica: bool = False
    socio_falecido: bool = False
    populacao_min: Optional[int] = None
    populacao_max: Optional[int] = None
    seq_tipo: Optional[str] = None
    seq_severidade_min: Optional[int] = None
    seq_dias_min: Optional[int] = None
    seq_dias_max: Optional[int] = None
    volume_atipico: bool = False
    volume_atipico_limite: Optional[float] = None
    dispersao_uf_sem_fronteira: bool = False
    dispersao_uf_sem_fronteira_limite: Optional[float] = None

    def como_dict(self) -> dict[str, Any]:
        """Campos como kwargs, para codigo interno que ainda recebe os filtros soltos."""
        return asdict(self)

    @classmethod
    def de_mapeamento(cls, valores: Mapping[str, Any]) -> "FiltrosFarmacia":
        """Objeto a partir de um mapeamento com todos os campos (chaves extras sao ignoradas)."""
        return cls(**{nome: valores[nome] for nome in CAMPOS_FILTROS_FARMACIA})


CAMPOS_FILTROS_FARMACIA: tuple[str, ...] = tuple(campo.name for campo in fields(FiltrosFarmacia))
SEM_FILTRO_FARMACIA = FiltrosFarmacia()
