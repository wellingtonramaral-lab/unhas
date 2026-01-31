import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
from supabase import create_client

# ======================
# SECRETS
# ======================
SENHA_ADMIN = st.secrets["SENHA_ADMIN"]
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ======================
# FUNÇÕES SUPABASE
# ======================
def listar_agendamentos():
    resp = (
        supabase
        .table("agendamentos")
        .select("id,cliente,data,horario,servico")
        .order("data")
        .order("horario")
        .execute()
    )
    dados = resp.data or []
    df = pd.DataFrame(dados)

    if df.empty:
        return pd.DataFrame(columns=["id", "Cliente", "Data", "Horário", "Serviço"])

    df.rename(columns={
        "cliente": "Cliente",
        "data": "Data",
        "horario": "Horário",
        "servico": "Serviço"
    }, inplace=True)

    df["Data"] = df["Data"].astype(str)
    df["Horário"] = df["Horário"].astype(str)
    return df


def horarios_ocupados(data_escolhida):
    resp = (
        supabase
        .table("agendamentos")
        .select("horario")
        .eq("data", data_escolhida.isoformat())
        .execute()
    )
    return set([r["horario"] for r in (resp.data or [])])


def inserir_agendamento(cliente, data_escolhida, horario, servico):
    payload = {
        "cliente": cliente,
        "data": data_escolhida.isoformat(),
        "horario": horario,
        "servico": servico
    }
    return supabase.table("agendamentos").insert(payload).execute()


def excluir_agendamento(ag_id):
    supabase.table("agendamentos").delete().eq("id", ag_id).execute()


# ======================
# CLIENTE
# ======================
st.subheader("Agende seu horário")

nome = st.text_input("Nome da cliente")
data_atendimento = st.date_input("Data do atendimento", min_value=date.today())

servico = st.selectbox(
    "Tipo de serviço",
    ["Alongamento em Gel", "Alongamento em Fibra de Vidro", "Pedicure"]
)

horarios = ["07:00", "08:30", "10:00", "13:30", "15:00", "16:30", "18:00"]
ocupados = horarios_ocupados(data_atendimento)
disponiveis = [h for h in horarios if h not in ocupados]

st.subheader("Horários disponíveis")

if disponiveis:
    with st.container(height=180):
        horario_escolhido = st.radio(
            "Escolha um horário",
            disponiveis,
            label_visibility="collapsed"
        )
else:
    horario_escolhido = None
    st.warning("Nenhum horário disponível")

# ======================
# CONFIRMAR AGENDAMENTO
# ======================
if st.button("Confirmar Agendamento 💅"):
    if not nome or not horario_escolhido:
        st.error("Preencha todos os campos")
    else:
        resp = inserir_agendamento(nome, data_atendimento, horario_escolhido, servico)

        if getattr(resp, "error", None):
            st.error("Esse horário acabou de ser ocupado. Escolha outro.")
        else:
            mensagem = (
                "Olá! Barbára Vitória, gostaria de confirmar meu agendamento:\n\n"
                f"👩 Cliente: {nome}\n"
                f"📅 Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
                f"⏰ Horário: {horario_escolhido}\n"
                f"💅 Serviço: {servico}\n"
            )

            mensagem_url = urllib.parse.quote(mensagem, safe="")
            link_whatsapp = (
                f"https://api.whatsapp.com/send"
                f"?phone={WHATSAPP_NUMERO}"
                f"&text={mensagem_url}"
            )

            st.success("Agendamento registrado! 💖")

            # Botão confiável no desktop
            st.link_button("📲 Confirmar no WhatsApp", link_whatsapp)

            # Fallback (caso o navegador bloqueie)
            st.caption("Se não abrir, copie o link abaixo e cole no navegador:")
            st.code(link_whatsapp)

            st.rerun()

# ======================
# ÁREA ADMIN
# ======================
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
        data_filtro = st.date_input("Escolha a data", value=date.today(), key="filtro")
        df_admin = df_admin[df_admin["Data"] == str(data_filtro)]

    if df_admin.empty:
        st.info("Nenhum agendamento encontrado.")
    else:
        st.dataframe(df_admin.drop(columns=["id"]), use_container_width=True)

        st.subheader("🗑️ Excluir agendamento")
        opcoes = df_admin.apply(
            lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço"]}',
            axis=1
        ).tolist()

        escolha = st.selectbox("Selecione um agendamento", opcoes)

        if st.button("Excluir ❌"):
            ag_id = int(escolha.split("|")[0].replace("#", "").strip())
            excluir_agendamento(ag_id)
            st.success("Agendamento excluído")
            st.rerun()

    st.subheader("⬇️ Baixar CSV")
    st.download_button(
        "Baixar agendamentos.csv",
        df_admin.drop(columns=["id"]).to_csv(index=False).encode("utf-8"),
        file_name="agendamentos.csv",
        mime="text/csv"
    )

else:
    with st.form("login_admin"):
        senha = st.text_input("Senha da profissional", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        if senha.strip() == SENHA_ADMIN.strip():
            st.session_state.admin_logado = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
