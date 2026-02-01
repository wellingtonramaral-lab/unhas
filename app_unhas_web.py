import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
from supabase import create_client
import fitz  # PyMuPDF
import json
import streamlit.components.v1 as components

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
if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False

if "wa_link" not in st.session_state:
    st.session_state.wa_link = None

if "wa_scheme" not in st.session_state:
    st.session_state.wa_scheme = None

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

def montar_mensagem(nome, data_atendimento: date, horario, servico):
    return (
        "Olá! Barbára Vitória, quero CONFIRMAR meu agendamento:\n\n"
        f"👩 Cliente: {nome}\n"
        f"📅 Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
        f"⏰ Horário: {horario}\n"
        f"💅 Serviço: {servico}\n\n"
        "✅ Estou enviando esta mensagem para confirmar."
    )

def montar_links_whatsapp(mensagem: str):
    text_encoded = urllib.parse.quote(mensagem, safe="")
    url_web = f"https://wa.me/{WHATSAPP_NUMERO}?text={text_encoded}"
    url_scheme = f"whatsapp://send?phone={WHATSAPP_NUMERO}&text={text_encoded}"
    return url_web, url_scheme

def copiar_para_clipboard(texto: str):
    components.html(
        f"<script>navigator.clipboard.writeText({json.dumps(texto)});</script>",
        height=0
    )

def limpar_confirmacao():
    st.session_state.wa_link = None
    st.session_state.wa_scheme = None
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

    # ======================
    # SE JÁ AGENDOU: MOSTRA CARD E ESCONDE FORM
    # ======================
    if st.session_state.wa_link:
        st.success("Agendamento registrado ✅ Agora envie a confirmação no WhatsApp 👇")

        st.markdown(
            """
            <div style="
                border:1px solid #e6e6e6;
                border-radius:14px;
                padding:16px;
                margin-top:10px;
                background:#ffffff;
            ">
              <div style="font-size:18px;font-weight:700;margin-bottom:8px;">
                📲 Enviar confirmação
              </div>
              <div style="color:#666;margin-bottom:12px;">
                Toque no botão abaixo para abrir o WhatsApp com a mensagem pronta.
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        c1, c2 = st.columns(2)

        with c1:
            st.link_button("📲 Abrir WhatsApp agora", st.session_state.wa_link)

        with c2:
            if st.button("📋 Copiar link"):
                st.session_state.do_copy = True

        if st.session_state.do_copy:
            copiar_para_clipboard(st.session_state.wa_link)
            st.toast("Link copiado ✅", icon="📋")
            st.session_state.do_copy = False

        st.caption("Se não abrir, copie o link e cole no navegador.")
        st.markdown("**Tentar abrir direto no app (opcional):**", help="Pode funcionar dependendo do iPhone/navegador.")
        st.markdown(
            f'<a href="{st.session_state.wa_scheme}" style="text-decoration:none;">'
            f'<button style="padding:10px 14px;border-radius:10px;border:1px solid #ccc;cursor:pointer;">'
            f'📱 Abrir no app (tentativa)'
            f'</button></a>',
            unsafe_allow_html=True
        )

        st.button("🔁 Novo agendamento / Limpar confirmação", on_click=limpar_confirmacao)
        st.stop()

    # ======================
    # FORM NORMAL (SÓ APARECE SE NÃO TIVER wa_link)
    # ======================
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
    st.subheader("📲 Confirmação")

    # Botão principal: agénda e mostra card do WhatsApp
    if st.button("📲 Agendar e abrir WhatsApp"):
        if not nome or not horario_escolhido:
            st.error("Preencha todos os campos")
        else:
            # checa novamente (anti corrida)
            if horario_escolhido in horarios_ocupados(data_atendimento):
                st.error("Esse horário acabou de ser ocupado. Escolha outro.")
            else:
                resp = inserir_agendamento(nome.strip(), data_atendimento, horario_escolhido, servico)

                if getattr(resp, "error", None):
                    st.error("Não foi possível salvar agora. Tente novamente.")
                else:
                    msg = montar_mensagem(nome.strip(), data_atendimento, horario_escolhido, servico)
                    url_web, url_scheme = montar_links_whatsapp(msg)

                    st.session_state.wa_link = url_web
                    st.session_state.wa_scheme = url_scheme

                    st.success("Agendamento registrado! ✅")
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
        st.error("Arquivo 'catalogo.pdf' não encontrado no repositório.")
        st.stop()

    with st.spinner("Carregando catálogo..."):
        paginas = pdf_para_imagens(CATALOGO_PDF)

    for i, img in enumerate(paginas, start=1):
        st.markdown(f"**Página {i}**")
        st.image(img, use_container_width=True)

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
