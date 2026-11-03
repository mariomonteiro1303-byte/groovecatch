# GrooveCatch Cloud v1.11.2: publicidade multicanal

## Painel
1. Configure `GROOVECATCH_ADS_ADMIN_PASSWORD` no Render > Environment, com senha forte e diferente da senha do piloto.
2. Acesse `/admin/ads` e entre com essa senha (além da autenticação do piloto, quando habilitada).
3. Cadastre anúncios de afiliados, patrocinadores ou criativos de redes que **autorizem** esse formato, com título, descrição, link HTTPS e imagem HTTPS opcional.
4. Escolha topo, conteúdo ou rodapé. Um anúncio ativo é exibido por posição; alternância aproximada por minuto.
5. Edite, pause, exclua e acompanhe contadores de exibições/cliques no painel.

## Restrições e limites reais
- **Sem scripts externos**: não é integração automática com AdSense, Adsterra, Monetag ou Meta Audience Network. Essas redes precisam aprovar o site e o formato. Não cole scripts em campos.
- **Sem receita automática**: cadastro de afiliado só gera comissão se o programa aprovar e a compra cumprir os termos.
- **Banco temporário**: no Render Free o SQLite local NÃO persiste de forma confiável após reinícios/deploys. Os cadastros e contadores podem sumir. Para produção use Postgres gerenciado ou configuração persistente externa.
- Contadores são eventos brutos, não métricas antifraude ou faturamento. Recarregamentos contam impressões; cliques não são vendas.
- Não há cookies de publicidade de terceiros nesta edição; URLs de imagem externas podem expor o IP do visitante ao fornecedor da imagem. Para maior privacidade, hospede imagens autorizadas no próprio projeto.
- A senha administrativa deve ser diferente da senha de acesso ao piloto. Não publique segredos no GitHub.
- Conteúdo baixável de terceiros pode inviabilizar aprovação em algumas redes. Avalie direitos autorais e termos antes de publicar.
- O Render Free pode suspender a instância e tem limites de processamento e armazenamento.

## Testes recomendados
1. Sem senha administrativa, `/admin/ads` deve responder 404.
2. Com senha, cadastrar anúncio e conferir exibição na posição escolhida.
3. Pausar anúncio e confirmar que desaparece.
4. Conferir link HTTPS, contagem de cliques e redirecionamento.
5. Editar e excluir anúncio.
6. Validar exibição mobile e regressões de downloads/conversões.
