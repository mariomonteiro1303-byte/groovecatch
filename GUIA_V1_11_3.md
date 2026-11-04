# GrooveCatch Cloud v1.11.3 - Publicação e identidade

1. Envie o conteúdo deste pacote para a raiz do repositório GitHub existente. Não crie um segundo serviço no Render.
2. O `render.yaml` não exige mais GROOVECATCH_ACCESS_PASSWORD. Em serviço já criado manualmente, pode manter a variável antiga, mas a aplicação não a utiliza para bloquear visitantes.
3. **Mantenha** `GROOVECATCH_SECRET_KEY` e `GROOVECATCH_ADS_ADMIN_PASSWORD` configuradas no Render. Não divulgue seus valores.
4. Para exibir seu nome, configure `GROOVECATCH_DEVELOPER_NAME` no Render (ex.: nome profissional desejado). Para contato, configure `GROOVECATCH_CONTACT_EMAIL`. Não publique e-mail pessoal sem avaliar spam e privacidade.
5. Aguarde deploy. Teste `/`, `/sobre`, `/privacidade`, `/termos` sem login e `/admin/ads` com login próprio.
6. **Atenção**: o plano Free pode suspender a instância. Os dados dos anúncios em SQLite local não têm persistência garantida.
7. O rate limit é local, aproximado e não distribuído. O serviço público ainda precisa de testes de carga, quotas de armazenamento e revisão de segurança.
8. As páginas de privacidade e termos são rascunhos informativos, não documentos jurídicos completos. Revise antes de monetizar com redes externas.
