import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta, timezone
import urllib.parse
from supabase import create_client
import fitz  # PyMuPDF
from PIL import Image
import io
from postgrest.exceptions import APIError

# timezone Brasil (UTC-3)
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=-3))


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

# 60 minutos
TEMPO_EXPIRACAO_MIN = int(st.secrets.get("TEMPO_EXPIRACAO_MIN", 60))

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
    "Alongamento em Gel": 130.0,
    "Manutenção – Gel": 100.0,

    "Fibra de Vidro": 150.0,
    "Manutenção – Fibra": 110.0,

    "Pedicure": 50.0,
    "Banho de Gel": 100.0,
}


def fmt_brl(v: float) -> str:
    s = f"{float(v):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def calcular_sinal(_servicos: list[str]) -> float:
    return float(VALOR_SINAL_FIXO)


def normalizar_servicos(servicos: list[str]) -> list[str]:
    return [s.strip() for s in servicos if s and s.strip()]


def servicos_para_texto(servicos: list[str]) -> str:
    return " + ".join(normalizar_servicos(servicos))


def texto_para_lista_servicos(texto: str) -> list[str]:
    if not texto:
        return []
    parts = [p.strip() for p in texto.split("+")]
    return [p for p in parts if p]


def calcular_total_servicos(servicos: list[str]) -> float:
    total = 0.0
    for s in normalizar_servicos(servicos):
        total += float(PRECOS.get(s, 0.0))
    return float(total)


def calcular_total_por_texto_servico(texto_servico: str) -> float:
    servs = texto_para_lista_servicos(texto_servico)
    return calcular_total_servicos(servs)


# ======================
# HORÁRIOS POR DIA
# ======================
def horarios_do_dia(d: date) -> list[str]:
    wd = d.weekday()  # 0=seg ... 5=sab ... 6=dom
    if wd in [0, 1, 2, 3, 4]:  # seg-sex
        return ["18:00"]
    if wd == 5:  # sábado
        return ["10:30", "14:00", "18:00"]
    return []  # domingo


# ======================
# CATÁLOGO PDF → IMAGENS (FUNDO BRANCO)
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

if "reservando" not in st.session_state:
    st.session_state.reservando = False

if "ultima_chave_reserva" not in st.session_state:
    st.session_state.ultima_chave_reserva = None


# ======================
# HELPERS
# ======================
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


def agora_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def agendamento_dt_local(data_str: str, horario_str: str) -> datetime | None:
    """
    Converte (data yyyy-mm-dd + horario HH:MM) em datetime local com tz.
    """
    try:
        d = datetime.strptime(str(data_str), "%Y-%m-%d").date()
        hh, mm = str(horario_str).split(":")
        dt = datetime(d.year, d.month, d.day, int(hh), int(mm), 0, tzinfo=LOCAL_TZ)
        return dt
    except Exception:
        return None


def make_reserva_key(nome: str, data_at: date, horario: str, servicos: list[str]) -> str:
    serv_txt = servicos_para_texto(servicos).lower()
    return f"{nome.strip().lower()}|{data_at.isoformat()}|{horario}|{serv_txt}"


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
        return pd.DataFrame(columns=["id", "Cliente", "Data", "Horário", "Serviço(s)", "Status", "Sinal", "Criado em"])

    df.rename(columns={
        "cliente": "Cliente",
        "data": "Data",
        "horario": "Horário",
        "servico": "Serviço(s)",
        "status": "Status",
        "valor": "Sinal",
        "created_at": "Criado em"
    }, inplace=True)

    df["Data"] = df["Data"].astype(str)
    df["Horário"] = df["Horário"].astype(str)
    df["Status"] = df["Status"].astype(str)
    df["Sinal"] = df["Sinal"].apply(lambda x: float(x) if x is not None else 0.0)

    return df


def limpar_pendentes_expirados():
    if TEMPO_EXPIRACAO_MIN <= 0:
        return

    cutoff_dt = agora_utc() - timedelta(minutes=TEMPO_EXPIRACAO_MIN)
    cutoff_iso = cutoff_dt.isoformat()

    supabase.table("agendamentos") \
        .delete() \
        .eq("status", "pendente") \
        .lt("created_at", cutoff_iso) \
        .execute()


def atualizar_finalizados():
    """
    Se status = 'pago' e já passou do horário, muda para 'finalizado'.
    Roda no Admin (e pode rodar sempre sem problema).
    """
    try:
        hoje = date.today().isoformat()
        resp = (
            supabase
            .table("agendamentos")
            .select("id,data,horario,status")
            .eq("status", "pago")
            .lte("data", hoje)  # só até hoje
            .execute()
        )

        rows = resp.data or []
        now = agora_local()

        for r in rows:
            ag_id = r.get("id")
            dt = agendamento_dt_local(r.get("data"), r.get("horario"))
            if dt is None:
                continue
            if dt < now:
                supabase.table("agendamentos").update({"status": "finalizado"}).eq("id", ag_id).execute()

    except Exception:
        # se falhar por qualquer motivo, não quebra o app
        return


def horarios_ocupados(data_escolhida: date):
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

        if status in ("pago", "finalizado"):
            ocupados.add(horario)
            continue

        if status == "pendente":
            if TEMPO_EXPIRACAO_MIN <= 0:
                ocupados.add(horario)
            else:
                if created_at is None:
                    ocupados.add(horario)
                else:
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if (now - created_at) <= timedelta(minutes=TEMPO_EXPIRACAO_MIN):
                        ocupados.add(horario)

    return set(ocupados)


def cliente_ja_agendou_no_dia(cliente: str, data_escolhida: date) -> bool:
    try:
        resp = (
            supabase
            .table("agendamentos")
            .select("id")
            .eq("data", data_escolhida.isoformat())
            .ilike("cliente", cliente.strip())
            .limit(1)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        return False


def inserir_pre_agendamento(cliente, data_escolhida: date, horario, servicos: list[str], valor_sinal: float):
    limpar_pendentes_expirados()

    payload = {
        "cliente": cliente,
        "data": data_escolhida.isoformat(),
        "horario": horario,
        "servico": servicos_para_texto(servicos),
        "status": "pendente",
        "valor": valor_sinal
    }

    try:
        return supabase.table("agendamentos").insert(payload).execute()
    except APIError as e:
        msg = str(e).lower()

        if "agendamento_cliente_dia" in msg or "cliente_norm" in msg:
            st.warning("Você já fez um agendamento para esse dia. Se quiser mudar, fale com a profissional.")
            return None

        if "agendamento_unico" in msg or "duplicate key" in msg or "23505" in msg:
            st.warning("Esse horário já foi reservado. Escolha outro.")
            return None

        st.error("Erro ao salvar no Supabase. Copie e me envie essa mensagem:")
        st.code(str(e))
        return None


def marcar_como_pago(ag_id: int):
    return supabase.table("agendamentos").update({"status": "pago"}).eq("id", ag_id).execute()


def excluir_agendamento(ag_id: int):
    return supabase.table("agendamentos").delete().eq("id", ag_id).execute()


def montar_mensagem_pagamento(nome, data_atendimento: date, horario, servicos: list[str], valor_sinal: float):
    servs = normalizar_servicos(servicos)
    total = calcular_total_servicos(servs)

    lista = "\n".join([f"• {s} ({fmt_brl(PRECOS.get(s, 0.0))})" for s in servs]) if servs else "-"

    msg = (
        "Olá! Quero reservar meu horário. 💅\n\n"
        f"👩 Cliente: {nome}\n"
        f"📅 Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
        f"⏰ Horário: {horario}\n"
        "💅 Serviço(s):\n"
        f"{lista}\n\n"
        f"💰 Total dos serviços: {fmt_brl(total)}\n"
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

    servicos_escolhidos = st.multiselect(
        "Tipo de serviço (pode escolher mais de um)",
        options=list(PRECOS.keys()),
        default=[]
    )
    servicos_escolhidos = normalizar_servicos(servicos_escolhidos)

    total_servico = calcular_total_servicos(servicos_escolhidos)
    valor_sinal = calcular_sinal(servicos_escolhidos)

    if servicos_escolhidos:
        st.caption(f"Total dos serviços: **{fmt_brl(total_servico)}** • Sinal para reservar: **{fmt_brl(valor_sinal)}**")
    else:
        st.caption(f"Sinal para reservar: **{fmt_brl(valor_sinal)}**")

    horarios = horarios_do_dia(data_atendimento)

    if eh_domingo or not horarios:
        disponiveis = []
    else:
        ocupados = horarios_ocupados(data_atendimento)
        disponiveis = [h for h in horarios if h not in ocupados]

    if (not eh_domingo) and horarios and (not disponiveis):
        st.info("Sem horários disponíveis para esse dia. Escolha outra data.")

    st.markdown("**Horários disponíveis**")

    if disponiveis:
        with st.container(height=120):
            horario_escolhido = st.radio("Escolha um horário", disponiveis, label_visibility="collapsed")
    else:
        horario_escolhido = None

    st.divider()

    pode_agendar = (
        (not eh_domingo)
        and bool(disponiveis)
        and bool(servicos_escolhidos)
        and (not st.session_state.reservando)
    )

    left, right = st.columns([1.2, 1])

    with left:
        reservar_click = st.button(
            "💳 Reservar e pagar sinal",
            use_container_width=True,
            disabled=not pode_agendar
        )

    with right:
        if st.session_state.wa_link:
            st.link_button("📲 Abrir WhatsApp", st.session_state.wa_link, use_container_width=True)

    if PIX_CHAVE and st.session_state.wa_link:
        if st.button("🔑 Ver chave Pix", use_container_width=True):
            st.toast(f"Chave Pix: {PIX_CHAVE}", icon="🔑")

    if reservar_click:
        if not nome or not horario_escolhido or not servicos_escolhidos:
            st.error("Preencha todos os campos e selecione pelo menos 1 serviço.")
        else:
            st.session_state.reservando = True

            chave = make_reserva_key(nome, data_atendimento, horario_escolhido, servicos_escolhidos)
            if st.session_state.ultima_chave_reserva == chave:
                st.warning("Você já enviou esse agendamento. Se quiser mudar, fale com a profissional.")
                st.session_state.reservando = False
            else:
                if cliente_ja_agendou_no_dia(nome, data_atendimento):
                    st.warning("Você já fez um agendamento para esse dia. Se quiser mudar, fale com a profissional.")
                    st.session_state.reservando = False
                else:
                    if horario_escolhido in horarios_ocupados(data_atendimento):
                        st.warning("Esse horário já foi reservado. Escolha outro.")
                        st.session_state.reservando = False
                    else:
                        resp = inserir_pre_agendamento(
                            nome.strip(),
                            data_atendimento,
                            horario_escolhido,
                            servicos_escolhidos,
                            valor_sinal
                        )

                        if resp is None:
                            st.session_state.reservando = False
                        else:
                            mensagem = montar_mensagem_pagamento(
                                nome.strip(),
                                data_atendimento,
                                horario_escolhido,
                                servicos_escolhidos,
                                valor_sinal
                            )
                            st.session_state.wa_link = montar_link_whatsapp(mensagem)
                            st.session_state.ultimo_ag = {
                                "cliente": nome.strip(),
                                "data": data_atendimento.strftime("%d/%m/%Y"),
                                "horario": horario_escolhido,
                                "servicos": servicos_para_texto(servicos_escolhidos),
                                "sinal": valor_sinal,
                                "status": "pendente"
                            }
                            st.session_state.ultima_chave_reserva = chave
                            st.session_state.reservando = False
                            st.success("Reserva criada como **PENDENTE**. Clique em **Abrir WhatsApp** para enviar a mensagem.")
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
        # ✅ Atualiza finalizados automaticamente ao abrir admin
        atualizar_finalizados()

        st.success("Acesso liberado ✅")
        if st.button("Sair"):
            sair_admin()

        df_admin = listar_agendamentos()

        st.subheader("📋 Agendamentos / Reservas")

        if df_admin.empty:
            st.info("Nenhum agendamento encontrado.")
        else:
            df_admin["Data_dt"] = pd.to_datetime(df_admin["Data"], errors="coerce")
            df_admin["Preço do serviço"] = df_admin["Serviço(s)"].apply(calcular_total_por_texto_servico).astype(float)

            # ===== FILTRO DE PERÍODO =====
            colp1, colp2, colp3 = st.columns([1, 1, 1])
            with colp1:
                periodo = st.selectbox("Período", ["Tudo", "Mês", "Ano"], index=0)

            anos_disponiveis = sorted([int(y) for y in df_admin["Data_dt"].dropna().dt.year.unique().tolist()])
            ano_padrao = anos_disponiveis[-1] if anos_disponiveis else date.today().year

            with colp2:
                ano_sel = st.selectbox(
                    "Ano",
                    anos_disponiveis if anos_disponiveis else [ano_padrao],
                    index=(len(anos_disponiveis) - 1) if anos_disponiveis else 0
                )

            with colp3:
                mes_sel = st.selectbox("Mês", list(range(1, 13)), index=date.today().month - 1)

            df_filtrado = df_admin.copy()

            if periodo == "Mês":
                df_filtrado = df_filtrado[
                    (df_filtrado["Data_dt"].dt.year == int(ano_sel)) &
                    (df_filtrado["Data_dt"].dt.month == int(mes_sel))
                ]
            elif periodo == "Ano":
                df_filtrado = df_filtrado[df_filtrado["Data_dt"].dt.year == int(ano_sel)]

            # ===== FILTRO DE STATUS (AGORA COM FINALIZADO) =====
            filtrar_status = st.checkbox("Filtrar por status")
            if filtrar_status:
                status_sel = st.selectbox("Status", ["pendente", "pago", "finalizado"])
                df_filtrado = df_filtrado[df_filtrado["Status"].str.lower() == status_sel]

            total_servicos = float(df_filtrado["Preço do serviço"].sum()) if not df_filtrado.empty else 0.0
            total_sinais = float(df_filtrado["Sinal"].sum()) if not df_filtrado.empty else 0.0
            qtd = int(len(df_filtrado))

            c1, c2, c3 = st.columns(3)
            c1.metric("Quantidade", f"{qtd}")
            c2.metric("Total serviços", fmt_brl(total_servicos))
            c3.metric("Total sinais", fmt_brl(total_sinais))

            df_show = df_filtrado.drop(columns=["Data_dt"]).copy()
            df_show["Preço do serviço"] = df_show["Preço do serviço"].apply(lambda v: fmt_brl(float(v)))
            df_show["Sinal"] = df_show["Sinal"].apply(lambda v: fmt_brl(float(v)))

            st.dataframe(df_show.drop(columns=["id"]), use_container_width=True)

            st.divider()

            st.subheader("✅ Marcar como PAGO")
            op_pagar = df_filtrado.apply(
                lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço(s)"]} | {r["Status"]}',
                axis=1
            ).tolist()

            if op_pagar:
                escolha_pagar = st.selectbox("Selecione uma reserva/agendamento", op_pagar, key="sel_pagar")
                if st.button("Marcar como PAGO ✅"):
                    ag_id = int(escolha_pagar.split("|")[0].replace("#", "").strip())
                    marcar_como_pago(ag_id)
                    st.success("Marcado como PAGO ✅")
                    st.rerun()
            else:
                st.info("Nada para marcar como pago no filtro atual.")

            st.subheader("🗑️ Excluir")
            op_excluir = df_filtrado.apply(
                lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço(s)"]} | {r["Status"]}',
                axis=1
            ).tolist()

            if op_excluir:
                escolha_exc = st.selectbox("Selecione", op_excluir, key="sel_exc")
                if st.button("Excluir ❌"):
                    ag_id = int(escolha_exc.split("|")[0].replace("#", "").strip())
                    excluir_agendamento(ag_id)
                    st.success("Excluído ✅")
                    st.rerun()
            else:
                st.info("Nada para excluir no filtro atual.")

            st.subheader("⬇️ Baixar CSV (filtrado)")
            if not df_filtrado.empty:
                df_csv = df_filtrado.drop(columns=["Data_dt"]).copy()
                df_csv["Preço do serviço"] = df_csv["Preço do serviço"].apply(lambda v: fmt_brl(float(v)))
                df_csv["Sinal"] = df_csv["Sinal"].apply(lambda v: fmt_brl(float(v)))
                st.download_button(
                    "Baixar agendamentos_filtrado.csv",
                    df_csv.drop(columns=["id"]).to_csv(index=False).encode("utf-8"),
                    file_name="agendamentos_filtrado.csv",
                    mime="text/csv"
                )
            else:
                st.download_button(
                    "Baixar agendamentos_filtrado.csv",
                    pd.DataFrame().to_csv(index=False).encode("utf-8"),
                    file_name="agendamentos_filtrado.csv",
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
