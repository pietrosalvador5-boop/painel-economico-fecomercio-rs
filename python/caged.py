"""Painel Econômico Fecomércio-RS - saldo do Novo CAGED (Brasil e RS).

Baixa os microdados de movimentação do Novo CAGED (arquivo CAGEDMOV do mês, no FTP do Ministério do Trabalho e
Emprego) e soma admissões, desligamentos e saldo do Brasil e do RS (UF 43), no total e por grande setor
(seção CNAE: agropecuária A; indústria B-E; construção F; comércio G; serviços H-U). É o mesmo número divulgado pelo MTE
no mês (declarações no prazo; ajustes de declarações fora do prazo não entram). Só baixa os meses que ainda não
estão em dados/caged.csv, então a primeira execução (desde jan/2020) demora e as seguintes levam 2 minutos.

Uso: python3 python/caged.py
Precisa de: pip3 install py7zr
"""
import csv
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

import py7zr

PASTA = Path(__file__).resolve().parent.parent
ARQ = PASTA / "dados" / "caged.csv"
FTP = "ftp://ftp.mtps.gov.br/pdet/microdados/NOVO%20CAGED"
INICIO = (2020, 1)
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


def ler():
    if not ARQ.exists():
        return []
    with open(ARQ, encoding="utf-8") as f:
        return [l for l in csv.reader(f)][1:]


def mes(a, m, tmp):
    """Admissões e desligamentos do Brasil e do RS no mês, ou None se o arquivo ainda não saiu."""
    url = f"{FTP}/{a}/{a}{m:02d}/CAGEDMOV{a}{m:02d}.7z"
    zip_ = tmp / "mov.7z"
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
        i_uf, i_sec, i_s = cab.index("uf"), cab.index("seção"), cab.index("saldomovimentação")
        for l in f:
            c = l.split(";", i_s + 1)
            alvo = adm if c[i_s] == "1" else desl
            setor = SETOR.get(c[i_sec], "Não identificado")
            alvo["Brasil", "Total"] += 1
            alvo["Brasil", setor] += 1
            if c[i_uf] == "43":
                alvo["RS", "Total"] += 1
                alvo["RS", setor] += 1
    shutil.rmtree(tmp / "x")
    zip_.unlink()
    return [[f"{a}-{m:02d}-01", r, s, adm[r, s], desl[r, s], adm[r, s] - desl[r, s]]
            for r in ("Brasil", "RS") for s in SETORES]


def main():
    linhas = ler()
    feitos = {l[0] for l in linhas}
    ARQ.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        for a, m in meses_ate_hoje():
            if f"{a}-{m:02d}-01" in feitos:
                continue
            novas = mes(a, m, Path(t))
            if novas is None:
                print(f"CAGED {m:02d}/{a}: ainda não divulgado")
                break
            linhas += novas
            linhas.sort()
            with open(ARQ, "w", encoding="utf-8", newline="") as f:     # grava a cada mês (pode retomar)
                w = csv.writer(f)
                w.writerow(COLUNAS)
                w.writerows(linhas)
            print(f"CAGED {m:02d}/{a}: Brasil {novas[0][5]:+,}, RS {novas[6][5]:+,}".replace(",", "."))
    print(f"caged          {len(linhas):5d} linhas")


if __name__ == "__main__":
    main()
