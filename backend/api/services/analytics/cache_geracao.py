"""Cache em memoria por geracao dos dados globais.

Guarda resultados caros que so dependem dos parametros e dos Parquets
carregados: ao recarregar o cache global (nova geracao em data_cache), as
entradas antigas sao descartadas. Usado pelos servicos de analise no lugar de
caches locais em cada modulo.
"""

import threading
import time
from collections import OrderedDict
from typing import Callable, Optional, TypeVar, cast

from data_cache import get_cache_generation

_T = TypeVar("_T")


class CacheGeracao:
    """
    LRU por geracao dos dados, com expiracao opcional e calculo unico por chave.

    Varias requisicoes que pedem a mesma chave ao mesmo tempo (ex.: os endpoints
    disparados por uma mudanca de filtro) calculam uma vez so: a primeira calcula
    e as demais esperam pelo resultado. Erros nunca entram no cache.

    Args:
        max_itens: numero maximo de entradas (as menos usadas saem primeiro).
        ttl_segundos: idade maxima de uma entrada; None = so a geracao invalida.
    """

    def __init__(self, max_itens: int, ttl_segundos: Optional[float] = None) -> None:
        if max_itens < 1:
            raise ValueError("max_itens deve ser pelo menos 1.")
        self._max_itens = max_itens
        self._ttl = ttl_segundos
        self._itens: "OrderedDict[tuple[object, ...], tuple[float, object]]" = OrderedDict()
        self._lock = threading.Lock()
        self._calculando: dict[tuple[object, ...], threading.Lock] = {}

    def _valido(self, chave: tuple[object, ...], agora: float) -> bool:
        """True se a chave esta no cache e nao expirou (chamar com _lock)."""
        item = self._itens.get(chave)
        return item is not None and (self._ttl is None or agora - item[0] <= self._ttl)

    def _limpar(self, geracao: object, agora: float) -> None:
        """Descarta geracoes antigas e entradas expiradas (chamar com _lock)."""
        for chave in [
            k for k, (criado_em, _valor) in self._itens.items()
            if k[0] != geracao or (self._ttl is not None and agora - criado_em > self._ttl)
        ]:
            del self._itens[chave]

    def obter(self, chave: tuple[object, ...], calcular: Callable[[], _T]) -> _T:
        """Valor da chave na geracao atual; calcula (uma vez) se ausente."""
        chave = (get_cache_generation(), *chave)
        with self._lock:
            agora = time.monotonic()
            self._limpar(chave[0], agora)
            if self._valido(chave, agora):
                self._itens.move_to_end(chave)
                return cast(_T, self._itens[chave][1])
            calculando = self._calculando.setdefault(chave, threading.Lock())
        with calculando:
            with self._lock:
                if self._valido(chave, time.monotonic()):
                    return cast(_T, self._itens[chave][1])
            try:
                valor = calcular()
                with self._lock:
                    self._itens[chave] = (time.monotonic(), valor)
                    self._itens.move_to_end(chave)
                    while len(self._itens) > self._max_itens:
                        self._itens.popitem(last=False)
                return valor
            finally:
                with self._lock:
                    self._calculando.pop(chave, None)
