# GrooveCatch Cloud v1.11.0 - piloto Render Free

## Implantação
1. Crie um repositório **privado** no GitHub e envie os arquivos desta pasta para a raiz do repositório. Não envie `.env` nem cookies.
2. No Render, selecione **New > Blueprint** e conecte o repositório. O `render.yaml` define um Web Service Docker no plano `free`.
3. Informe `GROOVECATCH_ACCESS_PASSWORD` com uma senha longa e exclusiva quando solicitado. A chave `GROOVECATCH_SECRET_KEY` será gerada pelo Render.
4. Confirme a criação. Aguarde a construção da imagem (FFmpeg e Python) e acesse a URL `*.onrender.com`.
5. O navegador pedirá usuário e senha. Usuário padrão: `admin`; senha: a definida no Render.
6. Acesse `/health` para conferir a inicialização. Faça um teste com áudio pequeno antes de vídeo.

## Limitações do piloto
- Instância gratuita pode dormir e reiniciar. A fila e arquivos são **temporários**; histórico SQLite também não é persistente.
- Apenas 1 worker web, 1 thread de download pesado, até 2 tarefas de download pendentes/ativas, 1 ferramenta FFmpeg síncrona por vez.
- Upload total até ~100 MB. Vídeos até 100 MB. Lotes áudio até 3 arquivos. Playlists: até 5 itens por download.
- Requisições de conversão ainda são síncronas. O navegador precisa ficar aberto; não há progresso real de FFmpeg ou cancelamento imediato para essas ferramentas.
- Links HTTPS de YouTube, Spotify e SoundCloud; outros provedores estão bloqueados nesta edição para reduzir SSRF. Recursos sujeitos a bloqueios das plataformas.
- Cookies de navegador local são ignorados na nuvem. Não forneça cookies de sessão ao Render.
- Metadados ICY de rádio no servidor desativados por segurança. Reprodução de rádio no navegador depende do stream e de CORS.
- **Não abra o piloto ao público** sem fila persistente, autenticação por usuário, limites por conta/IP, isolamento de arquivos e proteção mais robusta contra abuso e SSRF.
- **Sem garantia de custo zero contínuo**: acompanhe quotas e políticas do Render; não ative serviços pagos sem necessidade.

## Testes sugeridos
1. `/health` retorna `status: ok`.
2. `/` exige senha.
3. Converter MP3 pequeno para WAV.
4. Cortar áudio pequeno.
5. Playlist YouTube com 2 itens.
6. Conferir mensagens para upload acima de 100 MB.
7. Reiniciar o serviço e observar perda esperada dos arquivos temporários.

## Próximas melhorias
Fila durável, expiração de downloads, controle de cota de disco, progresso de FFmpeg e cancelamento de subprocessos. **Não estão implementados nesta versão.**
