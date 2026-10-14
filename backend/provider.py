"""
Provider de Sensores - Forzy · Digital Twin.

Simula a camada de dados dos sensores industriais (temperatura, vibração,
pressão etc.). Gera leituras determinísticas por tag + timestamp para que o
histórico seja consistente entre chamadas, e calcula a severidade de cada
leitura com base nos limites operacionais do sensor.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class SensorConfig:
    tag: str
    descricao: str
    unidade: str
    equipamento: str
    base: float          # valor nominal de operação
    amplitude: float     # variação senoidal normal
    ruido: float         # ruído aleatório
    limite_alerta: float
    limite_critico: float
    intervalo_s: int = 60  # periodicidade de amostragem (segundos)


SENSORES: dict[str, SensorConfig] = {
    "TT-101": SensorConfig("TT-101", "Temperatura do mancal do motor", "°C",
                           "Motor Principal M-01", 68.0, 6.0, 2.5, 80.0, 90.0),
    "VT-201": SensorConfig("VT-201", "Vibração da bomba centrífuga", "mm/s",
                           "Bomba B-02", 3.2, 1.1, 0.6, 4.5, 7.1),
    "PT-301": SensorConfig("PT-301", "Pressão da linha de recalque", "bar",
                           "Linha L-03", 6.0, 0.8, 0.3, 7.2, 8.0),
    "FT-401": SensorConfig("FT-401", "Vazão de água de resfriamento", "m³/h",
                           "Torre T-04", 120.0, 12.0, 5.0, 140.0, 155.0),
}


class SensorNaoEncontrado(Exception):
    """Tag de sensor inexistente no provider."""


def _severidade(valor: float, cfg: SensorConfig) -> str:
    if valor >= cfg.limite_critico:
        return "CRITICA"
    if valor >= cfg.limite_alerta:
        return "ALERTA"
    return "NORMAL"


def _valor(cfg: SensorConfig, instante: datetime) -> float:
    """Valor determinístico para (tag, instante) — mesmo instante, mesmo valor."""
    epoch_min = int(instante.timestamp() // cfg.intervalo_s)
    rng = random.Random(f"{cfg.tag}-{epoch_min}")
    onda = math.sin(epoch_min / 45.0) * cfg.amplitude
    pico = cfg.amplitude * 2.2 if rng.random() < 0.04 else 0.0  # eventos raros
    return round(cfg.base + onda + rng.gauss(0, cfg.ruido) + pico, 2)


def _alinhar(instante: datetime, intervalo_s: int) -> datetime:
    ts = int(instante.timestamp()) // intervalo_s * intervalo_s
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _config(tag: str) -> SensorConfig:
    cfg = SENSORES.get(tag.upper())
    if cfg is None:
        raise SensorNaoEncontrado(tag)
    return cfg


def _leitura(cfg: SensorConfig, instante: datetime) -> dict:
    valor = _valor(cfg, instante)
    return {
        "tag": cfg.tag,
        "valor": valor,
        "unidade": cfg.unidade,
        "severidade": _severidade(valor, cfg),
        "timestamp_leitura": instante.isoformat(),
    }


def listar_sensores() -> list[dict]:
    return [
        {
            "tag": c.tag, "descricao": c.descricao, "unidade": c.unidade,
            "equipamento": c.equipamento, "limite_alerta": c.limite_alerta,
            "limite_critico": c.limite_critico, "intervalo_s": c.intervalo_s,
        }
        for c in SENSORES.values()
    ]


def leitura_atual(tag: str) -> dict:
    cfg = _config(tag)
    agora = datetime.now(timezone.utc)
    # Simula atraso de ingestão (0 a ~3 intervalos) para que o indicador
    # de Freshness tenha variação real a ser observada pela Governança.
    atraso = random.choice([0, 0, 0, 0, 0, 1, 1, 2, 3]) * cfg.intervalo_s
    instante = _alinhar(agora - timedelta(seconds=atraso), cfg.intervalo_s)
    leitura = _leitura(cfg, instante)
    leitura["descricao"] = cfg.descricao
    leitura["equipamento"] = cfg.equipamento
    leitura["limite_alerta"] = cfg.limite_alerta
    leitura["limite_critico"] = cfg.limite_critico
    return leitura


def historico(tag: str, horas: int = 6) -> list[dict]:
    cfg = _config(tag)
    fim = _alinhar(datetime.now(timezone.utc), cfg.intervalo_s)
    total = int(horas * 3600 / cfg.intervalo_s)
    pontos = []
    for i in range(total, -1, -1):
        instante = fim - timedelta(seconds=i * cfg.intervalo_s)
        # ~2% de pontos perdidos -> alimenta o indicador de Completude
        if random.Random(f"gap-{cfg.tag}-{int(instante.timestamp())}").random() < 0.02:
            continue
        pontos.append(_leitura(cfg, instante))
    return pontos


def pontos_esperados(tag: str, horas: int) -> int:
    cfg = _config(tag)
    return int(horas * 3600 / cfg.intervalo_s) + 1
