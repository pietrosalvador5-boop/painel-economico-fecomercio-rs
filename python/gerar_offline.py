"""Painel Econômico Fecomércio-RS - página em um único arquivo HTML (site e versão offline).

Junta a página (pagina/index.html), os CSV de dados/ (gerados por coleta.py) e a biblioteca d3
(pagina/vendor/d3.min.js), aplica o tema da Fecomércio-RS (tema.css e logo/logo_fecomercio_cor.png) e grava
offline/Painel_Economico_Fecomercio_RS.html e index.html (a página publicada no GitHub Pages).
O arquivo abre com dois cliques em qualquer navegador, sem internet.

Uso: python3 python/gerar_offline.py
"""
import base64
import csv
import json
from datetime import date
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
DADOS, PAGINA = PASTA / "dados", PASTA / "pagina"
SAIDA = PASTA / "offline" / "Painel_Economico_Fecomercio_RS.html"
SITE = PASTA / "index.html"
LOGO = PASTA / "logo" / "logo_fecomercio_cor.png"
DATASETS = ["atividade", "precos", "meta", "juros_cambio", "trabalho", "pib", "focus", "caged"]

# Variáveis de estilo que o dashboard do Claude fornece; aqui recriadas, com tema claro e escuro.
TEMA = """
:root {
  --color-bg: #ffffff; --color-fg: #1d2330; --color-fg-muted: #5f6675; --color-panel: #f6f7f9;
  --color-border-line: #e1e4ea; --color-ok: #1f7a4d; --color-bad: #b4372f;
  --cds-chart-grid: #e8ebf0; --cds-chart-axis: #9aa1ad; --cds-chart-reference: #7b8291; --cds-chart-muted: #b9bfca;
  --cds-surface-popover: #ffffff; --cds-border: #d5d9e0; --cds-shadow-popover: 0 4px 16px rgba(20, 28, 45, .12);
  --cds-text-secondary: #5f6675;
  --s1: #1f4e8c; --s2: #c0612b; --s3: #2e8a6e; --s4: #7b5ea7;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) { :root {
  --color-bg: #15181e; --color-fg: #e8eaee; --color-fg-muted: #a2a8b3; --color-panel: #1d2129;
  --color-border-line: #2e333d; --color-ok: #5cc28f; --color-bad: #f07b6f;
  --cds-chart-grid: #2a2f38; --cds-chart-axis: #5d6471; --cds-chart-reference: #8a919d; --cds-chart-muted: #4c525d;
  --cds-surface-popover: #232833; --cds-border: #3a404b; --cds-shadow-popover: 0 4px 16px rgba(0, 0, 0, .45);
  --cds-text-secondary: #a2a8b3;
  --s1: #6ea4e8; --s2: #ee935a; --s3: #5cc2a0; --s4: #b399dd;
  color-scheme: dark;
} }
:root {
  --font-anthropic-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-anthropic-serif: Georgia, "Times New Roman", serif;
  --cds-font-size-caption: 12px; --cds-font-size-body: 14px; --cds-font-size-heading: 16px; --cds-font-size-title: 28px;
  --cds-font-weight-medium: 600;
  --cds-gap-xs: 6px; --cds-gap-sm: 10px; --cds-gap-md: 16px; --cds-gap-lg: 24px; --cds-gap-xl: 32px;
  --cds-pad-xs: 6px; --cds-pad-sm: 10px; --cds-pad-md: 14px; --cds-pad-lg: 18px;
  --cds-radius: 10px; --cds-dur-slow: 300ms;
}
html, body { margin: 0; background: var(--color-bg); color: var(--color-fg); }
#dash-root { padding: 28px var(--dash-gutter, 24px) 48px; }
.dash-skeleton { color: transparent !important; background: var(--color-border-line); border-radius: 4px; }
.pe-rodape { max-width: 1280px; margin: 32px auto 0; font-family: var(--font-anthropic-sans); font-size: 12px; color: var(--color-fg-muted); }
"""

# Substitui o objeto `dash` do dashboard: dados embutidos, cálculos e redesenho ao mudar a largura.
SHIM = """
(function () {
  const brutos = window.__DADOS__, calcs = {}, cache = {}, cbs = [];
  const cores = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)'];
  window.dash = {
    colors: cores,
    data(id) {
      if (brutos[id]) return { status: 'ok', data: brutos[id].rows, columns: brutos[id].columns, meta: [] };
      if (calcs[id]) {
        if (!(id in cache)) cache[id] = calcs[id].fn(...calcs[id].inputs.map(i => window.dash.data(i).data));
        return { status: 'ok', data: cache[id], meta: [] };
      }
      return { status: 'missing', data: [] };
    },
    calc(id, o) { calcs[id] = o; },
    loader() {},
    onData(fn) { cbs.push(fn); requestAnimationFrame(() => fn()); },
    refresh() {}, params() { return {}; }, setParams() {}, resetParams() {},
    setLink(nome) { try { history.replaceState(null, '', '#' + nome); } catch (e) {} },
  };
  let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => cbs.forEach(f => f()), 150); });
})();
"""


def main():
    dados = {}
    for ds in DATASETS:
        if not (DADOS / f"{ds}.csv").exists():          # CAGED ainda sem histórico baixado
            dados[ds] = {"columns": [], "rows": []}
            continue
        with open(DADOS / f"{ds}.csv", encoding="utf-8") as f:
            r = csv.DictReader(f)
            linhas = list(r)
            dados[ds] = {"columns": r.fieldnames, "rows": linhas}
    pagina = (PAGINA / "index.html").read_text(encoding="utf-8")
    tema_fc = (PAGINA / "tema.css").read_text(encoding="utf-8")
    logo = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()
    pagina = pagina.replace("LOGO_FECOMERCIO", logo)
    d3 = (PAGINA / "vendor" / "d3.min.js").read_text(encoding="utf-8")
    ult = max(l["data"] for l in dados["atividade"]["rows"] + dados["precos"]["rows"])
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel Econômico | Fecomércio-RS</title>
<style>{TEMA}</style>
<style>{tema_fc}</style>
</head>
<body>
<div class="fc-faixa"></div>
<div id="dash-root">
<script>{d3}</script>
<script>window.__DADOS__ = {json.dumps(dados, ensure_ascii=False)};</script>
<script>{SHIM}</script>
{pagina}
<p class="pe-rodape">Versão offline gerada em {date.today():%d/%m/%Y}, com dados até {ult[5:7]}/{ult[:4]}.
Fontes: IBGE (PMC, PMS, PIM-PF, IPCA, PNAD Contínua, Contas Nacionais), Banco Central (IBC-Br, IBCR-RS, Selic,
câmbio, Focus), Ministério do Trabalho e Emprego (Novo CAGED) e Conselho Monetário Nacional (metas de inflação).
Elaboração: Assessoria Econômica | Fecomércio-RS.</p>
</div>
</body>
</html>
"""
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text(html, encoding="utf-8")
    SITE.write_text(html, encoding="utf-8")
    print("Salvo:", SAIDA, f"({len(html.encode()) / 1024:.0f} KB) e index.html")


if __name__ == "__main__":
    main()
