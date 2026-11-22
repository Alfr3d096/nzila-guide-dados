#!/usr/bin/env python3
"""Gera / actualiza o manifest.json do GitHub Pages do Nzila Guide.

Corre-se NA PASTA DO REPOSITÓRIO nzila-guide-dados (a que o GitHub Pages serve):

    python tools/gerar_manifest.py --pasta .

Lê os ficheiros REAIS que existem na pasta (dados.json, traducoes.json),
valida-os, calcula SHA-256 e tamanho de cada um e escreve manifest.json.

 • Idempotente: se nada mudou (mesmos hashes e mesmo bloco "app"), o ficheiro
   não é reescrito (a versão e a data de publicação mantêm-se). Por isso pode
   correr em cada push (GitHub Action) sem criar commits inúteis.
 • Preserva o bloco "app" já existente; só o altera com as opções --min-build-*,
   --ultima-*, --nota.
 • --verificar: não escreve; sai com código 1 se o manifesto estiver
   desactualizado (útil em CI).

Formato: ver lib/core/updates/update_manifest.dart.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

SCHEMA = 1
# id -> (ficheiro, obrigatório)
FICHEIROS = {
    "dados": ("dados.json", True),
    "traducoes": ("traducoes.json", False),
}


class Erro(Exception):
    pass


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def validar(id_, j):
    """Validação mínima (a app volta a validar tudo antes de importar)."""
    if not isinstance(j, dict) or not str(j.get("versao", "")).strip():
        raise Erro(f"{id_}: falta o campo 'versao'")
    if id_ == "dados":
        d = j.get("dados")
        if not isinstance(d, dict):
            raise Erro("dados.json: falta o objecto 'dados'")
        for t in ("provincias", "municipios", "bairros"):
            if not isinstance(d.get(t), list) or not d[t]:
                raise Erro(f"dados.json: a tabela '{t}' está vazia ou em falta")
    if id_ == "traducoes":
        t = j.get("traducoes")
        if not isinstance(t, list) or not t:
            raise Erro("traducoes.json: lista 'traducoes' vazia ou em falta")


def construir(pasta, antigo, args, agora):
    ficheiros = []
    for id_, (nome, obrigatorio) in FICHEIROS.items():
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho):
            if obrigatorio:
                raise Erro(f"ficheiro obrigatório em falta: {nome}")
            continue
        with open(caminho, "rb") as f:
            raw = f.read()
        try:
            j = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise Erro(f"{nome} não é JSON UTF-8 válido: {e}")
        validar(id_, j)
        ficheiros.append({
            "id": id_,
            "tipo": id_,
            "caminho": nome,
            "sha256": sha256_bytes(raw),
            "tamanho": len(raw),
            "obrigatorio": obrigatorio,
            "versao": str(j["versao"]),
        })

    app = dict(antigo.get("app") or {})
    app.setdefault("min_build_compativel", 0)
    app.setdefault("min_build_obrigatoria", 0)
    app.setdefault("notas", [])
    if args.min_build_compativel is not None:
        app["min_build_compativel"] = args.min_build_compativel
    if args.min_build_obrigatoria is not None:
        app["min_build_obrigatoria"] = args.min_build_obrigatoria
    if args.ultima_build is not None:
        app["ultima_build"] = args.ultima_build
    if args.ultima_versao_nome is not None:
        app["ultima_versao_nome"] = args.ultima_versao_nome
    if args.nota:
        app["notas"] = list(args.nota)

    novo = {"schema": SCHEMA, "app": app, "ficheiros": ficheiros}
    # Nada mudou? mantém versão e data.
    if (antigo.get("schema") == SCHEMA
            and antigo.get("app") == app
            and antigo.get("ficheiros") == ficheiros
            and antigo.get("versao") and antigo.get("publicado_em")):
        novo["versao"] = antigo["versao"]
        novo["publicado_em"] = antigo["publicado_em"]
        return novo, False
    novo["versao"] = agora.strftime("%Y%m%d-%H%M")
    novo["publicado_em"] = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    return novo, True


def serializar(m):
    ordem = {"schema": m["schema"], "versao": m["versao"],
             "publicado_em": m["publicado_em"], "app": m["app"],
             "ficheiros": m["ficheiros"]}
    return json.dumps(ordem, indent=2, ensure_ascii=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", default=".", help="pasta do repositório GitHub Pages")
    ap.add_argument("--min-build-compativel", type=int)
    ap.add_argument("--min-build-obrigatoria", type=int)
    ap.add_argument("--ultima-build", type=int)
    ap.add_argument("--ultima-versao-nome")
    ap.add_argument("--nota", action="append", help="nota de versão (repetível)")
    ap.add_argument("--verificar", action="store_true")
    args = ap.parse_args(argv)

    destino = os.path.join(args.pasta, "manifest.json")
    antigo = {}
    if os.path.isfile(destino):
        try:
            with open(destino, encoding="utf-8") as f:
                antigo = json.load(f)
        except ValueError:
            antigo = {}
    try:
        novo, mudou = construir(args.pasta, antigo, args,
                                datetime.datetime.now(datetime.timezone.utc))
    except Erro as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2

    if args.verificar:
        if mudou:
            print("manifest.json DESACTUALIZADO", file=sys.stderr)
            return 1
        print("manifest.json em dia")
        return 0
    if not mudou:
        print("manifest.json já está em dia; nada a fazer")
        return 0
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write(serializar(novo))
    print(f"manifest.json escrito (versão {novo['versao']}):")
    for fi in novo["ficheiros"]:
        print(f"  {fi['caminho']:<16} {fi['tamanho']:>9} B  sha256={fi['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
