# streamlit/app_unhas_web.py
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta, timezone
import urllib.parse
import requests
import fitz  # PyMuPDF
from PIL import Image
import io
from supabase import create_client

# ============================================================
# TIMEZONE Brasil (UTC-3)
# ============================================================
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=-3))

# ============================================================
# STREAMLIT CONFIG
# ============================================================
st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ============================================================
# SECRETS
# ============================================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

# Edge Functions do seu projeto (OBRIGATÓRIAS)
URL_RESERVAR = st.secrets.get("URL_RESERVAR", "").strip()
URL_HORARIOS = st.secrets.get("URL_HORARIOS", "").strip()
URL_TENANT_PUBLIC = st.secrets.get("URL_TENANT_PUBLIC", "").strip()
URL_CREATE_TENANT = st.secrets.get("URL_CREATE_TENANT", "").strip()

TRIAL_DIAS = int(st.secrets.get("TRIAL_DIAS", 7))
TEMPO_EXPIRACAO_MIN = int(st.secrets.get("TEMPO_EXPIRACAO_MIN", 60))
PUBLIC_APP_BASE_URL = st.secrets.get("PUBLIC_APP_BASE_URL", "").strip()

# ============================================================
# MENSALIDADE (PIX do seu SaaS)
# ============================================================
SAAS_PIX_CHAVE = st.secrets.get("SAAS_PIX_CHAVE", "").strip()
SAAS_PIX_NOME = st.secrets.get("SAAS_PIX_NOME", "Suporte").strip()
SAAS_PIX_CIDADE = st.secrets.get("SAAS_PIX_CIDADE", "BRASIL").strip()
SAAS_MENSAL_VALOR = st.secrets.get("SAAS_MENSAL_VALOR", "R$ 39,90").strip()
SAAS_SUPORTE_WHATSAPP = st.secrets.get("SAAS_SUPORTE_WHATSAPP", "").strip()

# ============================================================
# SUPABASE CLIENTS
# ============================================================
def sb_anon():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def sb_user(access_token: str):
    """Compatível com a lib supabase instalada no Streamlit."""
    sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sb.postgrest.auth(access_token)
    return sb

# ============================================================
# HELPERS
# ============================================================
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
    try:
        d = datetime.strptime(str(data_str), "%Y-%m-%d").date()
        hh, mm = str(horario_str).split(":")
        return datetime(d.year, d.month, d.day, int(hh), int(mm), 0, tzinfo=LOCAL_TZ)
    except Exception:
        return None

def parse_date_iso(d) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(str(d))
    except Exception:
        return None

# ============================================================
# PREÇOS / SINAL FIXO
# ============================================================
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

# ============================================================
# HORÁRIOS POR DIA
# ============================================================
def horarios_do_dia(d: date) -> list[str]:
    wd = d.weekday()
    if wd in [0, 1, 2, 3, 4]:
        return ["18:00"]
    if wd == 5:
        return ["10:30", "14:00", "18:00"]
    return []

# ============================================================
# CATÁLOGO PDF → IMAGENS
# ============================================================
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

# ============================================================
# EDGE FUNCTIONS HELPERS
# ============================================================
def fn_headers():
    """Supabase Edge Functions exigem apikey/Authorization."""
    return {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    }

def assert_edge_config():
    missing = []
    if not URL_TENANT_PUBLIC: missing.append("URL_TENANT_PUBLIC")
    if not URL_RESERVAR: missing.append("URL_RESERVAR")
    if not URL_HORARIOS: missing.append("URL_HORARIOS")
    if missing:
        st.error("Configuração incompleta no secrets.")
        st.code({"missing": missing})
        st.stop()

# ============================================================
# ROUTING: PUBLIC vs ADMIN
# ============================================================
query = st.query_params
PUBLIC_TENANT_ID = query.get("t")
if isinstance(PUBLIC_TENANT_ID, list):
    PUBLIC_TENANT_ID = PUBLIC_TENANT_ID[0]
PUBLIC_TENANT_ID = (PUBLIC_TENANT_ID or "").strip()
IS_PUBLIC = bool(PUBLIC_TENANT_ID)

# ============================================================
# SESSION STATE
# ============================================================
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "wa_link" not in st.session_state:
    st.session_state.wa_link = None
if "reservando" not in st.session_state:
    st.session_state.reservando = False
if "ultima_chave_reserva" not in st.session_state:
    st.session_state.ultima_chave_reserva = None

# ============================================================
# AUTH (ADMIN)
# ============================================================
def auth_signup(email: str, password: str, nome: str):
    sb = sb_anon()
    return sb.auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {
                "display_name": nome.strip()
            }
        }
    })


def auth_login(email: str, password: str):
    sb = sb_anon()
    return sb.auth.sign_in_with_password({"email": email, "password": password})

def auth_logout():
    st.session_state.access_token = None
    st.rerun()

def get_auth_user(access_token: str):
    sb = sb_user(access_token)
    try:
        out = sb.auth.get_user(access_token)
        return out.user if out else None
    except Exception:
        return None

# ============================================================
# PROFILE (ADMIN)
# ============================================================
def carregar_profile(access_token: str) -> dict | None:
    sb = sb_user(access_token)
    try:
        resp = (
            sb.table("profiles")
            .select("id,email,nome,whatsapp,pix_chave,pix_nome,pix_cidade")
            .eq("id", sb.auth.get_user(access_token).user.id)
            .single()
            .execute()
        )
        return resp.data
    except Exception:
        return None

def salvar_profile(access_token: str, dados: dict):
    sb = sb_user(access_token)
    return (
        sb.table("profiles")
        .update(dados)
        .eq("id", sb.auth.get_user(access_token).user.id)
        .execute()
    )

# ============================================================
# TENANT LOAD (público / admin)
# ============================================================
def carregar_tenant_publico(tenant_id: str) -> dict | None:
    """Carrega tenant via Edge Function tenant-public.
    Retorna o tenant mesmo quando ok=false (bloqueado),
    para a UI exibir a tela de assinatura.
    """
    assert_edge_config()
    try:
        resp = requests.post(
            URL_TENANT_PUBLIC,
            headers=fn_headers(),
            json={"tenant_id": str(tenant_id)},
            timeout=12
        )
        if resp.status_code != 200:
            return None

        payload = resp.json()
        if isinstance(payload, dict) and isinstance(payload.get("tenant"), dict):
            return payload["tenant"]
        return None
    except Exception:
        return None

def carregar_tenant_admin(access_token: str) -> dict | None:
    sb = sb_user(access_token)
    try:
        resp = (
            sb.table("tenants")
            .select("id,nome,ativo,paid_until,billing_status,whatsapp_numero,pix_chave,pix_nome,pix_cidade,whatsapp,owner_user_id")
            .eq("owner_user_id", sb.auth.get_user(access_token).user.id)
            .maybe_single()
            .execute()
        )
        return resp.data if resp and resp.data else None
    except Exception:
        return None

def criar_tenant_se_nao_existir(access_token: str) -> dict | None:
    """Cria um tenant para o usuário logado (somente via Edge Function)."""
    user = get_auth_user(access_token)
    if not user:
        return {"ok": False, "error": "user_not_found"}

    if not URL_CREATE_TENANT:
        return {"ok": False, "error": "missing_URL_CREATE_TENANT"}

    try:
        resp = requests.post(
            URL_CREATE_TENANT,
            headers=fn_headers(),
            json={"user_id": str(user.id)},
            timeout=12
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"edge_http_{resp.status_code}", "details": resp.text}

        payload = resp.json()
        if isinstance(payload, dict) and payload.get("ok"):
            return payload

        return {"ok": False, "error": "edge_payload_invalid", "details": payload}
    except Exception as e:
        return {"ok": False, "error": "edge_exception", "details": str(e)}

# ============================================================
# PUBLIC: HORÁRIOS OCUPADOS + RESERVA
# ============================================================
def horarios_ocupados_publico(tenant_id: str, data_escolhida: date) -> set[str]:
    assert_edge_config()
    try:
        resp = requests.post(
            URL_HORARIOS,
            headers=fn_headers(),
            json={"tenant_id": str(tenant_id), "data": data_escolhida.isoformat()},
            timeout=12
        )
        if resp.status_code != 200:
            return set()

        payload = resp.json()
        rows = payload.get("rows", []) if isinstance(payload, dict) else []

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

        return ocupados
    except Exception:
        return set()

def inserir_pre_agendamento_publico(
    tenant_id: str,
    cliente: str,
    data_escolhida: date,
    horario: str,
    servicos: list[str],
    valor_sinal: float
) -> dict | None:
    assert_edge_config()
    payload = {
        "tenant_id": str(tenant_id),
        "cliente": cliente.strip(),
        "data": data_escolhida.isoformat(),
        "horario": str(horario),
        "servico": servicos_para_texto(servicos),
        "valor": float(valor_sinal),
    }

    try:
        resp = requests.post(
            URL_RESERVAR,
            headers=fn_headers(),
            json=payload,
            timeout=12
        )

        if resp.status_code != 200:
            st.error(f"Erro ao criar reserva (HTTP {resp.status_code}).")
            st.code(resp.text)
            return None

        out = resp.json()

        if isinstance(out, dict) and out.get("ok") is False:
            err = out.get("error")
            if err == "tenant_blocked":
                st.error("🔒 Agenda indisponível (assinatura vencida/inativa).")
            elif err == "slot_taken":
                st.warning("Esse horário já foi reservado. Escolha outro.")
            else:
                st.error("Erro retornado pela função:")
                st.code(out)
            return None

        return out

    except Exception as e:
        st.error("Falha de rede ao chamar a função de reserva.")
        st.code(str(e))
        return None

# ============================================================
# ADMIN: AGENDAMENTOS
# ============================================================
def listar_agendamentos_admin(access_token: str, tenant_id: str):
    sb = sb_user(access_token)
    resp = (
        sb.table("agendamentos")
        .select("id,cliente,data,horario,servico,status,valor,created_at,tenant_id")
        .eq("tenant_id", str(tenant_id))
        .order("data")
        .order("horario")
        .execute()
    )

    df = pd.DataFrame(resp.data or [])
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

def marcar_como_pago_admin(access_token: str, tenant_id: str, ag_id: int):
    sb = sb_user(access_token)
    return (
        sb.table("agendamentos")
        .update({"status": "pago"})
        .eq("tenant_id", str(tenant_id))
        .eq("id", ag_id)
        .execute()
    )

def excluir_agendamento_admin(access_token: str, tenant_id: str, ag_id: int):
    sb = sb_user(access_token)
    return (
        sb.table("agendamentos")
        .delete()
        .eq("tenant_id", str(tenant_id))
        .eq("id", ag_id)
        .execute()
    )

def atualizar_finalizados_admin(access_token: str, tenant_id: str):
    try:
        sb = sb_user(access_token)
        hoje = date.today().isoformat()
        resp = (
            sb.table("agendamentos")
            .select("id,data,horario,status")
            .eq("tenant_id", str(tenant_id))
            .eq("status", "pago")
            .lte("data", hoje)
            .execute()
        )
        rows = resp.data or []
        now = agora_local()

        for r in rows:
            ag_id = r.get("id")
            dt = agendamento_dt_local(r.get("data"), r.get("horario"))
            if dt and dt < now:
                sb.table("agendamentos").update({"status": "finalizado"}).eq("tenant_id", str(tenant_id)).eq("id", ag_id).execute()
    except Exception:
        return

# ============================================================
# WHATSAPP
# ============================================================
def montar_link_whatsapp(whatsapp_numero: str, texto: str):
    text_encoded = urllib.parse.quote(texto, safe="")
    return f"https://wa.me/{whatsapp_numero}?text={text_encoded}"

def montar_mensagem_pagamento_cliente(
    nome, data_atendimento: date, horario, servicos: list[str], valor_sinal: float,
    pix_chave: str, pix_nome: str, pix_cidade: str
):
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
        f"🔑 Chave Pix: {pix_chave}\n"
        f"👤 Nome: {pix_nome}\n"
        f"🏙️ Cidade: {pix_cidade}\n\n"
        "📌 Assim que pagar, me envie o comprovante aqui para eu confirmar como PAGO. 🙏"
    )
    return msg

# ============================================================
# UI: MODO PÚBLICO (SaaS)
# ============================================================
def tela_publica():
    tenant = carregar_tenant_publico(PUBLIC_TENANT_ID)

    if not tenant:
        st.error("Este link não é válido, não existe ou não está público ainda.")
        st.info("Se você é a profissional, acesse o link sem ?t= para entrar no painel.")
        st.stop()

    nome_prof = tenant.get("nome") or "Profissional"
    st.caption(f"Agenda de: **{nome_prof}**")

    # 🔒 REGRA ÚNICA: backend retorna pode_operar
    if not tenant.get("pode_operar", False):
        st.error("🔒 Assinatura vencida ou conta inativa")

        paid_until = tenant.get("paid_until")
        if paid_until:
            st.caption(f"Venceu em **{paid_until}**.")

        st.markdown("Para liberar, faça o Pix mensal e envie o comprovante no WhatsApp do suporte.")
        st.info(
            f"💰 **Valor:** {SAAS_MENSAL_VALOR}\n\n"
            f"🔑 **Chave Pix:** {SAAS_PIX_CHAVE or '(configure SAAS_PIX_CHAVE)'}\n\n"
            f"👤 **Nome:** {SAAS_PIX_NOME}\n\n"
            f"🏙️ **Cidade:** {SAAS_PIX_CIDADE}\n\n"
            f"🆔 **tenant_id:** {tenant.get('id')}"
        )

        if SAAS_SUPORTE_WHATSAPP:
            msg = f"Olá! Paguei a mensalidade. tenant_id: {tenant.get('id')} | Loja: {nome_prof}"
            link = montar_link_whatsapp(SAAS_SUPORTE_WHATSAPP, msg)
            st.link_button("📲 Enviar comprovante no WhatsApp", link, use_container_width=True)
        else:
            st.warning("Configure no secrets: SAAS_SUPORTE_WHATSAPP (seu WhatsApp do suporte).")

        st.stop()

    whatsapp_num = (tenant.get("whatsapp_numero") or "").strip()
    pix_chave = (tenant.get("pix_chave") or "").strip()
    pix_nome = (tenant.get("pix_nome") or "Profissional").strip()
    pix_cidade = (tenant.get("pix_cidade") or "BRASIL").strip()

    if not whatsapp_num:
        st.warning("WhatsApp desta loja não configurado.")

    aba_agendar, aba_catalogo = st.tabs(["💅 Agendamento", "📒 Catálogo"])

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
            ocupados = horarios_ocupados_publico(PUBLIC_TENANT_ID, data_atendimento)
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

        if pix_chave and st.session_state.wa_link:
            if st.button("🔑 Ver chave Pix", use_container_width=True):
                st.toast(f"Chave Pix: {pix_chave}", icon="🔑")

        def make_reserva_key(_nome: str, data_at: date, horario: str, servicos: list[str]) -> str:
            serv_txt = servicos_para_texto(servicos).lower()
            return f"{_nome.strip().lower()}|{data_at.isoformat()}|{horario}|{serv_txt}"

        if reservar_click:
            if not nome or not horario_escolhido or not servicos_escolhidos:
                st.error("Preencha todos os campos e selecione pelo menos 1 serviço.")
            elif not whatsapp_num:
                st.error("Esta loja ainda não configurou WhatsApp para receber a reserva.")
            else:
                st.session_state.reservando = True
                chave = make_reserva_key(nome, data_atendimento, horario_escolhido, servicos_escolhidos)

                if st.session_state.ultima_chave_reserva == chave:
                    st.warning("Você já enviou esse agendamento. Se quiser mudar, fale com a profissional.")
                    st.session_state.reservando = False
                else:
                    if horario_escolhido in horarios_ocupados_publico(PUBLIC_TENANT_ID, data_atendimento):
                        st.warning("Esse horário já foi reservado. Escolha outro.")
                        st.session_state.reservando = False
                    else:
                        resp = inserir_pre_agendamento_publico(
                            PUBLIC_TENANT_ID,
                            nome.strip(),
                            data_atendimento,
                            horario_escolhido,
                            servicos_escolhidos,
                            valor_sinal
                        )

                        if not resp:
                            st.session_state.reservando = False
                        else:
                            mensagem = montar_mensagem_pagamento_cliente(
                                nome.strip(),
                                data_atendimento,
                                horario_escolhido,
                                servicos_escolhidos,
                                valor_sinal,
                                pix_chave=pix_chave,
                                pix_nome=pix_nome,
                                pix_cidade=pix_cidade
                            )
                            st.session_state.wa_link = montar_link_whatsapp(whatsapp_num, mensagem)
                            st.session_state.ultima_chave_reserva = chave
                            st.session_state.reservando = False
                            st.success("Reserva criada como **PENDENTE**. Clique em **Abrir WhatsApp** para enviar a mensagem.")
                            st.rerun()

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

# ============================================================
# UI: MODO ADMIN
# ============================================================
def tela_admin():
    st.subheader("Área da Profissional 🔐")

    nome = st.text_input("Seu nome (para aparecer no painel)", key="cad_nome")
    
    if not st.session_state.access_token:
        tab1, tab2 = st.tabs(["Entrar", "Criar conta"])

        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Senha", type="password", key="login_pass")
            if st.button("Entrar"):
                try:
                    res = auth_login(email, password)
                    st.session_state.access_token = res.session.access_token
                    st.rerun()
                except Exception as e:
                    st.error("Falha no login.")
                    st.code(str(e))

        with tab2:
            email = st.text_input("Email", key="cad_email")
            password = st.text_input("Senha", type="password", key="cad_pass")
            if st.button("Criar conta"):
                try:
                    auth_signup(email, password, nome)
                    st.success("Conta criada! Agora volte na aba Entrar e faça login.")
                except Exception as e:
                    st.error("Falha ao criar conta.")
                    st.code(str(e))

        st.stop()

    access_token = st.session_state.access_token
    user = get_auth_user(access_token)
    if not user:
        st.warning("Sessão expirada. Faça login novamente.")
        auth_logout()
        st.stop()

    tenant = carregar_tenant_admin(access_token)
    if not tenant:
        st.warning("Você ainda não tem um tenant (loja) criado para esse usuário.")
        st.info("Tentando criar automaticamente...")

        out = criar_tenant_se_nao_existir(access_token)

        if not out or (isinstance(out, dict) and out.get("ok") is False):
            st.error("Falhou ao criar tenant automaticamente.")
            st.info("Verifique a Edge Function create-tenant e o SQL (unique owner_user_id).")
            if isinstance(out, dict):
                st.code(out)
            st.stop()

        st.success("Tenant criado! Recarregando...")
        st.rerun()

    tenant = carregar_tenant_admin(access_token)
    if not tenant:
        st.error("Não consegui carregar o tenant deste usuário.")
        st.stop()

    tenant_id = str(tenant.get("id"))

    # (Opcional) Bloqueio no ADMIN: você pode manter ou remover.
    # Aqui mantive igual seu app: se não estiver ativo/pago, bloqueia.
    paid_until = parse_date_iso(tenant.get("paid_until"))
    hoje = date.today()
    pago = bool(paid_until and paid_until >= hoje)
    ativo = (tenant.get("ativo") is not False)
    billing_ok = (tenant.get("billing_status") in (None, "active", "trial"))

    if (not ativo) or (not pago) or (not billing_ok):
        st.error("🔒 Assinatura mensal pendente")

        if paid_until:
            st.caption(f"Venceu em **{paid_until.strftime('%d/%m/%Y')}**.")
        else:
            st.caption("paid_until vazio (não ativado).")

        st.markdown("Para liberar, faça o Pix mensal e envie o comprovante no WhatsApp do suporte.")

        st.info(
            f"💰 **Valor:** {SAAS_MENSAL_VALOR}\n\n"
            f"🔑 **Chave Pix:** {SAAS_PIX_CHAVE or '(configure SAAS_PIX_CHAVE)'}\n\n"
            f"👤 **Nome:** {SAAS_PIX_NOME}\n\n"
            f"🏙️ **Cidade:** {SAAS_PIX_CIDADE}\n\n"
            f"🆔 **tenant_id:** {tenant_id}"
        )

        if SAAS_SUPORTE_WHATSAPP:
            msg = f"Olá! Paguei a mensalidade. Email: {user.email} | tenant_id: {tenant_id}"
            link = montar_link_whatsapp(SAAS_SUPORTE_WHATSAPP, msg)
            st.link_button("📲 Enviar comprovante no WhatsApp", link, use_container_width=True)
        else:
            st.warning("Configure no secrets: SAAS_SUPORTE_WHATSAPP (seu WhatsApp do suporte).")

        if st.button("Sair"):
            auth_logout()
        st.stop()

    st.success(f"Acesso liberado ✅ • Loja: **{tenant.get('nome','Minha loja')}**")

    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("Sair"):
            auth_logout()
    with colB:
        base = PUBLIC_APP_BASE_URL or "https://SEUAPP.streamlit.app"
        st.caption("Seu link para clientes:")
        st.code(f"{base}/?t={tenant_id}")

    st.divider()

    st.subheader("👩‍💼 Meu perfil")
    profile = carregar_profile(access_token)
    if not profile:
        st.error("Não foi possível carregar seu perfil.")
    else:
        nome = st.text_input("Nome da profissional", value=profile.get("nome") or "")
        whatsapp = st.text_input("WhatsApp (somente números)", value=profile.get("whatsapp") or "")
        pix_chave = st.text_input("Chave Pix", value=profile.get("pix_chave") or "")
        pix_nome = st.text_input("Nome do Pix", value=profile.get("pix_nome") or "")
        pix_cidade = st.text_input("Cidade do Pix", value=profile.get("pix_cidade") or "")

        if st.button("💾 Salvar dados do perfil"):
            salvar_profile(
                access_token,
                {
                    "nome": nome.strip(),
                    "whatsapp": whatsapp.strip(),
                    "pix_chave": pix_chave.strip(),
                    "pix_nome": pix_nome.strip(),
                    "pix_cidade": pix_cidade.strip(),
                }
            )
            st.success("Perfil atualizado com sucesso!")
            st.rerun()

    atualizar_finalizados_admin(access_token, tenant_id)

    st.divider()
    st.subheader("📋 Agendamentos / Reservas")

    df_admin = listar_agendamentos_admin(access_token, tenant_id)
    if df_admin.empty:
        st.info("Nenhum agendamento encontrado.")
        return

    df_admin["Data_dt"] = pd.to_datetime(df_admin["Data"], errors="coerce")
    df_admin["Preço do serviço"] = df_admin["Serviço(s)"].apply(calcular_total_por_texto_servico).astype(float)

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
            marcar_como_pago_admin(access_token, tenant_id, ag_id)
            st.success("Marcado como PAGO ✅")
            st.rerun()

    st.subheader("🗑️ Excluir")
    op_excluir = df_filtrado.apply(
        lambda r: f'#{r["id"]} | {r["Cliente"]} | {r["Data"]} | {r["Horário"]} | {r["Serviço(s)"]} | {r["Status"]}',
        axis=1
    ).tolist()

    if op_excluir:
        escolha_exc = st.selectbox("Selecione", op_excluir, key="sel_exc")
        if st.button("Excluir ❌"):
            ag_id = int(escolha_exc.split("|")[0].replace("#", "").strip())
            excluir_agendamento_admin(access_token, tenant_id, ag_id)
            st.success("Excluído ✅")
            st.rerun()

# ============================================================
# ROUTER
# ============================================================
if IS_PUBLIC:
    tela_publica()
else:
    tela_admin()
