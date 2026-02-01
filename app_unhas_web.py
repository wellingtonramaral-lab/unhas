import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta, timezone
import urllib.parse
from supabase import create_client
import fitz  # PyMuPDF
import json
import streamlit.components.v1 as components
from PIL import Image
import io
from postgrest.exceptions import APIError

# ======================
# SECRETS
# ======================
SENHA_ADMIN = st.secrets["SENHA_ADMIN"]
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]  # só números, ex: 5548999999999
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

PIX_CHAVE = st.secrets.get("PIX_CHAVE", "")
PIX_NOME = st.secrets.get("PIX_NOME", "Profissional")
PIX_CIDADE = st.secrets.get("PIX_CIDADE", "BRASIL")

# Se quiser expirar reserva pendente (ex: 30 min). Coloque 0 para NÃO expirar.
TEMPO_EXPIRACAO_MIN = int(st.secrets.get("TEMPO_EXPIRACAO_MIN", 30))

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ======================
# CONFIG STREAMLIT
# ======================
st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ======================
# PREÇOS / SINAL FIXO
# ======================
VALOR_SINAL_FIXO = 20.0

PRECOS = {
    "Unha em Gel": 130.0,
    "Manutenção – Gel": 100.0,

    "Unha Fibra de Vidro": 150.0,
    "Manutenção – Fibra": 110.0,

    "Pedicure": 50.0,
    "Manutenção – Pedicure": 50.0,

    "Banho de Gel": 100.0,
    "Manutenção – Banho de Gel": 100.0,
}


def fmt_brl(v: float) -> str:
    s = f"{float(v):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def calcular_sinal(_servico: str) -> float:
    return float(VALOR_SINAL_FIXO)


# ======================
# CATÁLOGO PDF → IMAGENS (FIX FUNDO BRANCO)
# ======================
CATALOGO_PDF = "catalogo.pdf"


@st.cache_data(show_spinner=False)
def pdf_para_imagens_com_fundo_branco(caminho_pdf: str, zoom: float = 2.0):
    doc = fitz.open(caminho_pdf)
    imagens = []
    mat = fitz.Matrix(zoom, zoom)

    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=True)
        png_bytes = pix.tobytes("png")

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

if "wa_link" not in st.session_state:
    st.session_state.wa_link = None

if "ultimo_ag" not in st.session_state:
    st.session_state.ultimo_ag = None

if "copy_text" not in st.session_state:
    st.session_state.copy_text = None

# Anti-duplo clique / idempotência
if "reservando" not in st.session_state:
    st.session_state.reservando = False

if "ultima_chave_reserva" not in st.session_state:
    st.session_state.ultima_chave_reserva = None


# ======================
# HELPERS
# ======================
def copiar_para_clipboard(texto: str):
    components.html(
        f"<script>navigator.clipboard.writeText({json.dumps(texto)});</script>",
        height=0
    )


def parse_dt(dt_str: str) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def limpar_confirmacao():
    st.session_state.wa_link = None
    st.session_state.ultimo_ag = None
    st.session_state.copy_text = None
    st.session_state.reservando = False
    st.session_state.ultima_chave_reserva = None
    st.rerun()


def make_reserva_key(nome: str, data_at: date, horario: str, servico: str) -> str:
    return f"{nome.strip().lower()}|{data_at.isoformat()}|{horario}|{servico}"


# ======================
# FUNÇÕES SUPABASE
# ======================
def listar_agendamentos():
    resp = (
        supabase
        .table("agendamentos")
        .select("id,cliente,data,horario,servico,status,valor,created_at")
        .order("data")
        .order("horario")
        .execute()
    )
    dados = resp.data or []
    df = pd.DataFrame(dados)

    if df.empty:
        return pd.DataFrame(columns=["id", "Cliente", "Data", "Horário", "Serviço", "Status", "Valor", "Criado em"])

    df.rename(columns={
        "cliente": "Cliente",
        "data": "Data",
        "horario": "Horário",
        "servico": "Serviço",
        "status": "Status",
        "valor": "Valor",
        "created_at": "Criado em"
    }, inplace=True)

    df["Data"] = df["Data"].astype(str)
    df["Horário"] = df["Horário"].astype(str)
    df["Status"] = df["Status"].astype(str)
    df["Valor"] = df["Valor"].apply(lambda x: float(x) if x is not None else 0.0)

    return df


def horarios_ocupados(data_escolhida: date):
    """
    Considera ocupado:
    - status = 'pago'
    - status = 'pendente' e (se TEMPO_EXPIRACAO_MIN > 0) ainda não expirou
    """
    resp = (
        supabase
        .table("agendamentos")
        .select("horario,status,created_at")
        .eq("data", data_escolhida.isoformat())
        .execute()
    )

    rows = resp.data or []
    ocupados = set()
    now = agora_utc()

    for r in rows:
        horario = r.get("horario")
        status = (r.get("status") or "").lower().strip()
        created_at = parse_dt(r.get("created_at", ""))

        if status == "pago":
            ocupados.add(horario)
            continue

        if status == "pendente":
            if TEMPO_EXPIRACAO_MIN <= 0:
                ocupados.add(horario)
            else:
                if created_at is None:
                    # se não der pra parsear, por segurança bloqueia
                    ocupados.add(horario)
                else:
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if (now - created_at) <= timedelta(minutes=TEMPO_EXPIRACAO_MIN):
                        ocupados.add(horario)

    return set(ocupados)


def inserir_pre_agendamento(cliente, data_escolhida: date, horario, servico, valor_sinal: float):
    payload = {
        "cliente": cliente,
        "data": data_escolhida.isoformat(),
        "horario": horario,
        "servico": servico,
        "status": "pendente",
        "valor": valor_sinal
    }

    try:
        return supabase.table("agendamentos").insert(payload).execute()
    except APIError as e:
        msg = str(e)

        # caso comum: duplicidade (índice único data+horario)
        if "duplicate key" in msg.lower() or "23505" in msg:
            st.warning("Esse horário já foi reservado. Escolha outro.")
            return None

        # Mostra erro real (para você me mandar)
        st.error("Erro ao salvar no Supabase. Copie e me envie essa mensagem:")
        st.code(msg)
        return None


def marcar_como_pago(ag_id: int):
    return supabase.table("agendamentos").update({"status": "pago"}).eq("id", ag_id).execute()


def excluir_agendamento(ag_id: int):
    return supabase.table("agendamentos").delete().eq("id", ag_id).execute()


def montar_mensagem_pagamento(nome, data_atendimento: date, horario, servico, valor_sinal: float):
    total = float(PRECOS.get(servico, 0.0))
    msg = (
        "Olá! Quero reservar meu horário. 💅\n\n"
        f"👩 Cliente: {nome}\n"
        f"📅 Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
        f"⏰ Horário: {horario}\n"
        f"💅 Serviço: {servico}\n\n"
        f"💰 Valor do serviço: {fmt_brl(total)}\n"
        f"✅ Sinal para confirmar: {fmt_brl(valor_sinal)}\n\n"
        "Pix para pagamento do sinal:\n"
        f"🔑 Chave Pix: {PIX_CHAVE}\n"
        f"👤 Nome: {PIX_NOME}\n"
        f"🏙️ Cidade: {PIX_CIDADE}\n\n"
        "📌 Assim que pagar, me envie o comprovante aqui para eu confirmar como PAGO. 🙏"
    )
    return msg


def montar_link_whatsapp(texto: str):
    text_encoded = urllib.parse.quote(texto, safe="")
    return f"https://wa.me/{WHATSAPP_NUMERO}?text={text_encoded}"


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

    eh_domingo = (data_atendimento.weekday() == 6)
    if eh_domingo:
        st.warning("Não atendemos aos domingos. Escolha outra data para agendar.")

    servico = st.selectbox("Tipo de serviço", list(PRECOS.keys()))

    total_servico = float(PRECOS.get(servico, 0.0))
    valor_sinal = calcular_sinal(servico)
    st.caption(f"Valor do serviço: **{fmt_brl(total_servico)}** • Sinal para reservar: **{fmt_brl(valor_sinal)}**")

    horarios = ["07:00", "08:30", "10:00", "13:30", "15:00", "16:30", "18:00"]

    # não consulta supabase se for domingo (mas também não trava outras abas)
    ocupados = horarios_ocupados(data_atendimento) if not eh_domingo else set()
    dia_lotado = (len(ocupados) >= len(horarios)) if not eh_domingo else False

    if dia_lotado:
        st.warning("Esse dia está sem vagas. Escolha outra data.")

    disponiveis = [h for h in horarios if h not in ocupados] if not eh_domingo else horarios

    st.markdown("**Horários disponíveis**")
    with st.container(height=180):
        horario_escolhido = st.radio("Escolha um horário", disponiveis, label_visibility="collapsed")

    st.divider()

    pode_agendar = (not eh_domingo) and (not dia_lotado) and (not st.session_state.reservando)

    left, r1, r2, r3 = st.columns([1.2, 1, 1, 0.9])

    with left:
        reservar_click = st.button(
            "💳 Reservar e pagar sinal",
            use_container_width=True,
            disabled=not pode_agendar
        )

    with r1:
        if st.session_state.wa_link:
            st.link_button("📲 Abrir WhatsApp", st.session_state.wa_link, use_container_width=True)
        else:
            st.write("")

    with r2:
        if st.session_state.copy_text:
            if st.button("📋 Copiar mensagem", use_container_width=True):
                copiar_para_clipboard(st.session_state.copy_text)
                st.toast("Mensagem copiada ✅", icon="📋")
        else:
            st.write("")

    with r3:
        if st.session_state.wa_link:
            st.button("🧹 Limpar", use_container_width=True, on_click=limpar_confirmacao)
        else:
            st.write("")

    if PIX_CHAVE and st.session_state.wa_link:
        if st.button("🔑 Copiar chave Pix", use_container_width=True):
            copiar_para_clipboard(PIX_CHAVE)
            st.toast("Chave Pix copiada ✅", icon="🔑")

    # ===== AÇÃO DO RESERVAR =====
    if reservar_click:
        if not nome or not horario_escolhido:
            st.error("Preencha todos os campos.")
        else:
            st.session_state.reservando = True

            chave = make_reserva_key(nome, data_atendimento, horario_escolhido, servico)
            if st.session_state.ultima_chave_reserva == chave:
                st.warning("Você já enviou esse agendamento. Se precisar, clique em Limpar e tente novamente.")
                st.session_state.reservando = False
            else:
                # checa de novo (anti-corrida)
                if horario_escolhido in horarios_ocupados(data_atendimento):
                    st.error("Esse horário acabou de ser ocupado. Escolha outro.")
                    st.session_state.reservando = False
                else:
                    resp = inserir_pre_agendamento(
                        nome.strip(),
                        data_atendimento,
                        horario_escolhido,
                        servico,
                        valor_sinal
                    )

                    if resp is None:
                        st.session_state.reservando = False
                    else:
                        mensagem = montar_mensagem_pagamento(
                            nome.strip(),
                            data_atendimento,
                            horario_escolhido,
                            servico,
                            valor_sinal
                        )
                        st.session_state.copy_text = mensagem
                        st.session_state.wa_link = montar_link_whatsapp(mensagem)
                        st.session_state.ultimo_ag = {
                            "cliente": nome.strip(),
                            "data": data_atendimento.strftime("%d/%m/%Y"),
                            "horario": horario_escolhido,
                            "servico": servico,
                            "sinal": valor_sinal,
                            "status": "pendente"
                        }
                        st.session_state.ultima_chave_reserva = chave
                        st.session_state.reservando = False
                        st.success("Reserva criada como **PENDENTE**. Envie a mensagem no WhatsApp e pague o sinal via Pix.")
                        st.rerun()

    if st.session_state.ultimo_ag:
        u = st.session_state.ultimo_ag
        st.caption(
            f"Última reserva: **{u['cliente']}** • **{u['data']}** • **{u['horario']}** • **{u['servico']}** • "
            f"**{fmt_brl(float(u.get('sinal', 0.0)))}** • **{u.get('status', '').upper()}**"
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
    else:
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

        st.subheader("📋 Agendamentos / Reservas")

        colf1, colf2 = st.columns([1, 1])
        with colf1:
            filtrar_data = st.checkbox("Filtrar por data")
        with colf2:
            filtrar_status = st.checkbox("Filtrar por status")

        if filtrar_data:
            data_filtro = st.date_input("Escolha a data", value=date.today(), key="filtro_admin")
            df_admin = df_admin[df_admin["Data"] == str(data_filtro)]

        if filtrar_status:
            status_sel = st.selectbox("Status", ["pendente", "pago"])
            df_admin = df_admin[df_admin["Status"].str.lower() == status_sel]

        if df_admin.empty:
            st.info("Nenhum agendamento encontrado.")
        else:
            df_show = df_admin.copy()
            df_show["Valor"] = df_show["Valor"].apply(lambda v: fmt_brl(float(v)))
            st.dataframe(df_show.drop(columns=["id"]), use_container_width=True)

            st.subheader("✅ Marcar como PAGO")
            op_pagar = df_admin.apply(
                lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço"]} | {r["Status"]}',
                axis=1
            ).tolist()

            escolha_pagar = st.selectbox("Selecione uma reserva/agendamento", op_pagar, key="sel_pagar")
            if st.button("Marcar como PAGO ✅"):
                ag_id = int(escolha_pagar.split("|")[0].replace("#", "").strip())
                marcar_como_pago(ag_id)
                st.success("Marcado como PAGO ✅")
                st.rerun()

            st.subheader("🗑️ Excluir")
            op_excluir = df_admin.apply(
                lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço"]} | {r["Status"]}',
                axis=1
            ).tolist()

            escolha_exc = st.selectbox("Selecione", op_excluir, key="sel_exc")
            if st.button("Excluir ❌"):
                ag_id = int(escolha_exc.split("|")[0].replace("#", "").strip())
                excluir_agendamento(ag_id)
                st.success("Excluído ✅")
                st.rerun()

        st.subheader("⬇️ Baixar CSV")
        if not df_admin.empty:
            df_csv = df_admin.copy()
            df_csv["Valor"] = df_csv["Valor"].apply(lambda v: fmt_brl(float(v)))
            st.download_button(
                "Baixar agendamentos.csv",
                df_csv.drop(columns=["id"]).to_csv(index=False).encode("utf-8"),
                file_name="agendamentos.csv",
                mime="text/csv"
            )
        else:
            st.download_button(
                "Baixar agendamentos.csv",
                pd.DataFrame().to_csv(index=False).encode("utf-8"),
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
