"""
Camada de observabilidade da Sensor Monitoring API.

Cada requisição recebida gera um registro persistido em SQLite contendo os
metadados definidos no Metric Contract da disciplina de Governança em IA:

  - request_id, timestamp (UTC), método, rota, tag do sensor
  - headers de contexto: X-Session-Id e X-Feature
  - status HTTP e latência (ms)
  - métricas de qualidade de dado: freshness (s), completude (%), severidade
  - conformidade com o contrato (headers obrigatórios presentes?)
"""
from __future__ import annotations

import sqlite3
import statistics
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "observabilidade.db"
_lock = threading.Lock()

# Limiares do Metric Contract (ver documento de Governança)
LIMIARES = {
    "latencia_p95_ms": 300.0,
    "taxa_erro_pct": 1.0,
    "conformidade_headers_pct": 99.0,
    "freshness_s": 120.0,
    "freshness_conformidade_pct": 90.0,
    "completude_pct": 95.0,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chamadas (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id       TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    metodo           TEXT NOT NULL,
    rota             TEXT NOT NULL,
    endpoint         TEXT,
    tag              TEXT,
    session_id       TEXT,
    feature          TEXT,
    status_code      INTEGER NOT NULL,
    latencia_ms      REAL NOT NULL,
    freshness_s      REAL,
    completude_pct   REAL,
    severidade       TEXT,
    contrato_ok      INTEGER NOT NULL,
    cliente          TEXT,
    user_agent       TEXT
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _conn() as conn:
        conn.executescript(_SCHEMA)


def registrar(registro: dict) -> None:
    colunas = ", ".join(registro.keys())
    marcadores = ", ".join("?" for _ in registro)
    with _lock, _conn() as conn:
        conn.execute(
            f"INSERT INTO chamadas ({colunas}) VALUES ({marcadores})",
            tuple(registro.values()),
        )


def listar(limite: int = 200, endpoint: str | None = None,
           feature: str | None = None, session_id: str | None = None) -> list[dict]:
    sql = "SELECT * FROM chamadas WHERE 1=1"
    params: list = []
    if endpoint:
        sql += " AND endpoint = ?"
        params.append(endpoint)
    if feature:
        sql += " AND feature = ?"
        params.append(feature)
    if session_id:
        sql += " AND session_id = ?"
        params.append(session_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    with _lock, _conn() as conn:
        linhas = conn.execute(sql, params).fetchall()
    return [dict(l) | {"contrato_ok": bool(l["contrato_ok"])} for l in linhas]


def limpar() -> int:
    with _lock, _conn() as conn:
        n = conn.execute("DELETE FROM chamadas").rowcount
    return n


def _percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    if len(valores) == 1:
        return round(valores[0], 2)
    return round(statistics.quantiles(valores, n=100, method="inclusive")[int(p) - 1], 2)


def _status(valor: float | None, limiar: float, maior_melhor: bool) -> str:
    if valor is None:
        return "SEM_DADOS"
    ok = valor >= limiar if maior_melhor else valor <= limiar
    return "OK" if ok else "VIOLADO"


def resumo(janela_min: int | None = None) -> dict:
    """Agrega os registros e avalia o cumprimento do Metric Contract."""
    sql = "SELECT * FROM chamadas"
    params: list = []
    if janela_min:
        corte = (datetime.now(timezone.utc) - timedelta(minutes=janela_min)).isoformat()
        sql += " WHERE timestamp >= ?"
        params.append(corte)
    with _lock, _conn() as conn:
        linhas = [dict(l) for l in conn.execute(sql, params).fetchall()]

    total = len(linhas)
    lat = [l["latencia_ms"] for l in linhas]
    erros = [l for l in linhas if l["status_code"] >= 500]
    erros_cliente = [l for l in linhas if 400 <= l["status_code"] < 500]
    conformes = [l for l in linhas if l["contrato_ok"]]
    fresh = [l["freshness_s"] for l in linhas if l["freshness_s"] is not None]
    compl = [l["completude_pct"] for l in linhas if l["completude_pct"] is not None]
    sev = Counter(l["severidade"] for l in linhas if l["severidade"])

    p95 = _percentil(lat, 95)
    taxa_erro = round(len(erros) / total * 100, 2) if total else None
    conformidade = round(len(conformes) / total * 100, 2) if total else None
    fresh_med = round(statistics.mean(fresh), 2) if fresh else None
    fresh_conf = (round(sum(f <= LIMIARES["freshness_s"] for f in fresh) / len(fresh) * 100, 2)
                  if fresh else None)
    compl_med = round(statistics.mean(compl), 2) if compl else None

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "janela_min": janela_min,
        "total_chamadas": total,
        "sessoes_distintas": len({l["session_id"] for l in linhas if l["session_id"]}),
        "latencia_ms": {
            "media": round(statistics.mean(lat), 2) if lat else None,
            "p50": _percentil(lat, 50),
            "p95": p95,
            "max": round(max(lat), 2) if lat else None,
        },
        "taxa_erro_5xx_pct": taxa_erro,
        "taxa_erro_4xx_pct": round(len(erros_cliente) / total * 100, 2) if total else None,
        "conformidade_headers_pct": conformidade,
        "freshness_media_s": fresh_med,
        "freshness_max_s": max(fresh) if fresh else None,
        "freshness_conformidade_pct": fresh_conf,
        "completude_media_pct": compl_med,
        "chamadas_por_endpoint": dict(Counter(l["endpoint"] for l in linhas)),
        "chamadas_por_feature": dict(Counter(l["feature"] or "(ausente)" for l in linhas)),
        "distribuicao_severidade": dict(sev),
        "contrato": {
            "latencia_p95_ms": {"valor": p95, "limiar": LIMIARES["latencia_p95_ms"],
                                "status": _status(p95, LIMIARES["latencia_p95_ms"], False)},
            "taxa_erro_pct": {"valor": taxa_erro, "limiar": LIMIARES["taxa_erro_pct"],
                              "status": _status(taxa_erro, LIMIARES["taxa_erro_pct"], False)},
            "conformidade_headers_pct": {"valor": conformidade,
                                         "limiar": LIMIARES["conformidade_headers_pct"],
                                         "status": _status(conformidade, LIMIARES["conformidade_headers_pct"], True)},
            "freshness_s": {"valor": fresh_med, "limiar": LIMIARES["freshness_s"],
                            "status": _status(fresh_med, LIMIARES["freshness_s"], False)},
            "freshness_conformidade_pct": {"valor": fresh_conf,
                                           "limiar": LIMIARES["freshness_conformidade_pct"],
                                           "status": _status(fresh_conf, LIMIARES["freshness_conformidade_pct"], True)},
            "completude_pct": {"valor": compl_med, "limiar": LIMIARES["completude_pct"],
                               "status": _status(compl_med, LIMIARES["completude_pct"], True)},
        },
    }
