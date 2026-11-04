# GrooveCatch Cloud v1.11.1: publicidade de terceiros

## Como ativar

No Render, abra o serviço > Environment e adicione até três conjuntos de variáveis:

- `GROOVECATCH_SPONSOR_1_TITLE`: nome da oferta, por exemplo `Loja parceira de acessórios`.
- `GROOVECATCH_SPONSOR_1_DESCRIPTION`: descrição curta e verdadeira.
- `GROOVECATCH_SPONSOR_1_URL`: link HTTPS autorizado pelo anunciante ou programa de afiliados.

Repita para os números 2 e 3. Reinicie ou faça deploy para aplicar. Se não houver título e URL HTTPS válidos, a seção de anúncios fica oculta. O sistema não inventa anunciantes.

## Política e transparência

- Os cards são identificados como `Publicidade · Patrocinado` e usam `rel="sponsored nofollow noopener noreferrer"`.
- A aplicação não injeta JavaScript, pixel ou iframe de terceiros e não registra cliques nesta versão.
- Verifique as regras do programa de afiliados, direitos sobre marcas e imagens, LGPD e exigências de transparência.
- O Google AdSense não foi integrado. Ele exige cadastro, análise do site e aprovação; não há garantia de aceitação. Um site de downloads de mídia pode enfrentar restrições de política. Avalie elegibilidade antes de integrar scripts.
- A autenticação Basic do piloto continua ativa. Para monetização real, o site precisará de páginas públicas adequadas, termos, privacidade, política de cookies se aplicável e revisão de direitos de conteúdo.

## Testes

1. Sem variáveis, a seção não aparece.
2. Com TITLE e URL HTTPS válidos, a seção aparece com a marcação de publicidade.
3. URLs HTTP e sem título não aparecem.
4. Links abrem em outra aba e não alteram o fluxo de downloads.
