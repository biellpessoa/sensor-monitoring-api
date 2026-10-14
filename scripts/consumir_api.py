"""
Script de consumo via requests dos três endpoints da Sensor Monitoring API.

Uso (com a API rodando):
    python scripts/consumir_api.py
    python scripts/consumir_api.py --tag VT-201 --chamadas 30
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

import requests

parser = argparse.ArgumentParser(description="Consome os endpoints da Sensor Monitoring API")
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--tag", default="TT-101")
parser.add_argument("--chamadas", type=int, default=10,
                    help="Quantidade de chamadas de leitura atual (gera massa p/ observabilidade)")
args = parser.parse_args()

SESSION_ID = f"script-{uuid.uuid4().hex[:8]}"


def get(caminho: str, feature: str, **params):
    headers = {"X-Session-Id": SESSION_ID, "X-Feature": feature}
    r = requests.get(f"{args.url}{caminho}", headers=headers, params=params, timeout=10)
    r.raise_for_status()
    print(f"  -> {r.status_code} | {r.headers.get('X-Response-Time-ms')} ms | "
          f"request_id={r.headers.get('X-Request-Id')}")
    return r.json()


try:
    print(f"Sessão: {SESSION_ID}\n")

    print(f"[1] GET /v1/sensores/{args.tag}/leitura-atual  (x{args.chamadas})")
    for _ in range(args.chamadas):
        leitura = get(f"/v1/sensores/{args.tag}/leitura-atual", "script-leitura-atual")
    print(json.dumps(leitura, indent=2, ensure_ascii=False))

    print(f"\n[2] GET /v1/sensores/{args.tag}/historico?horas=2")
    hist = get(f"/v1/sensores/{args.tag}/historico", "script-historico", horas=2)
    print(f"  pontos recebidos: {hist['pontos_recebidos']}/{hist['pontos_esperados']} "
          f"(completude {hist['completude_pct']}%)")
    print("  últimas 3 leituras:", json.dumps(hist["leituras"][-3:], ensure_ascii=False))

    print("\n[3] GET /v1/observabilidade")
    obs = get("/v1/observabilidade", "script-observabilidade", limite=5)
    print(json.dumps(obs["resumo"], indent=2, ensure_ascii=False))
    print("\n  últimos registros:")
    for reg in obs["registros"]:
        print(f"   {reg['timestamp']} | {reg['endpoint']:<35} | {reg['feature']:<22} | "
              f"{reg['status_code']} | {reg['latencia_ms']} ms")
except requests.ConnectionError:
    sys.exit(f"Não foi possível conectar em {args.url}. A API está rodando? "
             "(uvicorn backend.main:app --port 8000)")
