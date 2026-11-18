# GrooveCatch v1.11.4: estabilização do YouTube

## Alterações
- Links `youtu.be`, `/watch`, `/shorts` e `/live` com `list=` priorizam o vídeo explícito. URL `/playlist?list=...` continua sendo playlist.
- Mixes automáticos `RD` e `RDMM` em URL de playlist retornam mensagem específica.
- Falhas YouTube 429, 403 e ausência de resposta do player recebem códigos estáveis e mensagens públicas sem detalhes técnicos.
- Ao detectar HTTP 429, a instância Cloud suspende novas chamadas YouTube por 900 segundos (configurável entre 0 e 3600 via `GROOVECATCH_YOUTUBE_COOLDOWN_SECONDS`). Outras plataformas não são afetadas.
- Configuração Deno/yt-dlp, avisos e diagnóstico das dependências padronizados. Removido selo visual WEB.

## Publicação segura
1. Fazer backup da versão atual do GitHub e confirmar que o branch de atualização passou nos testes.
2. Publicar as alterações no branch principal somente após revisar o PR.
3. No Render, verificar o deploy mais recente e testar uma URL individual do YouTube somente uma vez.
4. Testar uma playlist convencional e as ferramentas locais (conversão, rádios).
5. Se o YouTube responder 429/403 novamente, a aplicação deverá informar a indisponibilidade sem insistir automaticamente. **Esta versão não remove restrições externas do YouTube**.

## Limitações
- Pausa compartilhada apenas entre threads de um mesmo processo. Em múltiplas instâncias exige armazenamento compartilhado.
- Estado da pausa é reiniciado ao reiniciar o servidor (Render Free). Não representa bloqueio permanente.
- Erros 403/429 são recusas do serviço externo. Instalar Deno ou pagar por Render não garante acesso.
- Vídeos e playlists exigem conteúdo acessível e uso autorizado, respeitando os termos das plataformas.
