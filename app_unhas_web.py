import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
from supabase import create_client
from supabase_auth.errors import AuthApiError
import fitz  # PyMuPDF

# =========================================================
# SECRETS (Streamlit Cloud → Settings → Secrets)
# =========================================================
# Obrigatórios:
# SUPABASE_URL="https://xxxx.supabase.co"
# SUPABASE_SERVICE_ROLE_KEY="...."
# SUPABASE_ANON_KEY="...."               <- ANON PUBLIC KEY (para Auth OTP)
# SENHA_ADMIN="Maite04!"
# WHATSAPP_NUMERO="5548XXXXXXXXX"
#
# Arquivo no repo:
# catalogo.pdf (na mesma pasta do app.py)
#
# Requisitos (requirements.txt):
# streamlit
# pandas
# supabase
# pymupdf
# =========================================================

SENHA_ADMIN = st.secrets["SENHA_ADMIN"]
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]  # só números: 55 + DDD + número
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

# Cliente DB (server) - acesso ao banco
supabase_db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
# Cliente Auth (OTP por SMS) - usa ANON KEY
supabase_auth = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ======================
# CONFIG STREAMLIT
# ======================
st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ======================
# CATÁLOGO PDF → IMAGENS
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

# Gate SMS (OTP)
if "cliente_verificada" not in st.session_state:
    st.session_state.cliente_verificada = False
if "cliente_phone" not in st.session_state:
    st.session_state.cliente_phone = None
if "cliente_nome" not in st.session_state:
    st.session_state.cliente_nome = None
if "otp_enviado" not in st.session_state:
    st.session_state.otp_enviado = False

# ======================
# HELPERS SMS/OTP
# ======================
def normalizar_phone_br(phone: str) -> str:
    """
    Aceita: 48999999999, (48) 99999-9999, 5548999999999, +5548999999999
    Retorna em E.164: +55DDDNUMERO
    """
    digits = "".join([c for c in phone if c.isdigit()])
    if digits.startswith("55"):
        return "+" + digits
    return "+55" + digits

def send_otp(phone_e164: str):
    # Envia OTP por SMS (depende de Phone Provider configurado no Supabase)
    return supabase_auth.auth.sign_in_with_otp({"phone": phone_e164})

def verify_otp(phone_e164: str, code: str):
    # Verifica OTP
    return supabase_auth.auth.verify_otp({"phone": phone_e164, "token": code, "type": "sms"})

def garantir_tabela_clientes():
    """
    Garante (tentando) que a tabela clientes exista.
    Se você já criou no SQL Editor, ótimo.
    Se não existir, esse select vai falhar. Aí crie manualmente no Supabase com:
      create table public.clientes (phone text primary key, nome text not null, criado_em timestamptz default now());
    """
    pass  # só um lembrete; criação de tabela é no Supabase (SQL Editor)

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
# TABS
# ======================
aba_agendar, aba_catalogo, aba_admin = st.tabs(
    ["💅 Agendamento", "📒 Catálogo", "🔐 Admin"]
)

# ======================
# GATE: CONFIRMAÇÃO POR SMS (antes de agendar)
# ======================
with aba_agendar:
    st.subheader("✅ Confirme seu número para agendar")

    # Se ainda não verificada, mostra tela de verificação e bloqueia o resto
    if not st.session_state.cliente_verificada:
        st.caption("Para evitar agendamentos falsos, confirme seu celular por SMS. Seu nome ficará fixo no sistema.")

        # Se já enviou OTP, mostramos o telefone travado para não confundir
        if not st.session_state.otp_enviado:
            nome_in = st.text_input("Seu nome (será fixo)", key="nome_gate")
            phone_in = st.text_input("Seu celular/WhatsApp (DDD + número)", key="phone_gate")

            if st.button("Enviar código por SMS"):
                if not nome_in.strip() or not phone_in.strip():
                    st.error("Preencha seu nome e telefone.")
                else:
                    phone_e164 = normalizar_phone_br(phone_in)
                    try:
                        send_otp(phone_e164)
                        st.session_state.otp_enviado = True
                        st.session_state.cliente_phone = phone_e164
                        st.session_state.cliente_nome = nome_in.strip()
                        st.success("Código enviado! Confira seu SMS.")
                    except AuthApiError:
                        st.error(
                            "Não consegui enviar o SMS. Verifique no Supabase se o Provider 'Phone' está ativo e o provedor de SMS configurado."
                        )
                    except Exception:
                        st.error("Erro ao enviar SMS. Tente novamente.")
        else:
            st.info(f"Enviamos um código para: {st.session_state.cliente_phone}")
            codigo = st.text_input("Digite o código (OTP) recebido por SMS", key="otp_code")

            col1, col2
