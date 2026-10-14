"""
Sensor Monitoring API — Forzy · Digital Twin
Checkpoint integrado Governança em IA + Front-end.

Executar (na raiz do projeto):
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from . import observability as obs
from . import provider

HEADERS_OBRIGATORIOS = ("x-session-id", "x-feature")
ROTAS_OBSERVADAS = ("/v1/",)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    obs.init_db()
    yield


app = FastAPI(
    title="Sensor Monitoring API — Forzy Digital Twin",
    description=(
        "API do provider de Sensores com observabilidade por chamada. "
        "Envie os headers de contexto **X-Session-Id** e **X-Feature** em toda requisição."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["X-Request-Id", "X-Response-Time-ms"])


@app.middleware("http")
async def middleware_observabilidade(request: Request, call_next):
    """Mede latência e registra os metadados de cada chamada (Metric Contract)."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.metricas = {}
    inicio = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    finally:
        latencia_ms = round((time.perf_counter() - inicio) * 1000, 3)
        if request.url.path.startswith(ROTAS_OBSERVADAS):
            rota = request.scope.get("route")
            session_id = request.headers.get("x-session-id")
            feature = request.headers.get("x-feature")
            metricas = getattr(request.state, "metricas", {})
            obs.registrar({
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metodo": request.method,
                "rota": request.url.path,
                "endpoint": getattr(rota, "path", request.url.path),
                "tag": request.path_params.get("tag", "").upper() or None,
                "session_id": session_id,
                "feature": feature,
                "status_code": status_code,
                "latencia_ms": latencia_ms,
                "freshness_s": metricas.get("freshness_s"),
                "completude_pct": metricas.get("completude_pct"),
                "severidade": metricas.get("severidade"),
                "contrato_ok": int(all(request.headers.get(h) for h in HEADERS_OBRIGATORIOS)),
                "cliente": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            })
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Response-Time-ms"] = str(latencia_ms)
    return response


# ---------------------------------------------------------------- Sensores
@app.get("/", tags=["Status"])
def raiz():
    return {"servico": "Sensor Monitoring API", "status": "online", "docs": "/docs"}


@app.get("/v1/sensores", tags=["Sensores"], summary="Lista sensores disponíveis")
def listar_sensores():
    return provider.listar_sensores()


@app.get("/v1/sensores/{tag}/leitura-atual", tags=["Sensores"],
         summary="Leitura atual do sensor com severidade")
def leitura_atual(tag: str, request: Request):
    try:
        leitura = provider.leitura_atual(tag)
    except provider.SensorNaoEncontrado:
        raise HTTPException(404, f"Sensor '{tag}' não encontrado")

    ts = datetime.fromisoformat(leitura["timestamp_leitura"])
    freshness = round((datetime.now(timezone.utc) - ts).total_seconds(), 2)
    leitura["freshness_s"] = freshness
    request.state.metricas = {"freshness_s": freshness, "severidade": leitura["severidade"]}
    return leitura


@app.get("/v1/sensores/{tag}/historico", tags=["Sensores"],
         summary="Histórico de leituras do sensor")
def historico(tag: str, request: Request,
              horas: int = Query(6, ge=1, le=48, description="Janela em horas")):
    try:
        pontos = provider.historico(tag, horas)
        esperados = provider.pontos_esperados(tag, horas)
    except provider.SensorNaoEncontrado:
        raise HTTPException(404, f"Sensor '{tag}' não encontrado")

    completude = round(len(pontos) / esperados * 100, 2)
    request.state.metricas = {"completude_pct": completude}
    return {
        "tag": tag.upper(),
        "janela_horas": horas,
        "pontos_esperados": esperados,
        "pontos_recebidos": len(pontos),
        "completude_pct": completude,
        "leituras": pontos,
    }


# ---------------------------------------------------------- Observabilidade
@app.get("/v1/observabilidade", tags=["Observabilidade"],
         summary="Registros de chamadas + resumo do Metric Contract")
def observabilidade(
    limite: int = Query(200, ge=1, le=5000),
    endpoint: str | None = None,
    feature: str | None = None,
    session_id: str | None = None,
    janela_min: int | None = Query(None, ge=1, description="Resumo apenas dos últimos N minutos"),
):
    return {
        "resumo": obs.resumo(janela_min),
        "registros": obs.listar(limite, endpoint, feature, session_id),
    }


@app.delete("/v1/observabilidade", tags=["Observabilidade"],
            summary="Limpa os registros (uso em ambiente de teste)")
def limpar_observabilidade():
    return {"removidos": obs.limpar()}
