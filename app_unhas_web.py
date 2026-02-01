import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
from supabase import create_client
import fitz  # PyMuPDF
import json
import streamlit.components.v1 as components
from PIL import Image
import io

# ======================
# SECRETS
# ======================
SENHA_ADMIN = st.secrets["SENHA_ADMIN"]
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]  # só números, ex: 5548999999999
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ======================
# CONFIG STREAMLIT
# ======================
st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ======================
# CATÁLOGO PDF → IMAGENS (FIX: FUNDO BRANCO)
# ======================
CATALOGO_PDF = "catalogo.pdf"

@st.cache_data(show_spinner=False)
def pdf_para_imagens_com_fundo_branco(caminho_pdf: str, zoom: float = 2.0):
    """
    Converte cada página do PDF em PNG.
    FIX catálogo preto: renderiza com alpha e depois "cola" em fundo branco.
    """
    doc = fitz.open(caminho_pdf)
    imagens = []
    mat = fitz.Matrix(zoom, zoom)

    for page in doc:
        # alpha=True para pegar transparência
        pix = page.get_pixmap(matrix=mat, alpha=True)
        png_bytes = pix.tobytes("png")

        # Composita em fundo branco (evita ficar tudo preto)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        out = Image.alpha_composite(bg, img).convert("RGB")

        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        imagens.append(buf.getvalue())

    doc.close()
    return imagens

# ======================
# STATE
# ======================
if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False

# link do whatsapp após agendar
if "wa_link" not in st.session_state:
    st.session_state.wa_link = None

# resumo do último agendamento
if "ultimo_ag" not in st.session_state:
    st.session_state.ultimo_ag = None

if "do_copy" not in st.session_state:
    st.session_state.do_copy = False

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
        "Olá! Barbára Vitória, quero CONFIRMAR meu agendamento:\n\n"
        f"👩 Cliente: {nome}\n"
        f"📅 Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
        f"⏰ Horário: {horario}\n"
        f"💅 Serviço: {servico}\n\n"
        "✅ Estou enviando esta mensagem para confirmar."
    )
    text_encoded = urllib.parse.quote(mensagem, safe="")
    return f"https://wa.me/{WHATSAPP_NUMERO}?text={text_encoded}"

def copiar_para_clipboard(texto: str):
    components.html(
        f"<script>navigator.clipboard.writeText({json.dumps(texto)});</script>",
        height=0
    )

def limpar_confirmacao():
    st.session_state.wa_link = None
    st.session_state.ultimo_ag = None
    st.rerun()

# ======================
# TABS
# ======================
aba_agendar, aba_catalogo, aba_admin = st.tabs(
    ["💅 Agendamento", "📒 Catálogo", "🔐 Admin"]
)

# ======================
# ABA: AGENDAMENTO
# ======================
with aba_agendar:
    st.subheader("Agende seu horário")

    nome = st.text_input("Nome da cliente")
    data_atendimento = st.date_input("Data do atendimento", min_value=date.today())

    # (1) BLOQUEAR DOMINGO
    if data_atendimento.weekday() == 6:
        st.error("Não atendemos aos domingos. Escolha outra data.")
        st.stop()

    servico = st.selectbox(
        "Tipo de serviço",
        ["Alongamento em Gel", "Alongamento em Fibra de Vidro", "Pedicure", "Manutenção"]
    )

    horarios = ["07:00", "08:30", "10:00", "13:30", "15:00", "16:30", "18:00"]
    ocupados = horarios_ocupados(data_atendimento)

    # (4) BLOQUEAR DIA LOTADO
    if len(ocupados) >= len(horarios):
        st.warning("Esse dia está sem vagas. Escolha outra data.")
        st.stop()

    disponiveis = [h for h in horarios if h not in ocupados]

    st.markdown("**Horários disponíveis**")
    with st.container(height=180):
        horario_escolhido = st.radio(
            "Escolha um horário",
            disponiveis,
            label_visibility="collapsed"
        )

    st.divider()

    # ===== LINHA: AGENDAR + (se tiver) botões de WhatsApp =====
    left, right1, right2, right3 = st.columns([1.2, 1, 1, 0.9])

    with left:
        agendar_click = st.button("✅ Agendar", use_container_width=True)

    # Se já tem link, mostra botões na mesma linha
    with right1:
        if st.session_state.wa_link:
            st.link_button("📲 Abrir WhatsApp", st.session_state.wa_link, use_container_width=True)
        else:
            st.write("")

    with right2:
        if st.session_state.wa_link:
            if st.button("📋 Copiar link", use_container_width=True):
                st.session_state.do_copy = True
        else:
            st.write("")

    with right3:
        if st.session_state.wa_link:
            st.button("🧹 Limpar", use_container_width=True, on_click=limpar_confirmacao)
        else:
            st.write("")

    if st.session_state.do_copy and st.session_state.wa_link:
        copiar_para_clipboard(st.session_state.wa_link)
        st.toast("Link copiado ✅", icon="📋")
        st.session_state.do_copy = False

    # ===== AÇÃO DO AGENDAR =====
    if agendar_click:
        if not nome or not horario_escolhido:
            st.error("Preencha todos os campos")
        else:
            # checa novamente (anti-corrida)
            if horario_escolhido in horarios_ocupados(data_atendimento):
                st.error("Esse horário acabou de ser ocupado. Escolha outro.")
            else:
                resp = inserir_agendamento(nome.strip(), data_atendimento, horario_escolhido, servico)
                if getattr(resp, "error", None):
                    st.error("Não foi possível salvar agora. Tente novamente.")
                else:
                    st.session_state.wa_link = montar_link_whatsapp(
                        nome.strip(), data_atendimento, horario_escolhido, servico
                    )
                    st.session_state.ultimo_ag = {
                        "cliente": nome.strip(),
                        "data": data_atendimento.strftime("%d/%m/%Y"),
                        "horario": horario_escolhido,
                        "servico": servico
                    }
                    st.success("Agendamento registrado! Agora confirme no WhatsApp.")
                    st.rerun()

    # ===== RESUMO DISCRETO (abaixo) =====
    if st.session_state.ultimo_ag:
        u = st.session_state.ultimo_ag
        st.caption(
            f"Último agendamento: **{u['cliente']}** • **{u['data']}** • **{u['horario']}** • **{u['servico']}**"
        )

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
        st.error("Arquivo 'catalogo.pdf' não encontrado no repositório.")
        st.stop()

    with st.spinner("Carregando catálogo..."):
        paginas = pdf_para_imagens_com_fundo_branco(CATALOGO_PDF, zoom=2.0)

    for i, img_bytes in enumerate(paginas, start=1):
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
            data_filtro = st.date_input("Escolha a data", value=date.today(), key="filtro_admin")
            df_admin = df_admin[df_admin["Data"] == str(data_filtro)]

        if df_admin.empty:
            st.info("Nenhum agendamento encontrado.")
        else:
            st.dataframe(df_admin.drop(columns=["id"]), use_container_width=True)

            st.subheader("🗑️ Excluir um agendamento")
            opcoes = df_admin.apply(
                lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço"]}',
                axis=1
            ).tolist()

            escolha = st.selectbox("Selecione", opcoes)
            if st.button("Excluir ❌"):
                ag_id = int(escolha.split("|")[0].replace("#", "").strip())
                excluir_agendamento(ag_id)
                st.success("Agendamento excluído ✅")
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
