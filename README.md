# GrooveCatch Web v1.6.2 - Fechamento da etapa Rádios

## Novidades
- Busca de rádios por nome, cidade, estado, país e gênero/tag.
- Rádios perto de mim continuam usando geolocalização somente após consentimento.
- Favoritos locais no navegador.
- Fallback visual quando a logo/favicon da emissora estiver ausente ou quebrada.
- Tentativa de leitura de `StreamTitle` (ICY metadata) da rádio atual.
- Quando a emissora informa a música, "Buscar música atual" envia o texto para a Busca Universal.
- Quando não há metadados, o GrooveCatch informa isso sem inventar artista ou título.

## Testes sugeridos
1. Pesquisar `Picos`, `Piauí`, `Brasil` e um gênero, por exemplo `forró`.
2. Favoritar uma rádio, atualizar a página e abrir `Favoritas`.
3. Reproduzir uma rádio sem logo para conferir o fallback.
4. Em rádios que publiquem ICY metadata, verificar a música atual e enviá-la à Busca Universal.
5. Validar `Rádios perto de mim` com permissão de localização.


## v1.6.3 - Correção da busca de rádios

- Filtro explícito: Automático, Emissora, Cidade, Estado, País e Gênero.
- Resultados são conferidos contra o campo solicitado. O catálogo não pode substituir silenciosamente uma cidade por rádios sem relação com ela.
- Modo automático prioriza correspondências geográficas, sem descartar correspondências reais de nome ou gênero.
- Quando não há correspondências, mostra estado vazio em vez de emissoras aleatórias.
- Mantidos player, favoritos, geolocalização sob consentimento e metadados ICY.

### Testes sugeridos

Pesquisar `Teresina` com Cidade, `Picos` com Cidade, `Piauí` com Estado, `Brasil` com País, `forró` com Gênero e `Grande FM` com Emissora. Verificar a localização exibida em cada resultado.

Nota: a disponibilidade de emissoras depende do cadastro no Radio Browser. Não encontrar uma emissora não significa que ela não exista.


## v1.11.2: Gerenciador de monetização
Painel em `/admin/ads` para anúncios próprios, afiliados e banners de redes autorizadas, com cadastro, edição, pausa, exclusão, rodízio por posição e contadores simples. Leia `GUIA_MONETIZACAO_MULTICANAL.md`.
