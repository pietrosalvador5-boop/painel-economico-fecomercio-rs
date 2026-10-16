"""Painel da Economia Brasil e RS - coleta dos dados.

Baixa as séries do Banco Central (SGS, Focus) e do IBGE (SIDRA) e grava em dados/ os 7 CSV que o painel
usa (separador vírgula, ponto decimal, datas ISO), desde 2015. Baixa tudo de novo a cada execução, então
meses novos e revisões entram sozinhos.

Uso: python3 python/coleta.py
"""
import csv
import json
import subprocess
import time
import unicodedata
from datetime import date
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
DADOS = PASTA / "dados"
INICIO = "2015-01-01"          # primeira data gravada
BUSCA = "01/01/2012"           # primeira data baixada (folga para variações em 12 e 24 meses)
HOJE = date.today()

# Metas de inflação do CMN: centro e intervalo de tolerância (p.p.)
METAS = {2015: (4.5, 2.0), 2016: (4.5, 2.0), 2017: (4.5, 1.5), 2018: (4.5, 1.5), 2019: (4.25, 1.5),
         2020: (4.0, 1.5), 2021: (3.75, 1.5), 2022: (3.5, 1.5), 2023: (3.25, 1.5), 2024: (3.0, 1.5),
         2025: (3.0, 1.5), 2026: (3.0, 1.5), 2027: (3.0, 1.5)}


# ---------- download ----------
def baixar(url, tentativas=5):
    """JSON de uma URL, pelo curl do sistema (evita problemas de certificado do Python no Mac)."""
    for i in range(tentativas):
        r = subprocess.run(["curl", "-s", "-m", "180", url], capture_output=True)
        try:
            return json.loads(r.stdout)
        except ValueError:
            print(f"  sem resposta ({url[:70]}...), tentando de novo em 10 s")
            time.sleep(10)
    raise RuntimeError(f"Fonte não respondeu: {url}")


def sgs(codigo, inicio=BUSCA, fim=None):
    fim = fim or HOJE.strftime("%d/%m/%Y")
    x = baixar(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
               f"&dataInicial={inicio}&dataFinal={fim}")
    if not isinstance(x, list):
        raise RuntimeError(f"SGS {codigo}: {x}")
    return {f"{d['data'][6:10]}-{d['data'][3:5]}-{d['data'][:2]}": float(d["valor"]) for d in x if d["valor"] != ""}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def sidra(caminho):
    """Linhas da API do SIDRA, com as colunas nomeadas pelo cabeçalho (sem acentos)."""
    x = baixar("https://apisidra.ibge.gov.br/values" + caminho)
    if not isinstance(x, list) or len(x) < 2:
        raise RuntimeError(f"SIDRA {caminho}: {x}")
    cab = {k: sem_acento(v) for k, v in x[0].items()}
    return [{cab[k]: v for k, v in linha.items()} for linha in x[1:]]


def valor(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mes(cod):        # 202608 -> 2026-08-01
    return f"{cod[:4]}-{cod[4:6]}-01"


def trimestre(cod):  # 202602 -> 2026-04-01 (primeiro mês do trimestre)
    return f"{cod[:4]}-{(int(cod[4:6]) - 1) * 3 + 1:02d}-01"


def r4(v):
    return "" if v is None else round(v, 4)


def gravar(nome, colunas, linhas):
    with open(DADOS / f"{nome}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(colunas)
        w.writerows(linhas)
    print(f"{nome:14s} {len(linhas):5d} linhas")


def acum12(serie):
    """Variação acumulada em 12 meses a partir das variações mensais (%)."""
    datas, out = sorted(serie), {}
    for i in range(11, len(datas)):
        p = 1.0
        for d in datas[i - 11:i + 1]:
            p *= 1 + serie[d] / 100
        out[datas[i]] = (p - 1) * 100
    return out


# ---------- atividade: PMC, PMS, PIM-PF e IBC ----------
def atividade():
    pesquisas = {
        "Varejo (PMC)": (8880, {"indice_sa": "7170", "var_mm": "11708", "var_aa": "11709", "var_12m": "11711"}, "c11046/56734"),
        "Serviços (PMS)": (5906, {"indice_sa": "7168", "var_mm": "11623", "var_aa": "11624", "var_12m": "11626"}, "c11046/56726"),
        "Indústria (PIM)": (8888, {"indice_sa": "12607", "var_mm": "11601", "var_aa": "11602", "var_12m": "11604"}, "c544/129314"),
    }
    linhas = []
    for ind, (tab, var, cls) in pesquisas.items():
        nome_var = {v: k for k, v in var.items()}
        for regiao, nivel in [("Brasil", "n1/all"), ("RS", "n3/43")]:
            dados = {}
            for l in sidra(f"/t/{tab}/{nivel}/v/{','.join(var.values())}/p/all/{cls}"):
                dados.setdefault(mes(l["Mes (Codigo)"]), {})[nome_var[l["Variavel (Codigo)"]]] = valor(l["Valor"])
            linhas += [[d, regiao, ind] + [r4(v.get(k)) for k in var] for d, v in dados.items()]
    # IBC-Br e IBCR-RS: dessazonalizado para o índice e a variação no mês; sem ajuste para as demais
    for regiao, cod_sa, cod_ns in [("Brasil", 24364, 24363), ("RS", 25404, 25401)]:
        sa, ns = sgs(cod_sa), sgs(cod_ns)
        ds = sorted(sa)
        for i, d in enumerate(ds):
            mm = 100 * (sa[d] / sa[ds[i - 1]] - 1) if i >= 1 else None
            aa = 100 * (ns[d] / ns[ds[i - 12]] - 1) if i >= 12 and d in ns and ds[i - 12] in ns else None
            v12 = None
            if i >= 23 and all(x in ns for x in ds[i - 23:i + 1]):
                v12 = 100 * (sum(ns[x] for x in ds[i - 11:i + 1]) / sum(ns[x] for x in ds[i - 23:i - 11]) - 1)
            linhas.append([d, regiao, "Atividade (IBC)", r4(sa[d]), r4(mm and round(mm, 2)), r4(aa and round(aa, 2)),
                           r4(v12 and round(v12, 2))])
    linhas = sorted((l for l in linhas if l[0] >= INICIO), key=lambda l: (l[2], l[1], l[0]))
    gravar("atividade", ["data", "regiao", "indicador", "indice_sa", "var_mm", "var_aa", "var_12m"], linhas)


# ---------- preços: IPCA, serviços, núcleos e Porto Alegre ----------
def precos():
    ipca, serv = sgs(433), sgs(10844)
    nucleos = [sgs(c) for c in (11427, 27839, 4466, 16122, 28751)]   # EX0, EX3, MS, DP e P55 (os 5 do BCB)
    media = {d: round(sum(n[d] for n in nucleos) / 5, 2) for d in nucleos[0] if all(d in n for n in nucleos)}
    linhas = []
    for nome, s in [("IPCA Brasil", ipca), ("IPCA serviços", serv), ("Média dos núcleos", media)]:
        a12 = acum12(s)
        linhas += [[d, nome, r4(round(s[d], 2)), r4(a12.get(d) and round(a12[d], 2))] for d in s]
    poa = {}
    for tab in (1419, 7060):
        for l in sidra(f"/t/{tab}/n7/4301/v/63,2265/p/all/c315/7169"):
            poa.setdefault(mes(l["Mes (Codigo)"]), {})["63" if l["Variavel (Codigo)"] == "63" else "12m"] = valor(l["Valor"])
    linhas += [[d, "IPCA Porto Alegre", r4(v.get("63")), r4(v.get("12m"))] for d, v in poa.items()]
    gravar("precos", ["data", "serie", "var_mensal", "var_12m"], sorted(l for l in linhas if l[0] >= INICIO))
    gravar("meta", ["ano", "centro", "tolerancia"], [[a, c, t] for a, (c, t) in METAS.items()])


# ---------- juros e câmbio ----------
def dolar_mensal():
    """Dólar PTAX de venda (SGS 1, fechamento diário do Banco Central).

    Meses fechados: média dos fechamentos do mês. Mês corrente: média dos últimos 10 dias úteis com
    fechamento divulgado; a coluna dolar_obs descreve o período dessa média.
    """
    media = sgs(3698)                       # média mensal oficial do BCB (mesma PTAX de venda)
    inicio = date.fromordinal(HOJE.toordinal() - 70)
    dia = sgs(1, inicio.strftime("%d/%m/%Y"))
    meses = {}
    for d in sorted(dia):
        meses.setdefault(d[:8] + "01", []).append(dia[d])
    atual = HOJE.isoformat()[:8] + "01"
    for m, v in meses.items():              # mês fechado (e completo na consulta) que ainda não está na 3698
        if m not in media and inicio.isoformat() < m < atual:
            media[m] = sum(v) / len(v)
    obs = {}
    if atual in meses:
        ult = sorted(dia)[-10:]
        media[atual] = sum(dia[d] for d in ult) / len(ult)
        br = lambda d: f"{d[8:10]}/{d[5:7]}/{d[:4]}"
        obs[atual] = f"média dos últimos {len(ult)} dias úteis, de {br(ult[0])} a {br(ult[-1])}"
    return media, obs


def ipca_esperado_12m():
    """Focus: mediana da expectativa de IPCA para os próximos 12 meses (suavizada), último dado de cada mês."""
    url = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoInflacao12Meses"
           "?$top=20000&$orderby=Data%20asc&$format=json&$select=Data,Mediana&$filter=Indicador%20eq%20'IPCA'"
           "%20and%20Suavizada%20eq%20'S'%20and%20baseCalculo%20eq%200%20and%20Data%20ge%20'2014-01-01'")
    return {r["Data"][:8] + "01": r["Mediana"] for r in baixar(url)["value"]}    # em ordem: fica o último do mês


def juros_cambio():
    selic_dia = {**sgs(432, "01/01/2014", "31/12/2023"), **sgs(432, "01/01/2024")}   # API: até 10 anos por consulta
    selic = {}
    for d in sorted(selic_dia):
        if d <= HOJE.isoformat():
            selic[d[:8] + "01"] = selic_dia[d]                                          # último valor do mês
    esperado = ipca_esperado_12m()
    dolar, obs = dolar_mensal()
    linhas = []
    for d in sorted(set(selic) | set(dolar)):
        if d < INICIO:
            continue
        real = 100 * ((1 + selic[d] / 100) / (1 + esperado[d] / 100) - 1) if d in esperado and d in selic else None
        linhas.append([d, selic.get(d, ""), r4(esperado.get(d)), r4(real), r4(dolar.get(d)), obs.get(d, "")])
    gravar("juros_cambio", ["data", "selic", "ipca_esperado_12m", "juro_real", "dolar", "dolar_obs"], linhas)


# ---------- mercado de trabalho ----------
def trabalho():
    linhas = [[mes(l["Trimestre Movel (Codigo)"]), "Brasil (trimestre móvel)", valor(l["Valor"])]
              for l in sidra("/t/6381/n1/all/v/4099/p/all")]
    for regiao, nivel in [("Brasil", "n1/all"), ("RS", "n3/43")]:
        linhas += [[trimestre(l["Trimestre (Codigo)"]), f"{regiao} (trimestral)", valor(l["Valor"])]
                   for l in sidra(f"/t/4099/{nivel}/v/4099/p/all")]
    gravar("trabalho", ["data", "serie", "desocupacao"], sorted(l for l in linhas if l[0] >= INICIO))


# ---------- PIB ----------
def pib():
    var = {"6564": "var_tri_sa", "6561": "var_interanual", "6562": "var_acum_4t"}
    dados = {}
    for l in sidra("/t/5932/n1/all/v/6564,6561,6562/p/all/c11255/90707"):
        d = dados.setdefault(trimestre(l["Trimestre (Codigo)"]), {"trimestre": l["Trimestre"]})
        d[var[l["Variavel (Codigo)"]]] = valor(l["Valor"])
    gravar("pib", ["data", "trimestre", "var_tri_sa", "var_interanual", "var_acum_4t"],
           [[d, v["trimestre"], v.get("var_tri_sa"), v.get("var_interanual"), v.get("var_acum_4t")]
            for d, v in sorted(dados.items()) if d >= INICIO])


# ---------- expectativas (Focus) ----------
def focus():
    url = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
           "?$top=400&$orderby=Data%20desc&$format=json&$filter=baseCalculo%20eq%200%20and%20(Indicador%20eq%20'IPCA'"
           "%20or%20Indicador%20eq%20'PIB%20Total'%20or%20Indicador%20eq%20'Selic'%20or%20Indicador%20eq%20"
           "'C%C3%A2mbio'%20or%20Indicador%20eq%20'IGP-M')")
    x = baixar(url)["value"]
    ult = max(r["Data"] for r in x)
    anos = {str(HOJE.year + k) for k in range(3)}
    linhas = sorted([r["Indicador"], r["DataReferencia"], r["Data"], r["Mediana"]]
                    for r in x if r["Data"] == ult and r["DataReferencia"] in anos)
    gravar("focus", ["indicador", "ano", "data_pesquisa", "mediana"], linhas)


def main():
    DADOS.mkdir(exist_ok=True)
    for etapa in (atividade, precos, juros_cambio, trabalho, pib, focus):
        etapa()
    print("Coleta concluída em", time.strftime("%d/%m/%Y %H:%M"))


if __name__ == "__main__":
    main()
