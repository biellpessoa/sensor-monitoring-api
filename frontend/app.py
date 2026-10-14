"""
Interface Streamlit — Forzy · Digital Twin | Sensor Monitoring

Executar (na raiz do projeto, com a API rodando):
    streamlit run frontend/app.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
from api_client import API_URL, SensorApiClient  # noqa: E402

st.set_page_config(page_title="Forzy · Sensor Monitoring", page_icon="📡", layout="wide")

# ------------------------------------------------------------------ estilo
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800&display=swap');
html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }
.stApp { background: radial-gradient(circle at 10% 0%, #1b2440 0%, #0b0f1a 55%); }
.hero { padding: 1.2rem 1.6rem; border-radius: 18px;
        background: linear-gradient(120deg, rgba(56,189,248,.18), rgba(167,139,250,.18));
        border: 1px solid rgba(255,255,255,.08); margin-bottom: 1rem; }
.hero h1 { margin: 0; font-weight: 800; font-size: 2rem;
           background: linear-gradient(90deg,#38bdf8,#a78bfa); -webkit-background-clip: text;
           -webkit-text-fill-color: transparent; }
.hero p { margin: .2rem 0 0; color: #94a3b8; }
.card { padding: 1rem 1.2rem; border-radius: 16px; background: rgba(255,255,255,.04);
        border: 1px solid rgba(255,255,255,.08); transition: transform .2s, border-color .2s; }
.card:hover { transform: translateY(-3px); border-color: rgba(56,189,248,.5); }
.card .lbl { color:#94a3b8; font-size:.85rem; text-transform:uppercase; letter-spacing:.06em; }
.card .val { font-size:2rem; font-weight:800; color:#f1f5f9; }
.sev { display:inline-block; padding:.25rem .8rem; border-radius:999px; font-weight:600; }
.sev-NORMAL  { background:rgba(34,197,94,.15);  color:#4ade80; }
.sev-ALERTA  { background:rgba(234,179,8,.15);  color:#facc15; }
.sev-CRITICA { background:rgba(239,68,68,.18);  color:#f87171; animation:pulse 1.4s infinite; }
@keyframes pulse { 50% { box-shadow:0 0 0 8px rgba(239,68,68,0); } 0% { box-shadow:0 0 0 0 rgba(239,68,68,.5);} }
.ok { color:#4ade80; font-weight:700; } .viol { color:#f87171; font-weight:700; }
</style>
""", unsafe_allow_html=True)

PLOT = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")


def card(rotulo: str, valor: str, extra: str = "") -> None:
    st.markdown(f"<div class='card'><div class='lbl'>{rotulo}</div>"
                f"<div class='val'>{valor}</div>{extra}</div>", unsafe_allow_html=True)


# ----------------------------------------------------------------- sessão
if "session_id" not in st.session_state:
    st.session_state.session_id = f"st-{uuid.uuid4().hex[:12]}"

with st.sidebar:
    st.markdown("### ⚙️ Configuração")
    base_url = st.text_input("URL da API", API_URL)
    st.caption("Headers de contexto enviados em toda chamada:")
    st.code(f"X-Session-Id: {st.session_state.session_id}\nX-Feature: <aba da interface>")
    if st.button("🔄 Nova sessão", width="stretch"):
        st.session_state.session_id = f"st-{uuid.uuid4().hex[:12]}"
        st.rerun()

api = SensorApiClient(base_url, st.session_state.session_id)

st.markdown("<div class='hero'><h1>📡 Forzy · Digital Twin — Sensor Monitoring</h1>"
            "<p>Leitura atual, histórico e observabilidade do provider de Sensores</p></div>",
            unsafe_allow_html=True)

try:
    sensores = api.listar_sensores()
except requests.RequestException:
    st.error(f"Não foi possível conectar à API em **{base_url}**. "
             "Inicie o back-end com `uvicorn backend.main:app --port 8000`.")
    st.stop()

mapa = {f"{s['tag']} — {s['descricao']}": s for s in sensores}
escolha = st.selectbox("Sensor", list(mapa))
sensor = mapa[escolha]
tag = sensor["tag"]

aba_leitura, aba_hist, aba_obs = st.tabs(["🎯 Leitura atual", "📈 Histórico", "🛰️ Observabilidade"])

# ---------------------------------------------------------- leitura atual
with aba_leitura:
    if st.button("Atualizar leitura", key="btn_leitura", type="primary"):
        st.session_state.pop("leitura", None)
    if st.session_state.get("leitura", {}).get("tag") != tag:
        st.session_state.leitura = api.leitura_atual(tag)
    l = st.session_state.leitura

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        card("Valor", f"{l['valor']} {l['unidade']}")
    with c2:
        card("Severidade", "", f"<span class='sev sev-{l['severidade']}'>{l['severidade']}</span>")
    with c3:
        card("Freshness", f"{l['freshness_s']:.0f} s")
    with c4:
        card("Equipamento", f"<span style='font-size:1.1rem'>{l['equipamento']}</span>")

    gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=l["valor"], number={"suffix": f" {l['unidade']}"},
        gauge={"axis": {"range": [0, l["limite_critico"] * 1.25]},
               "bar": {"color": "#38bdf8"},
               "steps": [{"range": [0, l["limite_alerta"]], "color": "rgba(34,197,94,.25)"},
                         {"range": [l["limite_alerta"], l["limite_critico"]], "color": "rgba(234,179,8,.3)"},
                         {"range": [l["limite_critico"], l["limite_critico"] * 1.25], "color": "rgba(239,68,68,.35)"}]}))
    gauge.update_layout(height=300, margin=dict(t=30, b=10), **PLOT)
    st.plotly_chart(gauge, width="stretch")
    st.caption(f"Timestamp da leitura (UTC): {l['timestamp_leitura']}")

# --------------------------------------------------------------- histórico
with aba_hist:
    horas = st.slider("Janela (horas)", 1, 48, 6)
    h = api.historico(tag, horas)
    df = pd.DataFrame(h["leituras"])
    df["timestamp_leitura"] = pd.to_datetime(df["timestamp_leitura"])

    c1, c2, c3 = st.columns(3)
    with c1:
        card("Pontos recebidos", f"{h['pontos_recebidos']}/{h['pontos_esperados']}")
    with c2:
        card("Completude", f"{h['completude_pct']}%")
    with c3:
        card("Leituras fora do normal", str((df["severidade"] != "NORMAL").sum()))

    fig = px.line(df, x="timestamp_leitura", y="valor", labels={"valor": sensor["unidade"],
                  "timestamp_leitura": "Horário (UTC)"})
    fig.update_traces(line_color="#38bdf8")
    fig.add_hline(y=sensor["limite_alerta"], line_dash="dash", line_color="#facc15",
                  annotation_text="Alerta")
    fig.add_hline(y=sensor["limite_critico"], line_dash="dash", line_color="#f87171",
                  annotation_text="Crítico")
    fig.update_layout(height=380, **PLOT)
    st.plotly_chart(fig, width="stretch")
    with st.expander("Tabela do histórico"):
        st.dataframe(df.sort_values("timestamp_leitura", ascending=False),
                     width="stretch", hide_index=True)

# ---------------------------------------------------------- observabilidade
with aba_obs:
    col_a, col_b = st.columns([3, 1])
    with col_a:
        janela = st.select_slider("Janela do resumo", ["Tudo", 5, 15, 60, 240, 1440], "Tudo",
                                  format_func=lambda v: v if v == "Tudo" else f"{v} min")
    with col_b:
        st.write("")
        if st.button("🔁 Gerar 20 chamadas de teste"):
            for _ in range(20):
                api.leitura_atual(tag, feature="teste-carga-interface")
    o = api.observabilidade(limite=1000, janela_min=None if janela == "Tudo" else janela)
    r = o["resumo"]

    st.markdown("#### Metric Contract")
    nomes = {"latencia_p95_ms": "Latência p95 (ms)", "taxa_erro_pct": "Taxa de erro 5xx (%)",
             "conformidade_headers_pct": "Conformidade headers (%)",
             "freshness_s": "Freshness média (s)",
             "freshness_conformidade_pct": "Freshness em conformidade (%)",
             "completude_pct": "Completude média (%)"}
    itens = list(r["contrato"].items())
    for linha in (itens[:3], itens[3:]):
        cols = st.columns(3)
        for col, (k, info) in zip(cols, linha):
            with col:
                cls = "ok" if info["status"] == "OK" else "viol"
                valor = "—" if info["valor"] is None else info["valor"]
                card(nomes[k], str(valor),
                     f"<span class='{cls}'>{info['status']}</span> "
                     f"<span style='color:#64748b'>limiar {info['limiar']}</span>")
        st.write("")

    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1:
        card("Total de chamadas", str(r["total_chamadas"]))
    with c2:
        card("Sessões distintas", str(r["sessoes_distintas"]))
    with c3:
        card("Latência média", f"{r['latencia_ms']['media']} ms")

    regs = pd.DataFrame(o["registros"])
    if not regs.empty:
        regs["timestamp"] = pd.to_datetime(regs["timestamp"])
        regs = regs.sort_values("timestamp")
        g1, g2 = st.columns(2)
        with g1:
            f1 = px.line(regs, x="timestamp", y="latencia_ms", color="endpoint",
                         title="Latência por chamada (ms)")
            f1.add_hline(y=300, line_dash="dash", line_color="#f87171")
            f1.update_layout(height=340, legend=dict(orientation="h", y=-0.3), **PLOT)
            st.plotly_chart(f1, width="stretch")
        with g2:
            feat = regs["feature"].fillna("(ausente)").value_counts().reset_index()
            f2 = px.bar(feat, x="count", y="feature", orientation="h",
                        title="Chamadas por X-Feature", color_discrete_sequence=["#a78bfa"])
            f2.update_layout(height=340, **PLOT)
            st.plotly_chart(f2, width="stretch")

        g3, g4 = st.columns(2)
        fr = regs.dropna(subset=["freshness_s"])
        with g3:
            if not fr.empty:
                f3 = px.scatter(fr, x="timestamp", y="freshness_s", color="severidade",
                                title="Freshness da leitura atual (s)",
                                color_discrete_map={"NORMAL": "#4ade80", "ALERTA": "#facc15",
                                                    "CRITICA": "#f87171"})
                f3.add_hline(y=120, line_dash="dash", line_color="#f87171")
                f3.update_layout(height=320, **PLOT)
                st.plotly_chart(f3, width="stretch")
        with g4:
            sev = r["distribuicao_severidade"]
            if sev:
                f4 = px.pie(names=list(sev), values=list(sev.values()), hole=.55,
                            title="Distribuição de severidade", color=list(sev),
                            color_discrete_map={"NORMAL": "#4ade80", "ALERTA": "#facc15",
                                                "CRITICA": "#f87171"})
                f4.update_layout(height=320, **PLOT)
                st.plotly_chart(f4, width="stretch")

        st.markdown("#### Registros de chamadas")
        st.dataframe(regs.sort_values("timestamp", ascending=False)[
            ["timestamp", "metodo", "rota", "session_id", "feature", "status_code",
             "latencia_ms", "freshness_s", "completude_pct", "severidade", "contrato_ok"]],
            width="stretch", hide_index=True)
        st.download_button("⬇️ Exportar registros (CSV)", regs.to_csv(index=False).encode(),
                           "observabilidade.csv", "text/csv")
    with st.expander("JSON bruto do resumo"):
        st.json(r)
