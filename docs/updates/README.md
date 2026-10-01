# Manifestos de atualização

O atualizador do Sentinela consulta um endereço fixo, gravado no executável
(`backend/api/services/system_update.py`, `MANIFEST_URL`). Existem dois:

| Arquivo | Quem consulta | Situação |
|---|---|---|
| `manifest.json` + `manifest.sig` | Sentinela 1.x | **Congelado em 1.7.0.** A 1.x nunca recebe oferta da 2.0, que exige o pacote completo com as novas bases. |
| `v2/manifest.json` + `v2/manifest.sig` | Sentinela 2.0 ou posterior | Manifesto ativo: é este que cada release atualiza e assina. |

Regras:

- **Não altere o manifesto legado.** Qualquer byte alterado invalida a assinatura e a 1.x o rejeita. O script de assinatura recusa assiná-lo e confere a assinatura dele a cada release.
- **Não apague o manifesto legado.** O `mkdocs gh-deploy --force` substitui o site inteiro: se o arquivo sumir daqui, some do GitHub Pages.
- A migração da 1.x para a 2.0 é feita fora do atualizador, com o pacote completo.
