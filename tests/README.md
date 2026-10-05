# Arquitetura de testes

## Categorias Python

Os marcadores são aplicados durante a coleta por `tests/conftest.py`:

- `unit`: lógica isolada de domínio, serviços, cache e utilitários. Os limites externos são controlados pelo teste.
- `contract`: rotas HTTP e seus parâmetros, validações, códigos de status e schemas de resposta.
- `integration`: fluxos que atravessam mais de um componente, ciclo de vida da aplicação ou persistência real isolada.
- `backend`: marcador adicional para qualquer teste localizado em `tests/backend/`.

Cada teste Python recebe exatamente uma categoria principal (`unit`, `contract` ou `integration`). Testes do backend também recebem `backend`, para que seja possível combinar filtros como `-m 'backend and contract'`. Regras por módulo ficam centralizadas em `tests/conftest.py`; uma nova pasta de testes precisa ser registrada ali.

Execute as categorias a partir da raiz do repositório:

```powershell
python -m pytest -m unit
python -m pytest -m contract
python -m pytest -m integration
python -m pytest -m backend
```

## Frontend

`npm run test:unit` executa os testes Vitest de stores, composables, utilitários, componentes e views. `npm run test:integration` inicia uma API FastAPI local de teste e executa a integração HTTP descrita abaixo.

## Integração HTTP frontend/backend

O runner `frontend/scripts/run-api-integration.mjs` inicia `tests/integration/api_app.py` em uma porta local livre, cria uma pasta temporária exclusiva para preferências/evidências e configura o frontend para usar essa API. A aplicação de teste monta os routers reais de preferências e evidências; o teste usa as stores Pinia reais e Axios sem mocks. O fluxo verifica gravação, resposta HTTP, leitura de volta e rejeição de uma evidência duplicada.

Esse teste cobre a integração entre o cliente Vue e os contratos/serviços HTTP reais de preferências e evidências. Ele não inicia o ciclo de vida completo do Sentinela nem se conecta ao SQL Server; os dados persistidos ficam limitados à pasta temporária do runner.
