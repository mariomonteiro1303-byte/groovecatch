/* GrooveCatch Web v1.6.0: busca universal, conexão/desempenho e base da central multimídia. */
let authorizedCookieBrowser = null;
const $ = (selector) => document.querySelector(selector);

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(data.error || `Erro HTTP ${response.status}`); Object.assign(error, data); throw error; }
  return data;
}
function setStatus(message, error = false) {
  const el = $("#smart-status"); el.textContent = message; el.style.color = error ? "var(--danger)" : "";
}
function formatDuration(seconds) {
  if (!Number.isFinite(Number(seconds))) return "";
  const value = Number(seconds); return `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, "0")}`;
}
function emptyState(title, detail) {
  const el = document.createElement("div"); el.className = "empty-state";
  const strong = document.createElement("strong"); strong.textContent = title;
  const small = document.createElement("small"); small.textContent = detail;
  el.append(strong, small); return el;
}
function setFormats(formats) {
  /* A mídia identificada define quais saídas fazem sentido para o usuário. */
  const select = $("#format-select"); select.replaceChildren(); select.disabled = false;
  (formats || []).forEach(item => {
    const option = document.createElement("option"); option.value = item.value; option.textContent = item.label; select.append(option);
  });
  if (!select.options.length) {
    [["mp3", "MP3 · Áudio"], ["mp4", "MP4 · Vídeo"]].forEach(([value, label]) => {
      const option = document.createElement("option"); option.value = value; option.textContent = label; select.append(option);
    });
  }
}
function makeTrackRow(titleText, subtitleText, actionText, action, thumbnail = "") {
  const row = document.createElement("div"); row.className = "track";
  if (thumbnail) { const img = document.createElement("img"); img.className = "thumb"; img.src = thumbnail; img.alt = ""; row.append(img); }
  const main = document.createElement("div"); main.className = "track-main";
  const title = document.createElement("div"); title.className = "track-title"; title.textContent = titleText || "Mídia sem título";
  const subtitle = document.createElement("div"); subtitle.className = "track-sub"; subtitle.textContent = subtitleText || "";
  main.append(title, subtitle);
  const button = document.createElement("button"); button.textContent = actionText; button.addEventListener("click", action);
  row.append(main, button); return row;
}

async function togglePreview(container, url) {
  /* A prévia é gerada sob demanda para evitar processamento desnecessário. */
  const existing = container.querySelector("audio");
  if (existing) { existing.paused ? existing.play() : existing.pause(); return; }
  const button = container.querySelector(".preview-button");
  const oldText = button.textContent; button.disabled = true; button.textContent = "Preparando prévia...";
  try {
    const data = await api("/api/preview", {method:"POST", body:JSON.stringify({url, cookie_browser: authorizedCookieBrowser})});
    const audio = document.createElement("audio"); audio.controls = true; audio.preload = "metadata"; audio.src = data.preview_url;
    container.append(audio); button.textContent = "Reproduzir / pausar";
    await audio.play().catch(() => {});
  } catch (error) {
    button.textContent = oldText;
    if (error.code === "youtube_auth_required") setStatus("O YouTube solicitou autenticação também para a prévia.", true);
    else setStatus(`Prévia indisponível: ${error.message}`, true);
  } finally { button.disabled = false; }
}

function spotifyPreview(main, track, button) {
  const existing=main.querySelector(".spotify-preview-frame");
  if(existing){ existing.remove(); button.textContent="▶ Ouvir prévia"; return; }
  if(track.spotify_embed_url){
    const frame=document.createElement("iframe"); frame.className="spotify-preview-frame";
    frame.src=track.spotify_embed_url; frame.width="100%"; frame.height="152"; frame.frameBorder="0";
    frame.allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"; frame.loading="lazy";
    main.append(frame); button.textContent="■ Fechar prévia";
  }
}

async function resolveSpotifyCandidate(track) {
  const data=await api("/api/spotify/match", {method:"POST", body:JSON.stringify({track, cookie_browser:authorizedCookieBrowser})});
  return data.candidates?.[0] || null;
}

async function startSpotifyTrack(track, button=null) {
  const original=button?.textContent;
  if(button){button.disabled=true;button.textContent="Procurando...";}
  try{
    const candidate=await resolveSpotifyCandidate(track);
    if(!candidate) throw new Error("Nenhuma correspondência confiável encontrada para esta faixa.");
    const display=`${(track.artists||[]).join(" - ")} - ${track.title}`.replace(/^ - /,"");
    await startDownload(display,candidate.url,{spotify_id:track.spotify_id,spotify_title:track.title,artists:track.artists||[]});
  }catch(error){setStatus(error.message,true);}
  finally{if(button){button.disabled=false;button.textContent=original;}}
}

function makeSpotifyMatch(track, candidate, selectable = false) {
  const row = document.createElement("div"); row.className = "track spotify-match";
  if (selectable) { const check=document.createElement("input"); check.type="checkbox"; check.className="spotify-select"; check.checked=true; check._track=track; row.append(check); }
  if (candidate.thumbnail || track.thumbnail) { const img=document.createElement("img"); img.className="thumb"; img.src=candidate.thumbnail || track.thumbnail; img.alt=""; row.append(img); }
  const main=document.createElement("div"); main.className="track-main";
  const title=document.createElement("div"); title.className="track-title"; title.textContent=`${(track.artists||[]).join(", ")} - ${track.title}`.replace(/^ - /, "");
  const subtitle=document.createElement("div"); subtitle.className="track-sub"; subtitle.textContent=`Spotify → YouTube · ${candidate.channel || "YouTube"}${candidate.duration ? " · "+formatDuration(candidate.duration) : ""} · correspondência selecionada`;
  const controls=document.createElement("div"); controls.className="match-controls";
  const preview=document.createElement("button"); preview.type="button"; preview.className="preview-button"; preview.textContent="▶ Ouvir prévia"; preview.addEventListener("click",()=>spotifyPreview(main,track,preview));
  const download=document.createElement("button"); download.type="button"; download.textContent="Baixar →"; download.addEventListener("click",()=>startDownload(`${(track.artists||[]).join(" - ")} - ${track.title}`.replace(/^ - /,""), candidate.url, {spotify_id:track.spotify_id, spotify_title:track.title, artists:track.artists||[]}));
  controls.append(preview,download); main.append(title,subtitle,controls); row.append(main); return row;
}

function makeSpotifyCollectionRow(track) {
  /* Coleções são exibidas sem pesquisar no YouTube. O matching só ocorre ao baixar. */
  const row=document.createElement("div"); row.className="track spotify-match";
  const check=document.createElement("input"); check.type="checkbox"; check.className="spotify-select"; check.checked=true; check._track=track; row.append(check);
  if(track.thumbnail){const img=document.createElement("img");img.className="thumb";img.src=track.thumbnail;img.alt="";row.append(img);}
  const main=document.createElement("div");main.className="track-main";
  const title=document.createElement("div");title.className="track-title";title.textContent=`${(track.artists||[]).join(", ")} - ${track.title}`.replace(/^ - /,"");
  const subtitle=document.createElement("div");subtitle.className="track-sub";subtitle.textContent=`Spotify${track.duration_ms ? " · "+formatDuration(track.duration_ms/1000) : ""} · correspondência será buscada ao baixar`;
  const controls=document.createElement("div");controls.className="match-controls";
  const preview=document.createElement("button");preview.type="button";preview.className="preview-button";preview.textContent="▶ Ouvir prévia";preview.addEventListener("click",()=>spotifyPreview(main,track,preview));
  const download=document.createElement("button");download.type="button";download.textContent="Baixar →";download.addEventListener("click",()=>startSpotifyTrack(track,download));
  controls.append(preview,download);main.append(title,subtitle,controls);row.append(main);return row;
}

async function startCollectionDownload(collectionTitle, tracks) {
  try{
    const response=await api("/api/collections/downloads",{method:"POST",body:JSON.stringify({collection_title:collectionTitle,tracks,format:$("#format-select").value,cookie_browser:authorizedCookieBrowser})});
    addJob(response.job); setStatus(`${tracks.length} faixa(s) enviadas para processamento. O resultado será um único ZIP.`);
  }catch(error){setStatus(error.message,true);}
}

function authRequiredBox(onAuthorized, technicalDetail = "") {
  /* A sessão do navegador só é usada após clique explícito do usuário. */
  const box = document.createElement("div"); box.className = "empty-state";
  const title = document.createElement("strong"); title.textContent = "O YouTube solicitou verificação";
  const text = document.createElement("small"); text.textContent = "Escolha um navegador no qual você já esteja conectado ao YouTube. O GrooveCatch não solicita sua senha.";
  const actions = document.createElement("div"); actions.className = "job-actions";
  [["chrome","Chrome"],["edge","Edge"],["firefox","Firefox"],["brave","Brave"]].forEach(([value,label]) => {
    const button = document.createElement("button"); button.textContent = `Usar sessão do ${label}`;
    button.addEventListener("click", () => { authorizedCookieBrowser = value; onAuthorized(value); }); actions.append(button);
  });
  if (technicalDetail) {
    const details = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = "Ver detalhes técnicos";
    const pre = document.createElement("pre"); pre.textContent = technicalDetail; details.append(summary, pre); box.append(title, text, actions, details);
  } else box.append(title, text, actions);
  return box;
}

$("#smart-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#smart-input").value.trim(), button = $("#resolve-button"), results = $("#results");
  if (!input) return;
  button.disabled = true; results.replaceChildren(emptyState("Identificando...", "Consultando a fonte e os formatos disponíveis."));
  const formatSelect = $("#format-select"); formatSelect.replaceChildren(); formatSelect.disabled = true;
  const automatic = document.createElement("option"); automatic.value = "auto"; automatic.textContent = "Automático · identificando..."; formatSelect.append(automatic);
  setStatus("Identificando conteúdo...");
  try {
    const data = await api("/api/resolve", { method: "POST", body: JSON.stringify({ input, cookie_browser: authorizedCookieBrowser }) });
    results.replaceChildren();
    if (data.kind === "spotify") {
      setFormats([{value:"mp3",label:"MP3 · Áudio"},{value:"m4a",label:"M4A · Áudio"},{value:"wav",label:"WAV · Áudio sem compressão"}]);
      const isCollection = data.item_type === "playlist" || data.item_type === "album" || data.count > 1;
      setStatus(`${data.count} faixa(s) Spotify identificada(s)${isCollection ? " · correspondências serão resolvidas somente no download" : ""}.`);
      if (isCollection) {
        const batch=document.createElement("div"); batch.className="batch-controls";
        const label=document.createElement("strong"); label.textContent=`${data.collection_title || "Coleção Spotify"} · ${data.count} faixa(s)`;
        const counter=document.createElement("span"); counter.className="selection-counter";
        const updateCounter=()=>{counter.textContent=`${results.querySelectorAll(".spotify-select:checked").length} selecionada(s)`;};
        const selectAll=document.createElement("button"); selectAll.type="button"; selectAll.textContent="Selecionar todas"; selectAll.addEventListener("click",()=>{results.querySelectorAll(".spotify-select").forEach(c=>c.checked=true);updateCounter();});
        const clearAll=document.createElement("button"); clearAll.type="button"; clearAll.textContent="Limpar seleção"; clearAll.addEventListener("click",()=>{results.querySelectorAll(".spotify-select").forEach(c=>c.checked=false);updateCounter();});
        const downloadAll=document.createElement("button"); downloadAll.type="button"; downloadAll.textContent="Baixar selecionadas em ZIP →"; downloadAll.addEventListener("click",()=>{const selected=[...results.querySelectorAll(".spotify-select:checked")].map(c=>c._track);if(!selected.length){setStatus("Selecione pelo menos uma faixa.",true);return;}startCollectionDownload(data.collection_title || "Coleção Spotify",selected);});
        batch.append(label,counter,selectAll,clearAll,downloadAll); results.append(batch);
        data.tracks.forEach(track=>results.append(makeSpotifyCollectionRow(track)));
        results.addEventListener("change",e=>{if(e.target.classList?.contains("spotify-select"))updateCounter();},{once:false}); updateCounter();
      } else {
        data.tracks.forEach(track => {
          if (track.candidates?.length) results.append(makeSpotifyMatch(track, track.candidates[0], false));
          else if (!(track.artists || []).length) results.append(emptyState("Artista não identificado com segurança", "O GrooveCatch não exibirá candidatos de outros artistas."));
          else results.append(emptyState("Nenhuma correspondência confiável encontrada", `Não encontrei no YouTube uma opção segura para ${(track.artists || []).join(", ")} - ${track.title}.`));
        });
      }
    } else if (data.kind === "youtube_playlist") {
      setFormats([{value:"mp3",label:"MP3 · Áudio"},{value:"m4a",label:"M4A · Áudio"},
                  {value:"wav",label:"WAV · Áudio"},{value:"mp4",label:"MP4 · Vídeo"},
                  {value:"webm",label:"WebM · Vídeo"}]);
      setStatus(`${data.count} vídeo(s) identificados na playlist. Selecione os desejados.`);
      const controls=document.createElement("div");controls.className="batch-controls";
      const title=document.createElement("strong");title.textContent=`${data.collection_title} · ${data.count} vídeos`;
      const counter=document.createElement("span");counter.className="selection-counter";
      const selected=()=>[...results.querySelectorAll(".youtube-playlist-select:checked")].map(el=>el._track);
      const update=()=>{counter.textContent=`${selected().length} selecionado(s)`;};
      const all=document.createElement("button");all.type="button";all.textContent="Selecionar todos";
      all.addEventListener("click",()=>{results.querySelectorAll(".youtube-playlist-select").forEach(el=>el.checked=true);update();});
      const none=document.createElement("button");none.type="button";none.textContent="Limpar seleção";
      none.addEventListener("click",()=>{results.querySelectorAll(".youtube-playlist-select").forEach(el=>el.checked=false);update();});
      const single=document.createElement("button");single.type="button";single.textContent="Baixar só o vídeo do link";
      single.addEventListener("click",async()=>{
        try {
          const original=new URL(input);const vid=original.searchParams.get("v") || (original.hostname==="youtu.be"?original.pathname.slice(1):null);
          if(!vid){setStatus("O link não contém um vídeo individual.",true);return;}
          const url=`https://www.youtube.com/watch?v=${encodeURIComponent(vid)}`;
          const info=await api("/api/resolve",{method:"POST",body:JSON.stringify({input:url,cookie_browser:authorizedCookieBrowser})});
          if(info.kind!=="media_url")throw new Error("Não foi possível identificar o vídeo individual.");
          startDownload(info.media.title,info.media.url,{platform:"YouTube"});
        }catch(err){setStatus(err.message,true);}
      });
      const download=document.createElement("button");download.type="button";download.textContent="Baixar selecionados em ZIP →";
      download.addEventListener("click",async()=>{
        const tracks=selected();if(!tracks.length){setStatus("Selecione pelo menos um vídeo.",true);return;}
        download.disabled=true;
        try{
          const job=await api("/api/youtube/playlist/downloads",{method:"POST",body:JSON.stringify({
            collection_title:data.collection_title,playlist_id:new URL(data.playlist_url).searchParams.get("list"),
            tracks,format:$("#format-select").value,cookie_browser:authorizedCookieBrowser})});
          addJob(job.job);setStatus(`${tracks.length} vídeo(s) enviados para a fila. ZIP será criado ao final.`);
        }catch(err){setStatus(err.message,true);}finally{download.disabled=false;}
      });
      controls.append(title,counter,all,none,single,download);results.append(controls);
      data.tracks.forEach(track=>{
        const row=makeTrackRow(`${track.position}. ${track.title}`,
          `${track.channel||"YouTube"}${track.duration?" · "+formatDuration(track.duration):""}`,
          "Baixar →",()=>startDownload(track.title,track.url,{platform:"YouTube"}),track.thumbnail);
        const checkbox=document.createElement("input");checkbox.type="checkbox";
        checkbox.className="youtube-playlist-select";checkbox.checked=true;checkbox._track=track;
        checkbox.addEventListener("change",update);row.prepend(checkbox);results.append(row);
      });update();
    } else if (data.kind === "media_url") {
      const media = data.media; setFormats(media.formats);
      setStatus(`${media.platform} identificado. Escolha o formato e baixe.`);
      const details = [media.platform, media.channel, media.duration ? formatDuration(media.duration) : "", media.has_video ? "vídeo" : "áudio"].filter(Boolean).join(" · ");
      results.append(makeTrackRow(media.title, details, "Baixar →", () => startDownload(media.title, media.url, { platform: media.platform }), media.thumbnail));
    } else {
      setFormats([{value:"mp3",label:"MP3 · Áudio"},{value:"m4a",label:"M4A · Áudio"},{value:"wav",label:"WAV · Áudio sem compressão"},{value:"mp4",label:"MP4 · Vídeo"},{value:"webm",label:"WebM · Vídeo"}]);
      setStatus(`${data.candidates.length} resultado(s) encontrado(s) no YouTube.`);
      data.candidates.forEach(candidate => {
        const row = makeTrackRow(candidate.title,
          `${candidate.channel || "YouTube"}${candidate.duration ? " · " + formatDuration(candidate.duration) : ""}`,
          "Baixar →", () => startDownload(candidate.title, candidate.url), candidate.thumbnail || "");
        const main = row.querySelector(".track-main");
        const controls = document.createElement("div"); controls.className = "match-controls";
        const preview = document.createElement("button"); preview.type="button"; preview.className="preview-button"; preview.textContent="▶ Ouvir prévia";
        preview.addEventListener("click", () => togglePreview(main, candidate.url));
        controls.append(preview); main.append(controls); results.append(row);
      });
    }
    if (!results.children.length) results.append(emptyState("Nenhum resultado", "Tente outro endereço ou termo de busca."));
  } catch (error) {
    if (error.code === "youtube_auth_required") {
      results.replaceChildren(authRequiredBox(() => document.querySelector("#smart-form").requestSubmit(), error.technical_detail));
      setStatus("O YouTube solicitou uma sessão autenticada.", true);
    } else {
      results.replaceChildren(emptyState("Não foi possível identificar", error.message)); setStatus(error.message, true);
    }
  } finally { button.disabled = false; }
});

async function startDownload(title, url, metadata = {}) {
  try {
    const response = await api("/api/downloads", { method: "POST", body: JSON.stringify({ title, url, format: $("#format-select").value, metadata, cookie_browser: authorizedCookieBrowser }) });
    addJob(response.job);
  } catch (error) { setStatus(error.message, true); }
}
function addJob(job) {
  const list = $("#jobs"); if (list.querySelector(".empty-state")) list.replaceChildren();
  const card = document.createElement("div"); card.className = "job";
  const top = document.createElement("div"); top.className = "job-top";
  const name = document.createElement("strong"); name.textContent = job.title || "Download";
  const status = document.createElement("span"); status.className = "pill"; status.textContent = job.status;
  top.append(name, status);
  const progress = document.createElement("div"); progress.className = "progress"; const fill = document.createElement("span"); progress.append(fill);
  const message = document.createElement("div"); message.className = "small"; message.textContent = job.message || "Na fila";
  const actions = document.createElement("div"); actions.className = "job-actions";
  card.append(top, progress, message, actions); list.prepend(card); pollJob(job.id, status, fill, message, actions);
}
async function pollJob(id, statusEl, fill, messageEl, actions) {
  try {
    const data = await api(`/api/jobs/${id}`); statusEl.textContent = data.status; fill.style.width = `${data.progress || 0}%`;
    let live = data.error || data.message || "";
    if (data.status === "running" && Number(data.speed_bps) > 0) {
      const mbps = Number(data.speed_bps) / 1024 / 1024;
      live += ` · ${mbps.toFixed(2)} MB/s`;
      if (Number.isFinite(Number(data.eta_seconds))) live += ` · ~${Math.max(0, Math.round(Number(data.eta_seconds)))}s restantes`;
    }
    messageEl.textContent = live;
    if (["queued", "running"].includes(data.status)) {
      if (!actions.querySelector("button")) { const cancel = document.createElement("button"); cancel.textContent = "Cancelar"; cancel.addEventListener("click", async () => { try { await api(`/api/jobs/${id}/cancel`, {method:"POST", body:"{}"}); } catch (e) { messageEl.textContent = e.message; } }); actions.append(cancel); }
      setTimeout(() => pollJob(id, statusEl, fill, messageEl, actions), 1300); return;
    }
    statusEl.className = `pill ${data.status === "completed" ? "ok" : "bad"}`;
    if (data.status === "completed" && data.download_url) {
      // O arquivo já foi validado no servidor. Tentamos iniciar o download automaticamente.
      // O próprio navegador decide entre a pasta padrão e "Salvar como", conforme a configuração do usuário.
      const link = document.createElement("a");
      link.className = "download-link"; link.href = data.download_url; link.download = data.filename || "";
      link.textContent = `Salvar novamente (${data.filename || "download"})`;
      actions.replaceChildren(link);
      messageEl.textContent = "Concluído. Salvamento enviado ao navegador.";
      if (!actions.dataset.autoDownloadStarted) {
        actions.dataset.autoDownloadStarted = "1";
        const automaticLink = document.createElement("a");
        automaticLink.href = data.download_url; automaticLink.download = data.filename || "";
        automaticLink.style.display = "none"; document.body.append(automaticLink);
        automaticLink.click(); automaticLink.remove();
      }
      loadHistory();
    } else if (data.error_code === "youtube_auth_required") {
      actions.replaceChildren(authRequiredBox(async (browser) => {
        try { const r = await api(`/api/jobs/${id}/retry`, {method:"POST", body:JSON.stringify({cookie_browser: browser})}); actions.replaceChildren(); addJob(r.job); }
        catch(e) { messageEl.textContent = e.message; }
      }, data.technical_detail));
      messageEl.textContent = "O YouTube exige uma sessão autenticada para este conteúdo.";
    } else {
      const retry = document.createElement("button"); retry.className = "retry"; retry.textContent = "Tentar novamente";
      retry.addEventListener("click", async () => { try { const r = await api(`/api/jobs/${id}/retry`, {method:"POST", body:"{}"}); actions.replaceChildren(); addJob(r.job); } catch(e) { messageEl.textContent=e.message; } }); actions.replaceChildren(retry);
    }
  } catch (error) { messageEl.textContent = error.message; }
}
async function loadDiagnostics() {
  const target = $("#diagnostic-list"); target.replaceChildren();
  try { const data = await api("/api/diagnostics"); data.checks.forEach(check => { const row=document.createElement("div"); row.className="diagnostic"; const name=document.createElement("strong"); name.textContent=check.name; const detail=document.createElement("span"); detail.className=`pill ${check.ok?"ok":"bad"}`; detail.textContent=check.detail; row.append(name,detail); target.append(row); }); }
  catch(error){ target.textContent=error.message; }
}
async function loadConnection() {
  const target = $("#connection-list"); target.replaceChildren();
  const add = (name, value, ok=true) => { const row=document.createElement("div"); row.className="diagnostic"; const strong=document.createElement("strong"); strong.textContent=name; const span=document.createElement("span"); span.className=`pill ${ok?"ok":"bad"}`; span.textContent=value; row.append(strong,span); target.append(row); };
  try {
    const data=await api("/api/connection");
    add("Internet", data.online ? "Conectado" : "Sem conexão", data.online);
    add("Latência", data.latency_ms == null ? "Indisponível" : `${data.latency_ms} ms`, data.online);
    add("Qualidade", data.quality || "Indisponível", data.online);
    add("Velocidade", "medida durante o download", true);
  } catch(error) { add("Internet", error.message, false); }
}
async function loadHistory() {
  const target = $("#history-list"); target.replaceChildren();
  try { const data=await api("/api/history"); if(!data.items.length){target.append(emptyState("Histórico vazio","Downloads concluídos aparecerão aqui."));return;} data.items.forEach(item=>{const row=document.createElement("div");row.className="history-item";const name=document.createElement("strong");name.textContent=`${item.filename||item.title}${item.file_exists?"":" · arquivo ausente"}`;const date=document.createElement("span");date.className="small";date.textContent=item.created_at?new Date(item.created_at).toLocaleString():"";row.append(name,date);target.append(row);}); }
  catch(error){target.textContent=error.message;}
}
$("#refresh-diagnostics").addEventListener("click", loadDiagnostics); $("#refresh-connection").addEventListener("click", loadConnection); $("#refresh-history").addEventListener("click", loadHistory);
loadConnection(); loadDiagnostics(); loadHistory();

// v1.6.2 - Rádios. A geolocalização é pedida somente após clique explícito.
const radioResults = $("#radio-results"), radioStatus = $("#radio-status");
const RADIO_FAVORITES_KEY="groovecatch_radio_favorites_v1";
function radioFavorites(){try{return JSON.parse(localStorage.getItem(RADIO_FAVORITES_KEY)||"[]")}catch{return []}}
function saveRadioFavorites(items){localStorage.setItem(RADIO_FAVORITES_KEY,JSON.stringify(items));}
function isRadioFavorite(st){return radioFavorites().some(x=>x.id===st.id || x.stream_url===st.stream_url)}
function toggleRadioFavorite(st){let items=radioFavorites();const i=items.findIndex(x=>x.id===st.id || x.stream_url===st.stream_url);if(i>=0)items.splice(i,1);else items.push(st);saveRadioFavorites(items);return i<0;}
function radioFallback(img,st){img.hidden=true;const fb=document.createElement("div");fb.className="radio-logo-fallback";fb.textContent=(st.name||"R").trim().slice(0,1).toUpperCase();img.replaceWith(fb);}
function renderRadios(items, provider) {
  radioResults.replaceChildren(); radioStatus.textContent = `${items.length} emissora(s) · ${provider || "catálogo"}`;
  if (!items.length) { radioResults.append(emptyState("Nenhuma rádio encontrada", "Tente emissora, cidade, estado, país ou gênero.")); return; }
  items.forEach(st => {
    const card=document.createElement("div"); card.className="radio-card";
    let visual;
    if(st.favicon){const img=document.createElement("img");img.alt="";img.loading="lazy";img.src=st.favicon;img.addEventListener("error",()=>radioFallback(img,st),{once:true});visual=img;}
    else{const fb=document.createElement("div");fb.className="radio-logo-fallback";fb.textContent=(st.name||"R").trim().slice(0,1).toUpperCase();visual=fb;}
    const info=document.createElement("div"); info.className="radio-info";
    const name=document.createElement("strong"); name.textContent=st.name;
    const place=document.createElement("small"); place.textContent=[st.city,st.state,st.country].filter(Boolean).join(" · ") + (st.distance_km!=null?` · ${st.distance_km} km`:"");
    const source=document.createElement("small"); source.textContent=[st.tags,st.provider||provider||""].filter(Boolean).join(" · ");
    info.append(name,place,source);
    const fav=document.createElement("button");fav.className="radio-fav";fav.textContent=isRadioFavorite(st)?"★":"☆";fav.title="Favoritar";fav.addEventListener("click",()=>{const on=toggleRadioFavorite(st);fav.textContent=on?"★":"☆";});
    const play=document.createElement("button"); play.textContent="▶"; play.title="Ouvir"; play.addEventListener("click",()=>playRadio(st));
    card.append(visual,info,fav,play); radioResults.append(card);
  });
}
async function refreshNowPlaying(st){const el=$("#radio-now-track");el.textContent="Consultando música atual...";try{const d=await api("/api/radios/now-playing",{method:"POST",body:JSON.stringify({stream_url:st.stream_url})});if(d.available){el.textContent=`♫ ${d.title}`;$("#radio-player").dataset.nowPlaying=d.title;}else{el.textContent="Música atual não informada pela emissora.";$("#radio-player").dataset.nowPlaying="";}}catch{el.textContent="Música atual não informada pela emissora.";}}
function playRadio(st) {
  const player=$("#radio-player"), audio=$("#radio-audio");
  $("#radio-now-name").textContent=st.name; $("#radio-now-place").textContent=[st.city,st.state,st.country].filter(Boolean).join(" · ");
  audio.src=st.stream_url; player.hidden=false; audio.play().catch(()=>{radioStatus.textContent="A emissora foi carregada. Clique em Play no player se o navegador bloqueou a reprodução automática.";});
  player.dataset.stationName=st.name;player.dataset.streamUrl=st.stream_url;refreshNowPlaying(st);
}
async function searchRadios(){
  const q=$("#radio-query").value.trim(), field=$("#radio-field").value;
  if(q.length<2){radioStatus.textContent="Digite pelo menos dois caracteres.";return;}
  radioStatus.textContent="Consultando catálogo e conferindo correspondências...";
  radioResults.replaceChildren();
  try{
    const d=await api(`/api/radios/search?q=${encodeURIComponent(q)}&field=${encodeURIComponent(field)}`);
    renderRadios(d.items,d.provider);
    if(!d.items.length){radioStatus.textContent=`Nenhuma emissora correspondente a "${q}". Tente outro filtro ou localidade.`;}
  }catch(e){radioStatus.textContent=e.message;}
}
$("#radio-search-button").addEventListener("click",searchRadios); $("#radio-query").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();searchRadios();}});
$("#favorite-radios").addEventListener("click",()=>renderRadios(radioFavorites(),"Favoritas"));
$("#nearby-radios").addEventListener("click",()=>{
  if(!navigator.geolocation){radioStatus.textContent="Este navegador não oferece geolocalização.";return;}
  radioStatus.textContent="Aguardando sua autorização de localização...";
  navigator.geolocation.getCurrentPosition(async pos=>{try{radioStatus.textContent="Procurando rádios próximas...";const d=await api(`/api/radios/nearby?lat=${encodeURIComponent(pos.coords.latitude)}&lon=${encodeURIComponent(pos.coords.longitude)}`);renderRadios(d.items,d.provider)}catch(e){radioStatus.textContent=e.message;}},err=>{radioStatus.textContent=err.code===1?"Localização não autorizada. Você ainda pode pesquisar rádios manualmente.":"Não foi possível obter sua localização.";},{enableHighAccuracy:false,timeout:10000,maximumAge:600000});
});
$("#radio-find-song").addEventListener("click",()=>{
  const player=$("#radio-player"), title=player.dataset.nowPlaying||"", station=player.dataset.stationName||"";
  if(title){$("#smart-input").value=title;$("#smart-input").focus();setStatus(`Música de ${station} enviada para a Busca Universal. Clique em Identificar.`);}
  else{$("#smart-input").value="";$("#smart-input").focus();setStatus(`A emissora ${station} não informou a música atual. Digite artista e música para pesquisar.`);}
  window.scrollTo({top:0,behavior:"smooth"});
});


// Ferramenta de conversão: envio local e download pelo navegador.
document.querySelector("#audio-convert-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.querySelector("#audio-convert-status");
  const button = document.querySelector("#audio-convert-button");
  const file = document.querySelector("#audio-file").files[0];
  if (!file) return;
  if (file.size > 100 * 1024 * 1024) { status.textContent = "Arquivo acima do limite de 100 MB."; return; }
  const target = document.querySelector("#audio-target").value;
  const data = new FormData(); data.append("file", file); data.append("format", target);
  button.disabled = true; status.textContent = "Convertendo... Aguarde.";
  try {
    const response = await fetch("/api/tools/convert-audio", {method:"POST", body:data});
    if (!response.ok) { const body = await response.json().catch(()=>({})); throw new Error(body.error || `Falha HTTP ${response.status}`); }
    const blob = await response.blob();
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
    const base = file.name.replace(/\.[^.]+$/, ""); link.download = `${base}.${target}`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(()=>URL.revokeObjectURL(link.href), 30000);
    status.textContent = "Conversão concluída. Confira o arquivo salvo pelo navegador.";
  } catch (error) { status.textContent = error.message; }
  finally { button.disabled = false; }
});

// Ferramentas multimídia v1.7.1: controla entradas e salva resultados no navegador.
const mediaOperation = document.querySelector("#media-operation");
const mediaFiles = document.querySelector("#media-files");
const mediaPreview = document.querySelector("#media-tools-preview");
let mediaPreviewUrl = null;
function refreshMediaTool() {
  const op = mediaOperation.value;
  document.querySelector("#trim-options").hidden = op !== "trim";
  mediaFiles.multiple = op === "batch";
  mediaFiles.accept = op === "extract" ? ".mp4,.mkv,.webm,.mov,.avi" : ".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus";
  mediaFiles.value = "";
  mediaPreview.removeAttribute("src");
  mediaPreview.load();
}
mediaOperation.addEventListener("change", refreshMediaTool);
mediaFiles.addEventListener("change", () => {
  if (mediaPreviewUrl) URL.revokeObjectURL(mediaPreviewUrl);
  const file = mediaFiles.files[0];
  if (file) { mediaPreviewUrl = URL.createObjectURL(file); mediaPreview.src = mediaPreviewUrl; }
});
refreshMediaTool();
document.querySelector("#media-tools-form").addEventListener("submit", async event => {
  event.preventDefault();
  const status = document.querySelector("#media-tools-status");
  const button = document.querySelector("#media-tools-button");
  const files = [...mediaFiles.files];
  if (!files.length) return;
  if (files.length > (window.GROOVECATCH_CLOUD ? 3 : 20) || files.reduce((n,f)=>n+f.size,0)>100*1024*1024) {
    status.textContent="Limite: quantidade de arquivos permitida e 100 MB no total."; return;
  }
  const data = new FormData();
  files.forEach(f => data.append("files", f));
  data.append("operation", mediaOperation.value);
  data.append("format", document.querySelector("#media-format").value);
  data.append("start", document.querySelector("#trim-start").value);
  data.append("end", document.querySelector("#trim-end").value);
  button.disabled=true; status.textContent="Processando... Aguarde.";
  try {
    const response=await fetch("/api/tools/process",{method:"POST",body:data});
    if (!response.ok) { const body=await response.json().catch(()=>({})); throw new Error(body.error||`Erro HTTP ${response.status}`); }
    const blob=await response.blob();
    const disposition=response.headers.get("content-disposition")||"";
    const found=disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
    const name=found ? decodeURIComponent(found[1].replace(/"$/,"")) : "GrooveCatch_resultado";
    const url=URL.createObjectURL(blob);
    const link=document.createElement("a"); link.href=url; link.download=name;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    status.textContent="Processamento concluído. Confira o arquivo salvo.";
  } catch(error) { status.textContent=error.message; }
  finally { button.disabled=false; }
});

// Ferramentas de vídeo v1.8.0: compressão e corte sem alterar o arquivo original.
const videoOperation = document.querySelector("#video-operation");
const videoInput = document.querySelector("#video-file");
const videoPreview = document.querySelector("#video-preview");
let currentVideoPreview = null;
videoOperation.addEventListener("change", () => {
  const trim = videoOperation.value === "trim";
  document.querySelector("#video-trim-options").hidden = !trim;
  document.querySelector("#video-preset").hidden = trim;
});
videoInput.addEventListener("change", () => {
  if (currentVideoPreview) URL.revokeObjectURL(currentVideoPreview);
  if (videoInput.files[0]) {
    currentVideoPreview = URL.createObjectURL(videoInput.files[0]);
    videoPreview.src = currentVideoPreview;
  }
});
document.querySelector("#video-tools-form").addEventListener("submit", async event => {
  event.preventDefault();
  const file = videoInput.files[0];
  const status = document.querySelector("#video-status");
  const button = document.querySelector("#video-submit");
  if (!file) return;
  if (file.size > (window.GROOVECATCH_CLOUD ? 100 : 500) * 1024 * 1024) {
    status.textContent = "O arquivo ultrapassa o limite desta edição."; return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("operation", videoOperation.value);
  form.append("preset", document.querySelector("#video-preset").value);
  form.append("start", document.querySelector("#video-start").value);
  form.append("end", document.querySelector("#video-end").value);
  button.disabled = true;
  status.textContent = "Processando vídeo... Arquivos grandes podem demorar alguns minutos.";
  try {
    const response = await fetch("/api/tools/video", {method:"POST", body:form});
    if (!response.ok) {
      const body = await response.json().catch(()=>({}));
      throw new Error(body.error || `Erro HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
    const name = match ? decodeURIComponent(match[1].replace(/"$/, "")) : "GrooveCatch_video.mp4";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = name;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    status.textContent = "Vídeo processado. Confira o arquivo salvo.";
  } catch(error) { status.textContent = error.message; }
  finally { button.disabled = false; }
});

// Central Multimídia v1.9.0: captura de quadros, GIFs e metadados de áudio.
const advancedOperation=document.querySelector("#advanced-operation");
const advancedInput=document.querySelector("#advanced-file");
const advancedPreview=document.querySelector("#advanced-preview");
let advancedPreviewUrl=null;
function refreshAdvanced(){
  const op=advancedOperation.value;
  document.querySelector("#advanced-format").hidden=op!=="frame";
  document.querySelector("#advanced-time").hidden=op==="metadata";
  document.querySelector("#advanced-end-label").hidden=op!=="gif";
  document.querySelector("#advanced-metadata").hidden=op!=="metadata";
  advancedInput.accept=op==="metadata"?".mp3,.flac,.m4a,.ogg":".mp4,.mkv,.webm,.mov,.avi";
  advancedInput.value="";
  advancedPreview.removeAttribute("src");advancedPreview.load();
}
advancedOperation.addEventListener("change",refreshAdvanced);
advancedInput.addEventListener("change",()=>{
  if(advancedPreviewUrl) URL.revokeObjectURL(advancedPreviewUrl);
  if(advancedInput.files[0]){
    advancedPreviewUrl=URL.createObjectURL(advancedInput.files[0]);
    advancedPreview.src=advancedPreviewUrl;
  }
});
refreshAdvanced();
document.querySelector("#advanced-tools-form").addEventListener("submit",async e=>{
  e.preventDefault();
  const status=document.querySelector("#advanced-status");
  const button=document.querySelector("#advanced-submit");
  const file=advancedInput.files[0];if(!file)return;
  if(file.size>(window.GROOVECATCH_CLOUD?100:500)*1024*1024){status.textContent="Arquivo excede o limite desta edição.";return;}
  const data=new FormData();data.append("file",file);data.append("operation",advancedOperation.value);
  data.append("format",document.querySelector("#advanced-format").value);
  data.append("start",document.querySelector("#advanced-start").value);
  data.append("end",document.querySelector("#advanced-end").value);
  for(const field of ["title","artist","album","date","genre"])
    data.append(field,document.querySelector(`#advanced-${field}`).value);
  button.disabled=true;status.textContent="Processando...";
  try{
    const response=await fetch("/api/tools/advanced",{method:"POST",body:data});
    if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.error||`Erro HTTP ${response.status}`);}
    const blob=await response.blob();
    const disposition=response.headers.get("content-disposition")||"";
    const match=disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
    const filename=match?decodeURIComponent(match[1].replace(/"$/,"")):"GrooveCatch_resultado";
    const url=URL.createObjectURL(blob);const a=document.createElement("a");
    a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    status.textContent="Arquivo gerado. Confira o download.";
  }catch(error){status.textContent=error.message;}
  finally{button.disabled=false;}
});

// v1.10.0: abas de interface; preserva os formulários e seus listeners existentes.
(function initMediaTabs() {
  const buttons = [...document.querySelectorAll("[data-tool-tab]")];
  const panels = {
    audio: document.querySelector("#tool-panel-audio"),
    video: document.querySelector("#tool-panel-video"),
    image: document.querySelector("#tool-panel-image")
  };
  const advanced = document.querySelector("#advanced-operation");
  function activate(name, updateHash = false) {
    // Metadados reutiliza o formulário de imagens, com operação predefinida.
    const activePanel = name === "metadata" ? "image" : name;
    if (name === "metadata") {
      advanced.value = "metadata";
      advanced.dispatchEvent(new Event("change", {bubbles:true}));
    } else if (name === "image" && advanced.value === "metadata") {
      advanced.value = "frame";
      advanced.dispatchEvent(new Event("change", {bubbles:true}));
    }
    Object.entries(panels).forEach(([key, panel]) => { if (panel) panel.hidden = key !== activePanel; });
    buttons.forEach(button => {
      const selected = button.dataset.toolTab === name;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    if (updateHash) history.replaceState(null, "", "#tools-section");
  }
  buttons.forEach((button, index) => {
    button.addEventListener("click", () => activate(button.dataset.toolTab, true));
    button.addEventListener("keydown", event => {
      if (!["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length-1 :
        (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next].focus();
      activate(buttons[next].dataset.toolTab);
    });
  });
  activate("audio");
})();
