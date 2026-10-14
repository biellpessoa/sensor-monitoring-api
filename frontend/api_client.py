"""
Cliente HTTP (requests) da Sensor Monitoring API.

Toda chamada envia os headers de contexto exigidos pelo Metric Contract:
    X-Session-Id -> identifica a sessão do usuário no front-end
    X-Feature    -> identifica a funcionalidade da interface que originou a chamada
"""
from __future__ import annotations

import os
import uuid

import requests

API_URL = os.getenv("SENSOR_API_URL", "http://127.0.0.1:8000")
TIMEOUT = 10


class SensorApiClient:
    def __init__(self, base_url: str = API_URL, session_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        self.http = requests.Session()

    def _get(self, caminho: str, feature: str, **params) -> dict | list:
        headers = {"X-Session-Id": self.session_id, "X-Feature": feature}
        resp = self.http.get(f"{self.base_url}{caminho}", headers=headers,
                             params={k: v for k, v in params.items() if v is not None},
                             timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def listar_sensores(self, feature: str = "lista-sensores") -> list[dict]:
        return self._get("/v1/sensores", feature)

    def leitura_atual(self, tag: str, feature: str = "painel-leitura-atual") -> dict:
        return self._get(f"/v1/sensores/{tag}/leitura-atual", feature)

    def historico(self, tag: str, horas: int = 6, feature: str = "grafico-historico") -> dict:
        return self._get(f"/v1/sensores/{tag}/historico", feature, horas=horas)

    def observabilidade(self, limite: int = 200, janela_min: int | None = None,
                        feature: str = "relatorio-observabilidade") -> dict:
        return self._get("/v1/observabilidade", feature, limite=limite, janela_min=janela_min)
