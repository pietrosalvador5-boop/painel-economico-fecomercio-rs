"""Painel Econômico Fecomércio-RS - saldo do Novo CAGED com ajustes (Brasil e RS).

Baixa os microdados do Novo CAGED (FTP do Ministério do Trabalho e Emprego). Cada mês divulgado tem três arquivos:
  CAGEDMOV: movimentações declaradas no prazo, todas da competência do mês;
  CAGEDFOR: declarações entregues fora do prazo naquele mês, de competências anteriores;
  CAGEDEXC: exclusões de movimentações declaradas antes.
O saldo de cada competência é MOV + FOR − EXC (somando os arquivos de todos os meses já divulgados), que é a série
com ajustes do MTE. O último mês ainda não recebeu ajustes e fica igual ao número divulgado no mês.
Soma admissões e desligamentos do Brasil e do RS (UF 43), no total e por grande setor (seção CNAE: agropecuária A;
indústria B-E; construção F; comércio G; serviços H-U).

dados/caged_bruto.csv guarda o que veio de cada arquivo (por competência); só baixa os arquivos que faltam
(MOV cerca de 50 MB e 1,5 min; FOR e EXC menos de 1 MB). dados/caged.csv é o resultado usado pela página.

Uso: python3 python/caged.py
Precisa de: pip3 install py7zr
"""
import csv
import shutil
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import py7zr

PASTA = Path(__file__).resolve().parent.parent
BRUTO = PASTA / "dados" / "caged_bruto.csv"
ARQ = PASTA / "dados" / "caged.csv"
FTP = "ftp://ftp.mtps.gov.br/pdet/microdados/NOVO%20CAGED"
INICIO = (2020, 1)
TIPOS = ("MOV", "FOR", "EXC")
COL_BRUTO = ["arquivo", "tipo", "data", "regiao", "setor", "admissoes", "desligamentos"]
COLUNAS = ["data", "regiao", "setor", "admissoes", "desligamentos", "saldo"]
SETOR = {**{"A": "Agropecuária", "F": "Construção", "G": "Comércio"},
         **{c: "Indústria" for c in "BCDE"}, **{c: "Serviços" for c in "HIJKLMNOPQRSTU"}}
SETORES = ["Total", "Agropecuária", "Indústria", "Construção", "Comércio", "Serviços"]


def meses_ate_hoje():
    a, m = INICIO
    hoje = date.today()
    while (a, m) < (hoje.year, hoje.month):
        yield a, m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def ler(arq):
    if not arq.exists():
        return []
    with open(arq, encoding="utf-8") as f:
        return list(csv.reader(f))[1:]


def gravar(arq, colunas, linhas):
    with open(arq, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(colunas)
        w.writerows(linhas)


def arquivo(a, m, tipo):
    """Admissões e desligamentos por competência, região e setor de um arquivo; None se ainda não saiu."""
    url = f"{FTP}/{a}/{a}{m:02d}/CAGED{tipo}{a}{m:02d}.7z"
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        zip_ = tmp / "arq.7z"
        for _ in range(3):
            r = subprocess.run(["curl", "-s", "-f", "-m", "900", "-o", str(zip_), url])
            if r.returncode == 0:
                break
            if r.returncode in (9, 19, 78):     # arquivo não existe no FTP (mês ainda não divulgado)
                return None
        else:
            raise RuntimeError(f"Falha ao baixar {url}")
        with py7zr.SevenZipFile(zip_) as z:
            z.extractall(tmp / "x")
        txt = next((tmp / "x").glob("*.txt"))
        adm, desl = Counter(), Counter()
        with open(txt, encoding="utf-8", errors="replace") as f:
            cab = next(f).rstrip("\n").split(";")
            i_c, i_uf, i_sec, i_s = (cab.index(c) for c in ("competênciamov", "uf", "seção", "saldomovimentação"))
            for l in f:
                c = l.split(";")
                alvo = adm if c[i_s] == "1" else desl
                setor = SETOR.get(c[i_sec], "Não identificado")
                regioes = ("Brasil", "RS") if c[i_uf] == "43" else ("Brasil",)
                for reg in regioes:
                    alvo[c[i_c], reg, "Total"] += 1
                    alvo[c[i_c], reg, setor] += 1
        shutil.rmtree(tmp / "x")
    chaves = sorted(set(adm) | set(desl))
    return [[f"{a}{m:02d}", tipo, f"{k[0][:4]}-{k[0][4:]}-01", k[1], k[2], adm[k], desl[k]]
            for k in chaves if k[2] in SETORES]


def consolidar(bruto):
    """MOV + FOR − EXC por competência."""
    adm, desl = Counter(), Counter()
    for _, tipo, d, reg, setor, a, dl in bruto:
        sinal = -1 if tipo == "EXC" else 1
        adm[d, reg, setor] += sinal * int(a)
        desl[d, reg, setor] += sinal * int(dl)
    meses_mov = {l[2] for l in bruto if l[1] == "MOV"}
    linhas = [[d, reg, setor, adm[d, reg, setor], desl[d, reg, setor], adm[d, reg, setor] - desl[d, reg, setor]]
              for d, reg, setor in sorted(set(adm) | set(desl)) if d in meses_mov]
    gravar(ARQ, COLUNAS, linhas)
    print(f"caged          {len(linhas):5d} linhas")


def main(paralelo=1):
    ARQ.parent.mkdir(exist_ok=True)
    bruto = ler(BRUTO)
    feitos = {(l[0], l[1]) for l in bruto}
    pend = [(a, m, t) for a, m in meses_ate_hoje() for t in TIPOS if (f"{a}{m:02d}", t) not in feitos]
    with ThreadPoolExecutor(paralelo) as ex:
        for (a, m, t), novas in zip(pend, ex.map(lambda x: arquivo(*x), pend)):
            if novas is None:
                print(f"CAGED{t} {m:02d}/{a}: ainda não divulgado")
                continue
            bruto += novas
            gravar(BRUTO, COL_BRUTO, sorted(bruto))     # grava a cada arquivo (pode retomar)
            print(f"CAGED{t} {m:02d}/{a}: {len(novas)} linhas", flush=True)
    consolidar(bruto)


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
