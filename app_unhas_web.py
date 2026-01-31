import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
from supabase import create_client
import fitz  # PyMuPDF

# ======================
# SECRETS
# ======================
SENHA_ADMIN = st.secrets["SENHA_ADMIN"]
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]  # só números
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

# cliente DB (server) - mantém como você já estava
supabase_db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# cliente Auth (para cadastro/login)
supabase_auth = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ======================
# CONFIG STREAMLIT
# ======================
st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ======================
# CATÁLOGO PDF
# ======================
CATALOGO_PDF = "catalogo.pdf"

@st.cache_data(show_spinner=False)
def pdf_para_imagens(caminho_pdf: str, zoom: float = 2.0):
    doc = fitz.open(caminho_pdf)
    imagens = []
    mat = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        imagens.append(pix.tobytes("png"))
    doc.close()
    return imagens

# ======================
# STATE
# ======================
if "wa_link" not in st.session_state:
    st.session_state.wa_link = None

if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False

# auth state
if "cliente_logado" not in st.session_state:
    st.session_state.cliente_logado = False
if "cliente_email" not in st.session_state:
    st.session_state.cliente_email = None

# ======================
# FUNÇÕES SUPABASE (DB)
# ======================
def listar_agendamentos():
    resp = (
        supabase_db
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
        supabase_db
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
    return supabase_db.table("agendamentos").insert(payload).execute()

def excluir_agendamento(ag_id: int):
    return supabase_db.table("agendamentos").delete().eq("id", ag_id).execute()

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
# FUNÇÕES AUTH
# ======================
def cadastrar(email: str, senha: str):
    return supabase_auth.auth.sign_up({"email": email, "password": senha})

def entrar(email: str, senha: str):
    return supabase_auth.auth.sign_in_with_password({"email": email, "password": senha})

def sair():
    try:
        supabase_auth.auth.sign_out()
    except Exception:
        pass

    st.session_state.cliente_logado = False
    st.session_state.cliente_email = None
    st.rerun()

# ======================
# TABS
# ======================
aba_agendar, aba_catalogo, aba_conta, aba_admin = st.tabs(
    ["💅 Agendamento", "📒 Catálogo", "👤 Conta", "🔐 Admin"]
)

# ======================
# ABA: CONTA (CADASTRO/LOGIN)
# ======================
with aba_conta:
    st.subheader("👤 Conta da Cliente")

    if st.session_state.cliente_logado:
        st.success(f"Logada como: {st.session_state.cliente_email}")
        st.button("Sair", on_click=sair)
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Entrar")
            with st.form("form_login"):
                email_l = st.text_input("Email", key="email_login")
                senha_l = st.text_input("Senha", type="password", key="senha_login")
                btn_l = st.form_submit_button("Entrar")

            if btn_l:
                resp = entrar(email_l.strip(), senha_l)
                # se deu certo, resp.user existe
                if getattr(resp, "user", None):
                    st.session_state.cliente_logado = True
                    st.session_state.cliente_email = email_l.strip()
                    st.success("Login realizado ✅")
                    st.rerun()
                else:
                    st.error("Não foi possível entrar. Confira e-mail/senha.")

        with col2:
            st.markdown("### Cadastrar")
            st.caption("Se a confirmação de e-mail estiver ativada no Supabase, você vai receber um e-mail para confirmar.")
            with st.form("form_cadastro"):
                email_c = st.text_input("Email", key="email_cad")
                senha_c = st.text_input("Senha", type="password", key="senha_cad")
                senha2_c = st.text_input("Repita a senha", type="password", key="senha2_cad")
                btn_c = st.form_submit_button("Criar conta")

            if btn_c:
                if not email_c or not senha_c:
                    st.error("Preencha e-mail e senha.")
                elif senha_c != senha2_c:
                    st.error("As senhas não conferem.")
                else:
                    resp = cadastrar(email_c.strip(), senha_c)
                    if getattr(resp, "user", None):
                        st.success("Conta criada ✅")
                        st.info("Se o Supabase estiver com confirmação de e-mail ligada, confirme no seu e-mail e depois faça login.")
                    else:
                        st.error("Não foi possível cadastrar. Tente outro e-mail ou uma senha diferente.")

# ======================
# ABA: AGENDAMENTO (bloqueado sem login)
# ======================
with aba_agendar:
    st.subheader("Agende seu horário")

    if not st.session_state.cliente_logado:
        st.warning("Para agendar, você precisa entrar ou criar uma conta na aba **👤 Conta**.")
        st.stop()

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
            horario_escolhido = st.radio("Escolha um horário", disponiveis, label_visibility="collapsed")
    else:
        horario_escolhido = None
        st.warning("Nenhum horário disponível")

    if st.button("Confirmar Agendamento 💅"):
        if not nome or not horario_escolhido:
            st.error("Preencha todos os campos")
        else:
            resp = inserir_agendamento(nome, data_atendimento, horario_escolhido, servico)

            if getattr(resp, "error", None):
                st.error("Esse horário acabou de ser ocupado. Escolha outro.")
            else:
                st.success("Agendamento registrado! 💖")
                st.session_state.wa_link = montar_link_whatsapp(
                    nome, data_atendimento, horario_escolhido, servico
                )

    # Botão fixo WhatsApp
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
    except FileNotFoundError:
        st.error("Não encontrei o arquivo 'catalogo.pdf' no repositório.")
        st.info("Confirme se ele está na mesma pasta do app.py e com o nome exato: catalogo.pdf")
        st.stop()

    st.caption("Visualize o catálogo abaixo (responsivo no PC e no iPhone):")
    with st.spinner("Carregando catálogo..."):
        paginas_png = pdf_para_imagens(CATALOGO_PDF, zoom=2.0)

    for i, img_bytes in enumerate(paginas_png, start=1):
        st.markdown(f"**Página {i}**")
        st.image(img_bytes, use_container_width=True)

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
            entrar_btn = st.form_submit_button("Entrar")

        if entrar_btn:
            if senha.strip() == SENHA_ADMIN.strip():
                st.session_state.admin_logado = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
