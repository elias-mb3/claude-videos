"""Pipeline de edição de vídeo — roda DENTRO do container (bin/editor), sem rede.

Uso:  bin/editor python3 scripts/video.py <projeto> <etapa> [opções]

Etapas (em ordem):
  info          resumo do vídeo bruto (duração, resolução, rotação)
  transcrever   Whisper large-v3 -> build/transcricao.json + transcricao.md (compacto, p/ revisão)
  trecho S E    re-transcreve só um trecho (beam maior), p/ conferir palavras duvidosas
  cortes        propõe cortes de pausas -> build/cortes.md (+ remove os de projeto.json)
  amostra [t..] folha de contato 270px (barata em tokens) -> build/amostra.jpg
  cor           compara presets de cor -> build/cor.jpg
  graficos      gera e renderiza os gráficos (HyperFrames, MOV com alpha)
  plano         calcula linha do tempo, legendas (.ass) e trilha -> build/plano.json
  segmentos     renderiza cada trecho mantido com cor + zoom
  final         concatena, aplica gráficos + legendas, mixa áudio -> saida/
  tudo          plano + graficos + segmentos + final
Opção global: --preview (540p rápido, para revisar antes do render final).
"""
import glob, html, json, os, shutil, subprocess, sys, wave
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREVIEW = "--preview" in sys.argv
ARGS = [a for a in sys.argv[1:] if a != "--preview"]

GRADES = {
    "neutro": "null",
    "natural": "curves=master='0/0 0.13/0.08 0.5/0.54 0.9/0.94 1/1',eq=saturation=1.22:gamma=1.06,"
               "colorbalance=rm=0.02:bm=-0.02:rh=0.01:bh=-0.02",
    "quente": "curves=master='0/0 0.13/0.07 0.5/0.55 0.9/0.95 1/1',eq=saturation=1.27:gamma=1.07,"
              "colorbalance=rs=0.02:bs=-0.02:rm=0.035:bm=-0.035:rh=0.02:bh=-0.02,vignette=PI/6",
    "vibrante": "curves=master='0/0 0.12/0.06 0.5/0.53 0.9/0.95 1/1',eq=saturation=1.38:contrast=1.04,"
                "colorbalance=rm=0.01:bm=-0.01",
}


# ------------------------------------------------------------------ utilidades
def run(cmd, quiet=False):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL if quiet else None,
                       stderr=subprocess.DEVNULL if quiet else None)
    if r.returncode:
        sys.exit(f"ERRO ({r.returncode}): {' '.join(map(str, cmd[:8]))} ...")


def probe(path, entries):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries,
                          "-of", "json", path], capture_output=True, text=True).stdout
    return json.loads(out)


def ts(x):
    return f"{int(x // 60):02d}:{x % 60:05.2f}"


class Proj:
    def __init__(self, nome):
        self.dir = os.path.join(ROOT, "projetos", nome)
        if not os.path.isdir(self.dir):
            sys.exit(f"projeto inexistente: projetos/{nome}")
        self.cfg = json.load(open(self.p("projeto.json")))
        self.est = json.load(open(os.path.join(ROOT, "estilos", self.cfg["estilo"] + ".json")))
        for k, v in self.cfg.get("ajustes_estilo", {}).items():  # sobrescritas por projeto
            if isinstance(v, dict):
                self.est.setdefault(k, {}).update(v)
            else:
                self.est[k] = v
        self.build = self.p("build"); os.makedirs(self.build, exist_ok=True)
        os.makedirs(self.p("saida"), exist_ok=True)
        self.src = self.p(self.cfg["fonte"])
        self.W, self.H = self.est["resolucao"]
        if PREVIEW:
            self.W, self.H = self.W // 2, self.H // 2
        self.suf = "_p" if PREVIEW else ""

    def p(self, *a):
        return os.path.join(self.dir, *a)

    def b(self, *a):
        return os.path.join(self.build, *a)

    @property
    def fps(self):
        r = probe(self.src, "stream=r_frame_rate")["streams"][0]["r_frame_rate"]
        return Fraction(r)

    @property
    def dur(self):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              self.src], capture_output=True, text=True).stdout
        return float(out)


# ------------------------------------------------------------------ info / transcrição
def info(P):
    d = probe(P.src, "stream=width,height,avg_frame_rate,codec_name:stream_side_data=rotation")
    s = d["streams"][0]
    rot = next((x.get("rotation") for x in s.get("side_data_list", []) if "rotation" in x), 0)
    print(f"{os.path.basename(P.src)}: {s['width']}x{s['height']} rot={rot} {s['avg_frame_rate']}fps "
          f"{ts(P.dur)} | estilo {P.cfg['estilo']} -> {P.est['resolucao'][0]}x{P.est['resolucao'][1]}")


def _audio16k(P):
    wav = P.b("voz_16k.wav")
    if not os.path.exists(wav):
        run(["ffmpeg", "-v", "error", "-y", "-i", P.src, "-vn", "-ac", "1", "-ar", "16000", wav])
    w = wave.open(wav)
    import numpy as np
    return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


def _modelo():
    from faster_whisper import WhisperModel
    return WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count())


def transcrever(P):
    # Lemos o WAV com numpy: PyAV >= 19 quebrou o decode_audio do faster-whisper 1.2.x.
    pcm = _audio16k(P)
    segs, _ = _modelo().transcribe(pcm, language=P.cfg.get("idioma", "pt"), word_timestamps=True,
                                   vad_filter=True, beam_size=5, condition_on_previous_text=False)
    data = []
    for s in segs:
        data.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                     "words": [{"start": w.start, "end": w.end, "word": w.word, "p": w.probability}
                               for w in s.words]})
        print(f"[{s.start:7.2f}/{P.dur:.0f}] {s.text.strip()[:70]}", flush=True)
    json.dump(data, open(P.b("transcricao.json"), "w"), ensure_ascii=False)
    with open(P.b("transcricao.md"), "w") as f:  # formato compacto: 1 linha por segmento
        for i, s in enumerate(data, 1):
            low = [w["word"].strip() for w in s["words"] if w["p"] < 0.5]
            f.write(f"{i} {ts(s['start'])} {s['text']}" + (f"  ?[{', '.join(low)}]" if low else "") + "\n")
    print(f"OK: {len(data)} segmentos -> build/transcricao.md")


def trecho(P, s, e):
    pcm = _audio16k(P)
    segs, _ = _modelo().transcribe(pcm[int(float(s) * 16000):int(float(e) * 16000)],
                                   language=P.cfg.get("idioma", "pt"), beam_size=8, vad_filter=False)
    print(" ".join(x.text.strip() for x in segs))


def _palavras(P):
    d = json.load(open(P.b("transcricao.json")))
    return d, [w for s in d for w in s["words"]]


# ------------------------------------------------------------------ cortes
def cortes(P):
    _, W = _palavras(P)
    r = P.est["ritmo"]; pmin, alvo = r["pausa_min"], r["pausa_alvo"]
    manter = P.cfg["cortes"].get("manter_pausas", [])
    remover = [tuple(x[:2]) for x in P.cfg["cortes"].get("remover", [])]
    pausas = []
    for a, b in zip(W, W[1:]):
        g = b["start"] - a["end"]
        if g <= pmin:
            continue
        s, e = a["end"] + alvo * 0.45, b["start"] - alvo * 0.55
        if e - s < 0.08 or any(ms <= s <= me or ms <= e <= me for ms, me, *_ in manter):
            continue
        if any(rs <= s <= re_ or rs <= e <= re_ for rs, re_ in remover):
            continue
        pausas.append((round(s, 3), round(e, 3)))
    json.dump({"A": pausas, "B": remover}, open(P.b("cortes.json"), "w"))
    tot = sum(e - s for s, e in pausas) + sum(e - s for s, e in remover)
    with open(P.b("cortes.md"), "w") as f:
        f.write(f"Original {ts(P.dur)} -> ~{ts(P.dur - tot)} (-{tot:.0f}s)\n\n## Conteúdo (projeto.json)\n")
        for x in P.cfg["cortes"].get("remover", []):
            f.write(f"- {ts(x[0])}-{ts(x[1])} {x[2] if len(x) > 2 else ''}\n")
        f.write(f"\n## Pausas > {pmin}s comprimidas para ~{alvo}s ({len(pausas)})\n")
        for s, e in pausas:
            f.write(f"- {ts(s)} -{e - s:.2f}s\n")
    print(f"{len(pausas)} pausas + {len(remover)} cortes de conteúdo | {ts(P.dur)} -> ~{ts(P.dur - tot)}")


# ------------------------------------------------------------------ amostras (baratas em tokens)
def amostra(P, tempos):
    tempos = [float(t) for t in tempos] or [P.dur * k / 7 for k in range(1, 7)]
    ins = sum((["-ss", f"{t:.2f}", "-i", P.src] for t in tempos), [])
    n = len(tempos)
    fc = "".join(f"[{i}:v]scale=270:-2[s{i}];" for i in range(n)) + "".join(f"[s{i}]" for i in range(n)) + f"hstack={n}"
    run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-frames:v", "1", P.b("amostra.jpg")])
    print("build/amostra.jpg (" + ", ".join(ts(t) for t in tempos) + ")")


def cor(P):
    t = P.dur * 0.4
    nomes = ["neutro", "natural", "quente", "vibrante"]
    fc = "[0:v]split=4" + "".join(f"[i{k}]" for k in range(4)) + ";"
    for k, n in enumerate(nomes):
        fc += (f"[i{k}]{GRADES[n]},scale=360:-2,drawtext=text='{n.upper()}':x=12:y=12:fontsize=24:"
               f"fontcolor=white:box=1:boxcolor=black@0.5[o{k}];")
    fc += "".join(f"[o{k}]" for k in range(4)) + "hstack=4"
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.1f}", "-i", P.src, "-filter_complex", fc,
         "-frames:v", "1", P.b("cor.jpg")])
    print(f"build/cor.jpg (quadro em {ts(t)}); estilo atual usa '{P.est['cor']}'")


# ------------------------------------------------------------------ gráficos (HyperFrames)
def _css(P):
    pal, fo, g = P.est["paleta"], P.est["fontes"], P.est["graficos"]
    W, H = P.est["resolucao"]
    horiz = W > H
    u = min(W, H) / 1080  # unidade de escala
    top, lat = int(H * g["topo"]), int(W * g["lateral"])
    card_w = f"width:{int(W * 0.42)}px" if horiz else f"right:{lat}px"
    pill_pos = f"left:{lat}px" if horiz else "left:50%;transform:translateX(-50%)"
    return f"""
@font-face{{font-family:'Playfair';src:url('../assets/fonts/PlayfairDisplay.ttf');font-weight:400 900}}
@font-face{{font-family:'Playfair';font-style:italic;src:url('../assets/fonts/PlayfairDisplay-Italic.ttf');font-weight:400 900}}
@font-face{{font-family:'Vibes';src:url('../assets/fonts/GreatVibes-Regular.ttf')}}
@font-face{{font-family:'Mont';src:url('../assets/fonts/Montserrat.ttf');font-weight:100 900}}
@font-face{{font-family:'Anton';src:url('../assets/fonts/Anton-Regular.ttf')}}
:root{{--claro:{pal['claro']};--acento:{pal['acento']};--acento-e:{pal['acento_escuro']};--dourado:{pal['dourado']};--texto:{pal['texto']};--fundo:{pal['fundo']}}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:transparent}}
#root{{position:relative;width:{W}px;height:{H}px}}
.abs{{position:absolute}}
.pill{{{pill_pos};top:{top}px;padding:{18*u:.0f}px {44*u:.0f}px;border-radius:999px;background:var(--claro);opacity:.95;
  box-shadow:0 10px 40px rgba(0,0,0,.25);white-space:nowrap;display:flex;align-items:center;gap:{22*u:.0f}px}}
.pill .num{{font-family:'Mont';font-weight:700;font-size:{26*u:.0f}px;letter-spacing:.2em;color:var(--acento-e)}}
.pill .t{{font-family:'{fo['titulo']}';font-style:italic;font-weight:600;font-size:{50*u:.0f}px;color:var(--texto)}}
.card{{left:{lat}px;{card_w};top:{top - int(30*u)}px;padding:{36*u:.0f}px {46*u:.0f}px;border-radius:{36*u:.0f}px;
  background:var(--claro);box-shadow:0 14px 50px rgba(0,0,0,.28);color:var(--texto)}}
.kicker{{font-family:'Mont';font-weight:700;font-size:{26*u:.0f}px;letter-spacing:.24em;color:var(--acento-e);text-transform:uppercase}}
.big{{font-family:'{fo['titulo']}';font-weight:700;font-size:{68*u:.0f}px;line-height:1.05;margin-top:{8*u:.0f}px}}
.sub{{font-family:'Mont';font-weight:500;font-size:{34*u:.0f}px;margin-top:{10*u:.0f}px;opacity:.8}}
.it{{display:flex;align-items:center;gap:{20*u:.0f}px;font-family:'Mont';font-weight:600;font-size:{36*u:.0f}px;margin-top:{16*u:.0f}px}}
.it .h{{min-width:{110*u:.0f}px;font-family:'{fo['titulo']}';font-weight:700;font-size:{38*u:.0f}px;color:var(--acento-e)}}
.it .dot{{width:{16*u:.0f}px;height:{16*u:.0f}px;border-radius:50%;background:var(--acento)}}
.quote{{left:{lat}px;right:{lat}px;top:{top}px;text-align:center;color:#fff;text-shadow:0 4px 24px rgba(0,0,0,.55)}}
.quote .q1{{font-family:'{fo['script']}';font-size:{110*u:.0f}px;line-height:1}}
.quote .q2{{font-family:'{fo['titulo']}';font-style:italic;font-weight:600;font-size:{52*u:.0f}px;margin-top:{10*u:.0f}px}}
.full{{inset:0;background:var(--fundo)}}
.bgimg{{inset:-40px;background-size:cover;background-position:center;filter:blur(26px) brightness(.6)}}
.center{{left:0;right:0;text-align:center;color:var(--claro)}}
"""


def _page(P, cid, dur, body, js):
    W, H = P.est["resolucao"]
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width={W}, height={H}"/>
<script src="../assets/gsap.min.js"></script><style>{_css(P)}</style></head><body>
<div id="root" data-composition-id="{cid}" data-start="0" data-duration="{dur}" data-width="{W}" data-height="{H}">
{body}</div>
<script>const tl = gsap.timeline({{ paused: true }});
{js}
window.__timelines = window.__timelines || {{}}; window.__timelines["{cid}"] = tl; tl.seek(0);</script>
</body></html>"""


def _entra_sai(dur, sel):
    return (f'tl.fromTo("{sel}",{{opacity:0,y:40,scale:.96}},{{opacity:1,y:0,scale:1,duration:.6,ease:"power3.out"}},0);\n'
            f'tl.to("{sel}",{{opacity:0,y:-20,duration:.5,ease:"power2.in"}},{dur - .5});\n')


def _comp_tela(P, cid, c, fundo_t):
    """abertura/encerramento: tela cheia opaca com o quadro do vídeo desfocado ao fundo."""
    u = min(P.est["resolucao"]) / 1080; fo = P.est["fontes"]
    d = c.get("dur", 4.0)
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{fundo_t:.2f}", "-i", P.src, "-frames:v", "1",
         "-vf", GRADES[P.est["cor"]], P.b("hf", "assets", f"{cid}.jpg")])
    e = html.escape
    body = (f'<div class="abs full"></div><div class="abs bgimg" style="background-image:url(\'../assets/{cid}.jpg\')"></div>'
            f'<div class="abs" style="inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:{24*u:.0f}px;text-align:center;color:var(--claro)">'
            f'<div id="a" style="font-family:\'{fo["script"]}\';font-size:{100*u:.0f}px;line-height:1.1">{e(c.get("linha1",""))}</div>'
            f'<div id="b" style="font-family:\'{fo["titulo"]}\';font-weight:700;font-size:{80*u:.0f}px;line-height:1.1;max-width:85%">{e(c.get("titulo",""))}</div>'
            f'<div id="c" style="font-family:\'Mont\';font-weight:600;font-size:{32*u:.0f}px;letter-spacing:.25em">{e(c.get("sub","").upper())}</div></div>')
    js = ('tl.fromTo(".bgimg",{scale:1},{scale:1.08,duration:%s,ease:"none"},0);' % d +
          'tl.fromTo("#a",{opacity:0,y:30},{opacity:1,y:0,duration:.9},0.2);'
          'tl.fromTo("#b",{opacity:0,y:30},{opacity:1,y:0,duration:.9},0.6);'
          'tl.fromTo("#c",{opacity:0},{opacity:1,duration:.8},1.1);'
          f'tl.to(["#a","#b","#c"],{{opacity:0,duration:.5}},{d - .55});')
    return d, _page(P, cid, d, body, js)


def graficos(P):
    hf = P.b("hf")
    for sub in ("compositions", "assets", "renders"):
        os.makedirs(os.path.join(hf, sub), exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "assets", "fonts"), os.path.join(hf, "assets", "fonts"), dirs_exist_ok=True)
    shutil.copy(os.path.join(ROOT, "hyperframes", "node_modules", "gsap", "dist", "gsap.min.js"),
                os.path.join(hf, "assets"))
    open(os.path.join(hf, "hyperframes.json"), "w").write('{"paths":{"assets":"assets"}}')
    open(os.path.join(hf, "index.html"), "w").write("<!doctype html><html><body></body></html>")
    man, e = [], html.escape
    if P.cfg.get("abertura"):
        d, h = _comp_tela(P, "abertura", P.cfg["abertura"], 1.0); man.append(("abertura", None, d, h))
    if P.cfg.get("encerramento"):
        d, h = _comp_tela(P, "encerramento", P.cfg["encerramento"], P.dur - 2); man.append(("encerramento", None, d, h))
    ncap = 0
    for k, g in enumerate(P.cfg.get("graficos", [])):
        t, cid = g["tipo"], f"g{k:02d}_{g['tipo']}"
        if t == "capitulo":
            ncap += 1; d = g.get("dur", 3.2)
            body = f'<div class="abs pill" id="x"><span class="num">{ncap:02d}</span><span class="t">{e(g["texto"])}</span></div>'
            js = (f'tl.fromTo("#x",{{opacity:0,y:-30}},{{opacity:1,y:0,duration:.55,ease:"power3.out"}},0);'
                  f'tl.to("#x",{{opacity:0,y:-20,duration:.45}},{d - .45});')
        elif t == "card":
            d = g.get("dur", 5)
            body = (f'<div class="abs card" id="x"><div class="kicker">{e(g.get("kicker",""))}</div>'
                    f'<div class="big">{e(g.get("titulo",""))}</div><div class="sub">{e(g.get("sub",""))}</div></div>')
            js = _entra_sai(d, "#x")
        elif t == "lista":
            d = g.get("dur", 10); a = g["ancora"]
            rows = "".join(f'<div class="it" id="i{j}"><span class="h">{e(str(h))}</span><span class="dot"></span>'
                           f'<span>{e(txt)}</span></div>' for j, (_, h, txt) in enumerate(g["itens"]))
            body = f'<div class="abs card" id="x"><div class="kicker">{e(g.get("kicker",""))}</div>{rows}</div>'
            js = _entra_sai(d, "#x") + "".join(
                f'tl.fromTo("#i{j}",{{opacity:0,x:-30}},{{opacity:1,x:0,duration:.45}},{max(0.3, tt - a):.2f});'
                for j, (tt, _, _) in enumerate(g["itens"]))
        elif t == "citacao":
            d = g.get("dur", 5)
            body = (f'<div class="abs quote" id="x"><div class="q1" id="q1">{e(g.get("linha1",""))}</div>'
                    f'<div class="q2" id="q2">{e(g.get("linha2",""))}</div></div>')
            js = (f'tl.fromTo("#q1",{{opacity:0,scale:.85}},{{opacity:1,scale:1,duration:.9}},0);'
                  f'tl.fromTo("#q2",{{opacity:0,y:20}},{{opacity:1,y:0,duration:.8}},1.2);'
                  f'tl.to("#x",{{opacity:0,duration:.6}},{d - .6});')
        else:
            sys.exit(f"tipo de gráfico desconhecido: {t}")
        man.append((cid, g["ancora"], d, _page(P, cid, d, body, js)))
    manifest = []
    for cid, anc, d, h in man:
        path = os.path.join(hf, "compositions", f"{cid}.html")
        mov = os.path.join(hf, "renders", f"{cid}.mov")
        novo = not os.path.exists(path) or open(path).read() != h
        open(path, "w").write(h)
        if novo or not os.path.exists(mov):  # só re-renderiza o que mudou (sequencial: Chrome usa muita CPU)
            run(["hyperframes", "render", hf, "-c", f"compositions/{cid}.html", "--format", "mov",
                 "-o", mov, "--quiet"], quiet=True)
            print(f"  renderizado {cid}", flush=True)
        manifest.append({"name": cid, "anchor": anc, "dur": d})
    for w in glob.glob(os.path.join(hf, "renders", "work-*")):
        shutil.rmtree(w, ignore_errors=True)
    json.dump(manifest, open(P.b("graficos.json"), "w"), indent=1)
    print(f"{len(manifest)} gráficos prontos")


# ------------------------------------------------------------------ plano (linha do tempo + legendas + trilha)
def plano(P):
    FPS, DUR = P.fps, P.dur
    fr = lambda t: int(round(t * FPS)); ft = lambda n: float(n / FPS)
    c = json.load(open(P.b("cortes.json")))
    cuts = sorted([tuple(x) for x in c["A"]] + [tuple(x) for x in c["B"]])
    keep, cur = [], 0.0
    for s, e in cuts:
        if s > cur:
            keep.append((cur, s))
        cur = max(cur, e)
    if cur < DUR:
        keep.append((cur, DUR))
    gm = {g["name"]: g for g in json.load(open(P.b("graficos.json")))} if os.path.exists(P.b("graficos.json")) else {}
    intro_f = fr(gm["abertura"]["dur"]) if "abertura" in gm else 0
    outro_f = fr(gm["encerramento"]["dur"]) if "encerramento" in gm else 0
    segs, out_f = [], intro_f
    for s, e in keep:
        fs, fe = fr(s), fr(e)
        if fe - fs >= 3:
            segs.append({"i": len(segs), "f0": fs, "f1": fe, "out0": out_f}); out_f += fe - fs
    total_f = out_f + outro_f
    END = ft(total_f)

    def to_out(t):
        f = t * float(FPS)
        for sg in segs:
            if sg["f0"] <= f < sg["f1"]:
                return ft(sg["out0"]) + (t - ft(sg["f0"]))
        return None

    def near(t):
        if t == "fim":
            return END
        if t == 0:
            return 0.0
        o = to_out(t)
        if o is not None:
            return o
        return next((ft(sg["out0"]) for sg in segs if sg["f0"] / float(FPS) > t), ft(out_f))

    overlays = [{"name": n, "t": round(near(g["anchor"]), 3)} for n, g in gm.items() if g["anchor"] is not None]
    A = P.est["audio"]
    mus = []
    for m in P.cfg.get("musica", []):
        arq = P.p(m["arquivo"])
        if not os.path.exists(arq):
            print(f"  aviso: música ausente {m['arquivo']} (ignorada)"); continue
        vol = m.get("volume") or (A["musica_destaque"] if m.get("destaque") else A["musica_volume"])
        mus.append([arq, m.get("inicio_faixa", 0), near(m["de"]), near(m["ate"]), vol])
    _legendas(P, to_out)
    json.dump({"fps": str(FPS), "segs": segs, "intro_f": intro_f, "outro_f": outro_f, "total_f": total_f,
               "overlays": overlays, "musica": mus}, open(P.b("plano.json"), "w"), indent=1)
    print(f"{len(segs)} trechos | final {ts(END)} | {len(overlays)} gráficos | {len(mus)} blocos de música")


def _ass_t(t):
    cs = int(round(max(0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_cor(hexc, alpha="00"):
    h = hexc.lstrip("#")
    return f"&H{alpha}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _legendas(P, to_out):
    L, lc = P.est["legendas"], P.cfg.get("legendas", {})
    if not lc.get("ativar", True):
        open(P.b("legendas.ass"), "w").write(""); return
    data, _ = _palavras(P)
    fix, sub = lc.get("correcoes", {}), {int(k): v for k, v in lc.get("substituir_segmento", {}).items()}
    words = []
    for si, s in enumerate(data, 1):
        ws = s["words"]
        if si in sub:
            txt = sub[si].split()
            if not txt:
                continue
            a, b = ws[0]["start"], ws[-1]["end"]; st = (b - a) / len(txt)
            ws = [{"start": a + k * st, "end": a + (k + 1) * st, "word": w} for k, w in enumerate(txt)]
        for w in ws:
            raw = w["word"].strip()
            for errado, certo in fix.items():
                raw = raw.replace(errado, certo)
            o0 = to_out(w["start"] + 0.02)
            if o0 is None:
                continue
            o1 = to_out(max(w["start"] + 0.03, w["end"] - 0.02)) or o0 + 0.25
            t = raw.rstrip(".,")
            if words and t.lower() == words[-1]["w"].lower() and len(t) <= 3:
                continue  # gaguejada ("o o")
            words.append({"s": o0, "e": max(o1, o0 + 0.05), "w": t, "os": w["start"], "oe": w["end"],
                          "brk": raw.endswith((".", ",", "?", "!"))})
    groups, g = [], []
    for w in words:
        if g and (len(g) >= L["max_palavras"] or len(" ".join(x["w"] for x in g + [w])) > L["max_chars"]
                  or w["s"] - g[-1]["e"] > 0.45 or w["os"] - g[-1]["oe"] > 0.6):
            groups.append(g); g = []
        g.append(w)
        if w["brk"]:
            groups.append(g); g = []
    if g:
        groups.append(g)
    up = (lambda x: x.upper()) if L["maiusculas"] else (lambda x: x)
    hl, base = _ass_cor(L["destaque"]), _ass_cor(L["cor"])
    ev = []
    for gi, g in enumerate(groups):
        g_end = g[-1]["e"] + 0.15
        if gi + 1 < len(groups):
            g_end = min(g_end + 0.25, groups[gi + 1][0]["s"])
        if not L["karaoke"]:
            ev.append(f"Dialogue: 0,{_ass_t(g[0]['s'])},{_ass_t(g_end)},Leg,,0,0,0,,{' '.join(up(x['w']) for x in g)}")
            continue
        for k, w in enumerate(g):
            e = g[k + 1]["s"] if k + 1 < len(g) else g_end
            txt = " ".join("{\\c" + hl + "&}" + up(x["w"]) + "{\\c" + base + "&}" if j == k else up(x["w"])
                           for j, x in enumerate(g))
            ev.append(f"Dialogue: 0,{_ass_t(w['s'])},{_ass_t(e)},Leg,,0,0,0,,{txt}")
    W, H = P.est["resolucao"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Leg,{L['fonte']},{L['tamanho']},{base},{base},&H00201418,&H80000000,-1,0,0,0,100,100,1,0,1,{L['contorno']},{L['sombra']},2,70,70,{L['margem_inferior']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    open(P.b("legendas.ass"), "w").write(head + "\n".join(ev) + "\n")
    print(f"  legendas: {len(words)} palavras em {len(groups)} blocos")


# ------------------------------------------------------------------ segmentos (cor + zoom)
def _smooth(x):
    c = f"clip({x},0,1)"
    return f"({c}*{c}*(3-2*{c}))"


def _zoom_expr(P, t0, t1, base):
    Z = P.est["zoom"]; T = f"({t0:.4f}+t)"; terms = []
    for m in P.cfg.get("zoom", []):
        a, b, kind = m["de"], m["ate"], m["tipo"]
        k = m.get("intensidade", Z[kind])
        ri, ro = ((b - a), 0.8) if kind == "lento" else (0.18, 0.45)
        if b + ro < t0 or a > t1:
            continue
        terms.append(f"{k}*{_smooth(f'({T}-{a})/{ri}')}*(1-{_smooth(f'({T}-{b})/{ro}')})")
    return f"{base}*(1+{'+'.join(terms)})" if terms else f"{base}"


def segmentos(P):
    PL = json.load(open(P.b("plano.json")))
    FPS = Fraction(PL["fps"]); ft = lambda n: float(n / FPS)
    W, H, av = P.W, P.H, P.est["zoom"]["ancora_vertical"]
    lista = []
    for sg in PL["segs"]:
        base = 1.0 if sg["i"] % 2 == 0 else P.est["ritmo"]["alternar_zoom"]
        n = sg["f1"] - sg["f0"]; dur = ft(n)
        z = _zoom_expr(P, ft(sg["f0"]), ft(sg["f1"]), base)
        out = P.b(f"seg_{sg['i']:03d}{P.suf}.mkv"); lista.append(os.path.basename(out))
        if os.path.exists(out):
            continue
        vf = (f"{GRADES[P.est['cor']]},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame:flags=lanczos,"
              f"crop={W}:{H}:(iw-{W})/2:(ih-{H})*{av},setsar=1,format=yuv420p")
        af = (f"atrim=0:{dur:.5f},asetpts=PTS-STARTPTS,afade=t=in:d=0.012,"
              f"afade=t=out:st={dur - 0.012:.5f}:d=0.012,apad=whole_dur={dur:.5f}")
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ft(sg['f0']):.5f}", "-i", P.src, "-vf", vf, "-af", af,
             "-frames:v", str(n), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast" if PREVIEW else "fast",
             "-crf", "14", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out])
        print(f"  trecho {sg['i'] + 1}/{len(PL['segs'])} ({dur:.1f}s)", flush=True)
    seq = []
    for nm, nf in (("abertura", PL["intro_f"]), ("encerramento", PL["outro_f"])):
        if not nf:
            continue
        out = P.b(f"{nm}{P.suf}.mkv")
        if not os.path.exists(out):
            run(["ffmpeg", "-v", "error", "-y", "-i", P.b("hf", "renders", f"{nm}.mov"), "-f", "lavfi", "-i",
                 "anullsrc=r=48000:cl=stereo", "-vf", f"scale={W}:{H},fps={FPS},format=yuv420p,setsar=1",
                 "-frames:v", str(nf), "-af", f"atrim=0:{ft(nf):.5f}", "-shortest", "-r", str(FPS),
                 "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-c:a", "pcm_s16le", out])
    if PL["intro_f"]:
        seq.append(f"abertura{P.suf}.mkv")
    seq += lista
    if PL["outro_f"]:
        seq.append(f"encerramento{P.suf}.mkv")
    open(P.b(f"concat{P.suf}.txt"), "w").write("".join(f"file '{x}'\n" for x in seq))
    print(f"{len(lista)} trechos prontos")


# ------------------------------------------------------------------ final
def final(P):
    PL = json.load(open(P.b("plano.json")))
    FPS = Fraction(PL["fps"]); END = float(PL["total_f"] / FPS)
    W, H, A = P.W, P.H, P.est["audio"]
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", P.b(f"concat{P.suf}.txt"),
         "-c", "copy", P.b(f"montado{P.suf}.mkv")])
    ins, fc, v = ["-i", P.b(f"montado{P.suf}.mkv")], [], "[0:v]"
    for k, o in enumerate(PL["overlays"], 1):
        ins += ["-i", P.b("hf", "renders", f"{o['name']}.mov")]
        fc.append(f"[{k}:v]scale={W}:{H},setpts=PTS+{o['t']:.3f}/TB[g{k}]")
        fc.append(f"{v}[g{k}]overlay=0:0:eof_action=pass:format=auto[v{k}]"); v = f"[v{k}]"
    Wf, Hf = P.est["resolucao"]
    if os.path.getsize(P.b("legendas.ass")):
        fc.append(f"{v}subtitles={P.b('legendas.ass')}:fontsdir={ROOT}/assets/fonts:original_size={Wf}x{Hf}[vs]"); v = "[vs]"
    fc.append(f"{v}format=yuv420p[vout]")
    voz = ("[0:a]highpass=f=80,afftdn=nr=10:nf=-32,equalizer=f=3200:t=q:w=1.2:g=2,"
           "acompressor=threshold=-22dB:ratio=3:attack=8:release=160:makeup=3")
    if PL["musica"]:
        n0, xf, mix = len(ins) // 2, A["crossfade"], []
        for j, (arq, ini, a, b, vol) in enumerate(PL["musica"]):
            ins += ["-i", arq]
            st = max(0.0, a - (xf / 2 if a else 0)); en = b + (xf / 2 if b < END - 0.1 else 0); Ln = en - st
            fi = 0.01 if a == 0 else xf; fo = 3.5 if b >= END - 0.1 else xf
            fc.append(f"[{n0 + j}:a]atrim={ini:.3f}:{ini + Ln:.3f},asetpts=PTS-STARTPTS,"
                      f"aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},afade=t=in:d={fi},"
                      f"afade=t=out:st={max(0, Ln - fo):.3f}:d={fo},adelay={int(st * 1000)}:all=1[m{j}]")
            mix.append(f"[m{j}]")
        fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=longest,apad,atrim=0:{END:.4f}[mus]")
        fc.append(voz + ",asplit=2[voz][sc]")
        fc.append("[mus][sc]sidechaincompress=threshold=0.015:ratio=10:attack=25:release=450[musd]")  # ducking
        fc.append(f"[voz][musd]amix=inputs=2:normalize=0:duration=first,loudnorm=I={A['loudness']}:TP=-1.5:LRA=11,aresample=48000[aout]")
    else:
        fc.append(voz + f",loudnorm=I={A['loudness']}:TP=-1.5:LRA=11,aresample=48000[aout]")
    open(P.b(f"filtro{P.suf}.txt"), "w").write(";\n".join(fc))
    nome = os.path.basename(P.dir)
    out = P.p("saida", f"{nome}_preview.mp4" if PREVIEW else f"{nome}_{Wf}x{Hf}.mp4")
    run(["ffmpeg", "-v", "error", "-stats", "-y", *ins, "-/filter_complex", P.b(f"filtro{P.suf}.txt"),
         "-map", "[vout]", "-map", "[aout]", "-r", str(FPS), "-c:v", "libx264",
         "-preset", "veryfast" if PREVIEW else "slow", "-crf", "26" if PREVIEW else "17", "-pix_fmt", "yuv420p",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    print(f"pronto: {os.path.relpath(out, ROOT)} ({ts(END)})")
    if any(g.get("tipo") == "capitulo" for g in P.cfg.get("graficos", [])):
        _capitulos_youtube(P, PL)


def _capitulos_youtube(P, PL):
    """Lista de capítulos no formato da descrição do YouTube."""
    gm = {g["name"]: g for g in json.load(open(P.b("graficos.json")))}
    linhas = ["00:00 Início"]
    caps = [g for g in P.cfg["graficos"] if g["tipo"] == "capitulo"]
    for k, (o, g) in enumerate(zip([o for o in PL["overlays"] if o["name"].endswith("capitulo")], caps)):
        t = o["t"]; linhas.append(f"{int(t // 60):02d}:{int(t % 60):02d} {g['texto']}")
    open(P.p("saida", "capitulos.txt"), "w").write("\n".join(linhas) + "\n")


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    if len(ARGS) < 2:
        sys.exit(__doc__)
    P, etapa, extra = Proj(ARGS[0]), ARGS[1], ARGS[2:]
    etapas = {"info": info, "transcrever": transcrever, "cortes": cortes, "cor": cor, "graficos": graficos,
              "plano": plano, "segmentos": segmentos, "final": final}
    if etapa == "trecho":
        trecho(P, *extra)
    elif etapa == "amostra":
        amostra(P, extra)
    elif etapa == "tudo":
        for f in (graficos, plano, segmentos, final):
            f(P)
    elif etapa in etapas:
        etapas[etapa](P)
    else:
        sys.exit(__doc__)
