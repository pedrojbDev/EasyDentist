# ADR 0003: princípios SOLID e fronteiras modulares

**Status:** Aceito — M1.1, 2026-09-16

## Decisão

O backend aplica SOLID de modo pragmático, preservando limites explícitos sem
adicionar camadas genéricas sem consumidor.

- Um router trata somente HTTP: rota, validação de transporte, serialização e
  mapeamento de erros.
- Um service ou use case concentra a orquestração de uma operação de aplicação.
- Um repository concentra a persistência de seu agregado ou consulta.
- Regras de domínio não importam FastAPI nem SQLAlchemy.
- Ports definidos com `Protocol` só são introduzidos onde há uma fronteira externa
  realmente substituível (por exemplo, provedor de armazenamento ou mensageria),
  não como abstração antecipada.
- `BaseRepository` e `BaseService` genéricos são proibidos. Cada colaboração deve
  exibir as operações e invariantes que de fato suporta.

`app/main.py` permanece um composition root mínimo: expõe somente
`app = create_app()`. A application factory é responsável por configurar
FastAPI e registrar routers. No M1.1, o router de plataforma contém somente o
health check técnico; ele não cria módulos vazios de domínio.

## Consequências

O custo de uma nova fronteira é pago apenas quando uma funcionalidade a requer,
mas cada módulo futuro tem responsabilidades previsíveis e testáveis. Testes
arquiteturais leves protegem o composition root e impedem declaração de rotas em
`main.py`. Auth, tenancy, repositories de domínio e migrations continuam fora
do M1.1 e começam nos marcos definidos para eles.
