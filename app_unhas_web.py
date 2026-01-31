import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
import base64
from supabase import create_client

# ======================
# SECRETS
# ======================
SENHA_ADMIN = st.secrets["SENHA_ADMIN"]
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]  # só números: 55 + DDD + número
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ======================
# CONFIG STREAMLIT
# ======================
st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ======================
# CATÁLOGO PDF
# ======================
CATALOGO_PDF = "catalogo.pdf"

def mostrar_pdf_inline(caminho_pdf: str, altura: int = 950):
    """Mostra PDF dentro do Streamlit (iframe)."""
    with open(caminho_pdf, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode("utf-8")
    st.markdown(
        f"""
        <iframe
            src="data:application/pdf;base64,{base64_pdf}"
            width="100%"
            height="{altura}"
            style="border: none; border-radius: 10px;"
        ></iframe>
        """,
        unsafe_allow_html=True
    )

# ======================
# STATE: WhatsApp fixo + Admin login
# ======================
if "wa_link" not in st.session_state:
    st.session_state.wa_link = None

if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False

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


def horarios_ocupados(data_escolhida: date):
    resp = (
        supabase
        .table("agendamentos")
        .select("horario")
        .eq("data", data_escolhida.isoformat())
        .execute()
    )
    return set([r["horario"] for r in (resp.data or [])])


def inserir_agendamento(cliente, data_escolhida: date, horario, servico):
    payload = {
        "cliente": cliente,
        "data": data_escolhida.isoformat(),
        "horario": horario,
        "servico": servico
    }
    return supabase.table("agendamentos").insert(payload).execute()


def excluir_agendamento(ag_id: int):
    return supabase.table("agendamentos").delete().eq("id", ag_id).execute()


def montar_link_whatsapp(nome, data_atendimento: date, horario, servico):
    mensagem = (
        "Olá! Barbára Vitória, gostaria de confirmar meu agendamento:\n\n"
        f"👩 Cliente: {nome}\n"
        f"📅 Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
        f"⏰ Horário: {horario}\n"
        f"💅 Serviço: {servico}\n"
    )
    mensagem_url = urllib.parse.quote(mensagem, safe="")
    return f"https://api.whatsapp.com/send?phone={WHATSAPP_NUMERO}&text={mensagem_url}"

# ======================
# TABS
# ======================
aba_agendar, aba_catalogo, aba_admin = st.tabs(["💅 Agendamento", "📒 Catálogo", "🔐 Admin"])

# ======================
# ABA: AGENDAMENTO
# ======================
with aba_agendar:
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

    st.markdown("**Horários disponíveis**")

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

    if st.button("Confirmar Agendamento 💅"):
        if not nome or not horario_escolhido:
            st.error("Preencha todos os campos")
        else:
            resp = inserir_agendamento(nome, data_atendimento, horario_escolhido, servico)

            # Checa erro sem depender de exception
            if getattr(resp, "error", None):
                st.error("Esse horário acabou de ser ocupado. Escolha outro.")
            else:
                st.success("Agendamento registrado! 💖")
                st.session_state.wa_link = montar_link_whatsapp(
                    nome, data_atendimento, horario_escolhido, servico
                )

    # ======================
    # BOTÃO FIXO WHATSAPP
    # ======================
    if st.session_state.wa_link:
        st.divider()
        st.subheader("📲 Confirmar no WhatsApp")

        st.link_button("Abrir WhatsApp para confirmar", st.session_state.wa_link)
        st.caption("Se não abrir, copie e cole este link no navegador:")
        st.code(st.session_state.wa_link)

        if st.button("Limpar link de confirmação ✅"):
            st.session_state.wa_link = None
            st.rerun()

# ======================
# ABA: CATÁLOGO
# ======================
with aba_catalogo:
    st.subheader("📒 Catálogo de Serviços")

    try:
        with open(CATALOGO_PDF, "rb") as f:
            st.download_button(
                "⬇️ Baixar catálogo (PDF)",
                data=f,
                file_name="catalogo.pdf",
                mime="application/pdf"
            )

        st.caption("Visualize o catálogo aqui mesmo no app 👇")
        mostrar_pdf_inline(CATALOGO_PDF, altura=950)

    except FileNotFoundError:
        st.error("Não encontrei o arquivo 'catalogo.pdf' no repositório.")
        st.info("Confirme se o arquivo está na mesma pasta do app.py e com o nome exato: catalogo.pdf")

# ======================
# ABA: ADMIN
# ======================
with aba_admin:
    st.subheader("Área administrativa 🔐")

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
            data_filtro = st.date_input("Escolha a data", value=date.today(), key="data_filtro_admin")
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
                ag_id = int(escolha.split("|")[0].replace("#", "").strip())
                excluir_agendamento(ag_id)
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
            senha = st.text_input("Senha da profissional", type="password")
            entrar = st.form_submit_button("Entrar")

        if entrar:
            if senha.strip() == SENHA_ADMIN.strip():
                st.session_state.admin_logado = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
