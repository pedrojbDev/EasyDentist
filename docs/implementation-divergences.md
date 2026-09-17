# Divergências encontradas antes do M1.1

| Estado observado                                                                                                      | Resolução compatível com o plano                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A especificação foi solicitada como `PLAN.md`, mas o único arquivo presente é `plan.md`.                              | `plan.md` foi lido integralmente e é a fonte de verdade desta implementação. Nenhum conteúdo foi renomeado sem solicitação explícita.                                                                    |
| O diretório não continha `.git`, código, manifests ou CI.                                                             | A fundação foi criada no diretório atual; a publicação remota permanece pendente da inicialização, autenticação exclusiva em `github.com` como `pedrojbDev` e primeira execução verde do GitHub Actions. |
| A primeira opção de storage S3-compatible, MinIO, declara AGPLv3 e a tag escolhida não estava disponível no registro. | SeaweedFS 4.29, com licença Apache-2.0 e S3 local, substitui MinIO. O plano exige storage S3-compatible, não um produto específico.                                                                      |
| SeaweedFS poderia parecer um serviço pronto para produção.                                                            | É uma dependência exclusiva do Docker Compose local no M1.1. Produção exige storage gerenciado ou signing keys, criptografia e backup explicitamente configurados.                                       |

O M1.1 não inicia M1.2: migrations/Alembic são não aplicáveis neste marco. As
dependências MPL encontradas receberam exceções exatas por pacote, versão e
licença após aviso explícito; MPL continua fora da allowlist geral.
