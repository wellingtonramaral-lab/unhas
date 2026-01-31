import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
from supabase import create_client

# ===== SECRETS =====
SENHA_ADMIN = st.secrets["SENHA_ADMIN"]           # "Maite04!"
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ===== FUNÇÕES DB =====
def listar_agendamentos():
    resp = (
        supabase
        .table("agendamentos")
        .select("id,cliente,data,horario,servico")
        .order("data")
        .order("horario")
        .execute()
    )
    rows = resp.data or []
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["id","Cliente","Data","Horário","Serviço"])
    df.rename(columns={
        "cliente":"Cliente","data":"Data","horario":"Horário","servico":"Serviço"
    }, inplace=True)
    df["Data"] = df["Data"].astype(str)
    df["Horário"] = df["Horário"].astype(str)
    return df

def horarios_ocupados_para_data(d: date):
    resp = (
        supabase
        .table("agendamentos")
        .select("horario")
        .eq("data", d.isoformat())
        .execute()
    )
    return set([r["horario"] for r in (resp.data or [])])

def inserir_agendamento(cliente, d: date, horario, servico):
    payload = {"cliente": cliente, "data": d.isoformat(), "horario": horario, "servico": servico}
    return supabase.table("agendamentos").insert(payload).execute()

def excluir_por_id(ag_id: int):
    return supabase.table("agendamentos").delete().eq("id", ag_id).execute()

# ===== CLIENTE =====
st.subheader("Agende seu horário")

nome = st.text_input("Nome da cliente")
data_atendimento = st.date_input("Data do atendimento", min_value=date.today())
servico = st.selectbox(
    "Tipo de serviço",
    ["Alongamento em Gel", "Alongamento em Fibra de Vidro", "Pedicure"]
)

horarios = ["07:00","08:30","10:00","13:30","15:00","16:30","18:00"]
ocupados = horarios_ocupados_para_data(data_atendimento)
disponiveis = [h for h in horarios if h not in ocupados]

st.subheader("Horários disponíveis")
if disponiveis:
    with st.container(height=180):
        horario_escolhido = st.radio("Escolha um horário", disponiveis, label_visibility="collapsed")
else:
    horario_escolhido = None
    st.warning("Nenhum horário disponível")

if st.button("Confirmar Agendamento 💅"):
    ok = True
    if not nome or not horario_escolhido:
        st.error("Preencha todos os campos")
        ok = False

    if ok:
        try:
            inserir_agendamento(nome, data_atendimento, horario_escolhido, servico)
        except Exception:
            st.error("Esse horário acabou de ser ocupado. Escolha outro.")
            ok = False

    if ok:
        mensagem = f"""Olá! Barbára Vitória Gostaria de confirmar meu agendamento:

👩 Cliente: {nome}
📅 Data: {data_atendimento}
⏰ Horário: {horario_escolhido}
💅 Serviço: {servico}
"""
        link_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={urllib.parse.quote(mensagem)}"
        st.success("Agendamento registrado! 💖")
        st.markdown(
            f"""
            <a href="{link_whatsapp}" target="_blank">
              <button style="
                background-color:#25D366;color:white;padding:12px 20px;
                border:none;border-radius:8px;font-size:16px;cursor:pointer;">
                📲 Confirmar no WhatsApp
              </button>
            </a>
            """,
            unsafe_allow_html=True
        )
        st.rerun()

# ===== ADMIN =====
st.divider()
st.subheader("Área administrativa 🔐")

if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False

def sair_admin():
    st.session_state.admin_logado = False
    st.rerun()

if st.session_state.admin_logado:
    st.success("Acesso liberado ✅")
    if st.button("Sair"):
        sair_admin()

    df_admin = listar_agendamentos()
    st.subheader("📋 Agendamentos")

    filtrar = st.checkbox("Filtrar por data")
    if filtrar:
        data_filtro = st.date_input("Escolha a data", value=date.today(), key="data_filtro")
        df_filtrado = df_admin[df_admin["Data"] == str(data_filtro)]
    else:
        df_filtrado = df_admin

    if df_filtrado.empty:
        st.info("Nenhum agendamento encontrado.")
    else:
        st.dataframe(df_filtrado.drop(columns=["id"]), use_container_width=True)

        st.subheader("🗑️ Excluir um agendamento")
        opcoes = df_filtrado.apply(
            lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço"]}',
            axis=1
        ).tolist()

        escolha = st.selectbox("Selecione", opcoes)
        if st.button("Excluir agendamento selecionado ❌"):
            ag_id = int(escolha.split("|")[0].replace("#","").strip())
            excluir_por_id(ag_id)
            st.success("Agendamento excluído ✅")
            st.rerun()

    st.subheader("⬇️ Baixar CSV")
    st.download_button(
        label="Baixar agendamentos.csv",
        data=df_admin.drop(columns=["id"]).to_csv(index=False).encode("utf-8"),
        file_name="agendamentos.csv",
        mime="text/csv"
    )

else:
    with st.form("login_admin", clear_on_submit=False):
        senha_digitada = st.text_input("Senha da profissional", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        if senha_digitada.strip() == SENHA_ADMIN.strip():
            st.session_state.admin_logado = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
