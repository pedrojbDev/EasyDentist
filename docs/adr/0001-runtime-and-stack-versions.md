# ADR 0001: versões estáveis fixadas

**Status:** Aceito — M1.1, 2026-09-16

## Contexto

O plano exige versões estáveis e suportadas. Elas devem estar fixadas em runtimes,
manifests, imagens e lockfiles, sem forçar Python 3.13 ou Next 16.

## Decisão

Usar Node 24.19.0 LTS/pnpm 11.10.0, Python 3.12.14/uv 0.12.5, Next 15.5.25,
React 19.2.7, FastAPI 0.141.1, PostgreSQL 17.6 e as versões complementares da
matriz. Os manifests usam igualdade para dependências diretas, o lockfile fecha
as transitivas e as imagens usam tags de release completas.

O workspace fixa PostCSS 8.5.23 via override transitivo pois a última manutenção
do Next 15.5 ainda resolve uma versão afetada por CVEs. O override será removido
quando uma manutenção do Next 15 o tornar redundante.

Vitest usa 4.1.11, a primeira versão sem as vulnerabilidades conhecidas no audit
atual. A configuração de testes é deliberadamente mínima e foi validada nessa
linha estável.

## Consequências

O stack recebe uma base madura e reproduzível, ao custo de não adotar recursos
novos de Next 16 ou Python 3.13/3.14 agora. Uma atualização futura é uma mudança
explícita, acompanhada de regeneração de lockfiles e validação integral.
