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
# STREAMLIT CONFIG + THEME (Agenda-Pro)
# ============================================================
st.set_page_config(
    page_title="Agenda-Pro",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed",
)

def apply_theme():
    st.markdown(
        """
        <style>
        :root{
            --bg0: #070B12;
            --bg1: #0B1220;
            --card: rgba(255,255,255,.04);
            --stroke: rgba(255,255,255,.10);
            --stroke2: rgba(255,255,255,.16);
            --text: rgba(255,255,255,.92);
            --muted: rgba(255,255,255,.66);
            --primary: #38BDF8;
            --success: #22C55E;
            --shadow: 0 10px 30px rgba(0,0,0,.35);
        }

        .stApp{
            background:
              radial-gradient(1200px 600px at 10% 0%, rgba(56,189,248,.12), transparent 55%),
              radial-gradient(1000px 520px at 80% 10%, rgba(34,197,94,.10), transparent 60%),
              linear-gradient(180deg, var(--bg0), var(--bg1));
            color: var(--text);
        }

        .block-container{
            padding-top: 2.2rem;
            padding-bottom: 2.8rem;
            max-width: 1100px;
        }

        h1, h2, h3{ letter-spacing: .2px; }
        .muted{ color: var(--muted); }

        div[data-testid="stVerticalBlockBorderWrapper"]{
            background: linear-gradient(180deg, var(--card), rgba(255,255,255,.02));
            border: 1px solid var(--stroke);
            border-radius: 18px;
            box-shadow: var(--shadow);
        }

        button[data-baseweb="tab"]{
            background: transparent !important;
            color: var(--muted) !important;
            border-radius: 14px !important;
            padding: 10px 14px !important;
        }
        button[data-baseweb="tab"][aria-selected="true"]{
            color: var(--text) !important;
            border: 1px solid var(--stroke2) !important;
            background: rgba(56,189,248,.08) !important;
        }

        input, textarea{
            background: rgba(255,255,255,.04) !important;
            border: 1px solid var(--stroke) !important;
            color: var(--text) !important;
            border-radius: 14px !important;
        }

        .stButton > button, .stDownloadButton > button, .stLinkButton > a{
            border-radius: 14px !important;
            border: 1px solid var(--stroke2) !important;
            background: rgba(255,255,255,.04) !important;
            color: var(--text) !important;
            padding: 0.65rem 0.9rem !important;
            transition: all .15s ease-in-out;
        }
        .stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover{
            transform: translateY(-1px);
            border-color: rgba(56,189,248,.55) !important;
            background: rgba(56,189,248,.10) !important;
        }

        div[data-testid="stMetric"]{
            background: rgba(255,255,255,.03);
            border: 1px solid var(--stroke);
            border-radius: 16px;
            padding: 14px 14px 10px 14px;
        }

        details{
            background: rgba(255,255,255,.03) !important;
            border: 1px solid var(--stroke) !important;
            border-radius: 16px !important;
            box-shadow: var(--shadow);
        }
        details summary{
            padding: 12px 14px !important;
            font-weight: 800 !important;
            color: var(--text) !important;
        }

        hr{ border-color: rgba(255,255,255,.10) !important; }

        .chip{
            display: inline-flex;
            gap: 8px;
            align-items: center;
            padding: 6px 10px;
            border: 1px solid var(--stroke);
            border-radius: 999px;
            background: rgba(255,255,255,.03);
            color: var(--muted);
            font-size: 0.9rem;
        }
        .chip b{ color: var(--text); }
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_theme()

# ============================================================
# SECRETS
# ============================================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

URL_RESERVAR = st.secrets.get("URL_RESERVAR", "").strip()
URL_HORARIOS = st.secrets.get("URL_HORARIOS", "").strip()
URL_TENANT_PUBLIC = st.secrets.get("URL_TENANT_PUBLIC", "").strip()
URL_CREATE_TENANT = st.secrets.get("URL_CREATE_TENANT", "").strip()

TRIAL_DIAS = int(st.secrets.get("TRIAL_DIAS", 7))
TEMPO_EXPIRACAO_MIN = int(st.secrets.get("TEMPO_EXPIRACAO_MIN", 60))
PUBLIC_APP_BASE_URL = st.secrets.get("PUBLIC_APP_BASE_URL", "").strip()

SAAS_PIX_CHAVE = st.secrets.get("SAAS_PIX_CHAVE", "").strip()
SAAS_PIX_NOME = st.secrets.get("SAAS_PIX_NOME", "Suporte").strip()
SAAS_PIX_CIDADE = st.secrets.get("SAAS_PIX_CIDADE", "BRASIL").strip()
SAAS_MENSAL_VALOR = st.secrets.get("SAAS_MENSAL_VALOR", "R$ 39,90").strip()
SAAS_SUPORTE_WHATSAPP = st.secrets.get("SAAS_SUPORTE_WHATSAPP", "").strip()

# ============================================================
# DEFAULTS (serviços + horários)
# ============================================================
DEFAULT_SERVICES = {
    "Corte de cabelo": 50.0,
    "Barba": 30.0,
    "Manicure": 40.0,
    "Pedicure": 50.0,
    "Tatuagem (pequena)": 150.0,
}

DEFAULT_WORKING_HOURS = {
    "0": ["09:00", "10:00", "15:00"],
    "1": ["09:00", "10:00", "15:00"],
    "2": ["09:00", "10:00", "15:00"],
    "3": ["09:00", "10:00", "15:00"],
    "4": ["09:00", "10:00", "15:00"],
    "5": ["09:00", "10:00", "15:00"],
    "6": [],
}

VALOR_SINAL_FIXO = 20.0

# ============================================================
# SUPABASE CLIENTS
# ============================================================
def sb_anon():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def sb_user(access_token: str):
    sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sb.postgrest.auth(access_token)
    return sb

# ============================================================
# HELPERS
# ============================================================
def parse_dt(dt_str: str):
    if not dt_str:
        return None
    try:
        dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None

def agora_utc():
    return datetime.now(timezone.utc)

def agora_local():
    return datetime.now(LOCAL_TZ)

def agendamento_dt_local(data_str: str, horario_str: str):
    try:
        d = datetime.strptime(str(data_str), "%Y-%m-%d").date()
        hh, mm = str(horario_str).split(":")
        return datetime(d.year, d.month, d.day, int(hh), int(mm), 0, tzinfo=LOCAL_TZ)
    except Exception:
        return None

def parse_date_iso(d):
    if not d:
        return None
    try:
        return date.fromisoformat(str(d))
    except Exception:
        return None

def fmt_brl(v: float) -> str:
    s = f"{float(v):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def normalizar_servicos(servicos):
    return [s.strip() for s in servicos if s and str(s).strip()]

def servicos_para_texto(servicos):
    return " + ".join(normalizar_servicos(servicos))

def texto_para_lista_servicos(texto: str):
    if not texto:
        return []
    parts = [p.strip() for p in texto.split("+")]
    return [p for p in parts if p]

def calcular_total_servicos(servicos, services_map):
    total = 0.0
    for s in normalizar_servicos(servicos):
        total += float(services_map.get(s, 0.0))
    return float(total)

def calcular_sinal(_servicos):
    return float(VALOR_SINAL_FIXO)

def validar_hhmm(h: str) -> bool:
    try:
        hh, mm = h.split(":")
        hh = int(hh)
        mm = int(mm)
        return 0 <= hh <= 23 and 0 <= mm <= 59
    except Exception:
        return False

def unique_sorted_times(times):
    clean = []
    seen = set()
    for t in times:
        t = str(t).strip()
        if not t:
            continue
        if not validar_hhmm(t):
            continue
        if t not in seen:
            seen.add(t)
            clean.append(t)
    return sorted(clean)

# ============================================================
# EDGE FUNCTIONS HELPERS
# ============================================================
def fn_headers():
    return {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    }

def assert_edge_config(must_have_create: bool = False):
    missing = []
    if not URL_TENANT_PUBLIC:
        missing.append("URL_TENANT_PUBLIC")
    if not URL_RESERVAR:
        missing.append("URL_RESERVAR")
    if not URL_HORARIOS:
        missing.append("URL_HORARIOS")
    if must_have_create and (not URL_CREATE_TENANT):
        missing.append("URL_CREATE_TENANT")
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

if "show_profile" not in st.session_state:
    st.session_state.show_profile = False
if "show_copy" not in st.session_state:
    st.session_state.show_copy = False
if "show_hours" not in st.session_state:
    st.session_state.show_hours = False
if "show_services" not in st.session_state:
    st.session_state.show_services = False

# ============================================================
# AUTH (ADMIN)
# ============================================================
def auth_signup(email: str, password: str):
    sb = sb_anon()
    return sb.auth.sign_up({"email": email, "password": password})

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
def carregar_profile(access_token: str):
    sb = sb_user(access_token)
    try:
        uid = sb.auth.get_user(access_token).user.id
        resp = (
            sb.table("profiles")
            .select("id,email,nome,whatsapp,pix_chave,pix_nome,pix_cidade")
            .eq("id", uid)
            .single()
            .execute()
        )
        return resp.data
    except Exception:
        return None

def salvar_profile(access_token: str, dados: dict):
    sb = sb_user(access_token)
    uid = sb.auth.get_user(access_token).user.id
    return sb.table("profiles").update(dados).eq("id", uid).execute()

# ============================================================
# TENANT SETTINGS (JSON em tenants.settings)
# ============================================================
def get_tenant_settings_admin(access_token: str, tenant_id: str):
    sb = sb_user(access_token)
    try:
        resp = sb.table("tenants").select("settings").eq("id", tenant_id).single().execute()
        data = resp.data or {}
        s = data.get("settings")
        if isinstance(s, dict):
            return s
        return {}
    except Exception:
        return {}

def save_tenant_settings_admin(access_token: str, tenant_id: str, settings: dict):
    sb = sb_user(access_token)
    try:
        sb.table("tenants").update({"settings": settings}).eq("id", tenant_id).execute()
        return True, ""
    except Exception as e:
        return False, str(e)

def settings_get_services(settings: dict):
    s = settings.get("services")
    if isinstance(s, dict) and s:
        out = {}
        for k, v in s.items():
            try:
                out[str(k)] = float(v)
            except Exception:
                continue
        return out if out else DEFAULT_SERVICES.copy()
    return DEFAULT_SERVICES.copy()

def settings_get_working_hours(settings: dict):
    wh = settings.get("working_hours")
    if isinstance(wh, dict):
        out = {}
        for k, v in wh.items():
            if isinstance(v, list):
                out[str(k)] = unique_sorted_times(v)
            else:
                out[str(k)] = []
        for i in range(7):
            out.setdefault(str(i), DEFAULT_WORKING_HOURS.get(str(i), []))
        return out
    return DEFAULT_WORKING_HOURS.copy()

# ============================================================
# TENANT LOAD (público / admin)
# ============================================================
def carregar_tenant_publico(tenant_id: str):
    assert_edge_config()
    try:
        resp = requests.post(
            URL_TENANT_PUBLIC,
            headers=fn_headers(),
            json={"tenant_id": str(tenant_id)},
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if isinstance(payload, dict) and isinstance(payload.get("tenant"), dict):
            return payload["tenant"]
        return None
    except Exception:
        return None

def carregar_tenant_admin(access_token: str):
    sb = sb_user(access_token)
    try:
        uid = sb.auth.get_user(access_token).user.id
        resp = (
            sb.table("tenants")
            .select("id,nome,ativo,paid_until,billing_status,whatsapp_numero,pix_chave,pix_nome,pix_cidade,whatsapp,owner_user_id")
            .eq("owner_user_id", uid)
            .maybe_single()
            .execute()
        )
        return resp.data if resp and resp.data else None
    except Exception:
        return None

def criar_tenant_se_nao_existir(access_token: str):
    user = get_auth_user(access_token)
    if not user:
        return {"ok": False, "error": "user_not_found"}
    assert_edge_config(must_have_create=True)
    try:
        resp = requests.post(
            URL_CREATE_TENANT,
            headers=fn_headers(),
            json={"user_id": str(user.id)},
            timeout=12,
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
def horarios_ocupados_publico(tenant_id: str, data_escolhida: date):
    assert_edge_config()
    try:
        resp = requests.post(
            URL_HORARIOS,
            headers=fn_headers(),
            json={"tenant_id": str(tenant_id), "data": data_escolhida.isoformat()},
            timeout=12,
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
    servicos: list,
    valor_sinal: float,
):
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
        resp = requests.post(URL_RESERVAR, headers=fn_headers(), json=payload, timeout=12)
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

    df.rename(
        columns={
            "cliente": "Cliente",
            "data": "Data",
            "horario": "Horário",
            "servico": "Serviço(s)",
            "status": "Status",
            "valor": "Sinal",
            "created_at": "Criado em",
        },
        inplace=True,
    )
    df["Data"] = df["Data"].astype(str)
    df["Horário"] = df["Horário"].astype(str)
    df["Status"] = df["Status"].astype(str)
    df["Sinal"] = df["Sinal"].apply(lambda x: float(x) if x is not None else 0.0)
    return df

def marcar_como_pago_admin(access_token: str, tenant_id: str, ag_id: int):
    sb = sb_user(access_token)
    return sb.table("agendamentos").update({"status": "pago"}).eq("tenant_id", str(tenant_id)).eq("id", ag_id).execute()

def excluir_agendamento_admin(access_token: str, tenant_id: str, ag_id: int):
    sb = sb_user(access_token)
    return sb.table("agendamentos").delete().eq("tenant_id", str(tenant_id)).eq("id", ag_id).execute()

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
    nome,
    data_atendimento: date,
    horario,
    servicos: list,
    valor_sinal: float,
    pix_chave: str,
    pix_nome: str,
    pix_cidade: str,
    services_map: dict,
):
    servs = normalizar_servicos(servicos)
    total = calcular_total_servicos(servs, services_map)
    lista = "\n".join([f"• {s} ({fmt_brl(services_map.get(s, 0.0))})" for s in servs]) if servs else "-"
    msg = (
        "Olá! Quero agendar um atendimento.\n\n"
        f"👤 Cliente: {nome}\n"
        f"📅 Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
        f"⏰ Horário: {horario}\n"
        "🧾 Serviço(s):\n"
        f"{lista}\n\n"
        f"💰 Total: {fmt_brl(total)}\n"
        f"✅ Sinal: {fmt_brl(valor_sinal)}\n\n"
        "Pix para pagamento do sinal:\n"
        f"🔑 Chave Pix: {pix_chave}\n"
        f"👤 Nome: {pix_nome}\n"
        f"🏙️ Cidade: {pix_cidade}\n\n"
        "📌 Após pagar, envie o comprovante aqui para eu confirmar como PAGO. 🙏"
    )
    return msg

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
# HORÁRIOS (usando settings)
# ============================================================
WEEKDAY_LABELS = {
    "0": "Segunda",
    "1": "Terça",
    "2": "Quarta",
    "3": "Quinta",
    "4": "Sexta",
    "5": "Sábado",
    "6": "Domingo",
}

def horarios_do_dia_com_settings(d: date, working_hours: dict):
    wd = str(d.weekday())
    return working_hours.get(wd, [])

# ============================================================
# MENU (expander) com 4 itens
# ============================================================
def menu_topo_comandos(access_token: str, tenant_id: str):
    settings = get_tenant_settings_admin(access_token, tenant_id)
    services_map = settings_get_services(settings)
    working_hours = settings_get_working_hours(settings)

    base = PUBLIC_APP_BASE_URL or "https://SEUAPP.streamlit.app"
    link_cliente = f"{base}/?t={tenant_id}"

    with st.expander("☰ Menu rápido", expanded=False):
        st.caption("Ações do seu painel (perfil, link, horários e serviços).")

        if st.button("👤 Meu perfil", use_container_width=True):
            st.session_state.show_profile = True
            st.session_state.show_copy = False
            st.session_state.show_hours = False
            st.session_state.show_services = False

        if st.button("🔗 Copiar link do cliente", use_container_width=True):
            st.session_state.show_copy = True
            st.session_state.show_profile = False
            st.session_state.show_hours = False
            st.session_state.show_services = False

        if st.button("⏰ Horário de trabalho", use_container_width=True):
            st.session_state.show_hours = True
            st.session_state.show_profile = False
            st.session_state.show_copy = False
            st.session_state.show_services = False

        if st.button("🧾 Serviços e valores", use_container_width=True):
            st.session_state.show_services = True
            st.session_state.show_profile = False
            st.session_state.show_copy = False
            st.session_state.show_hours = False

    if st.session_state.show_copy:
        with st.container(border=True):
            st.markdown("### 🔗 Link do cliente")
            st.text_input("Copie o link abaixo", value=link_cliente, key="link_cliente_input")
            st.caption("Dica: clique no campo e use Ctrl+C (no celular: segure e copie).")
            if st.button("Fechar", use_container_width=True):
                st.session_state.show_copy = False
                st.rerun()

    if st.session_state.show_profile:
        with st.container(border=True):
            st.markdown("### 👤 Meu perfil")
            profile = carregar_profile(access_token)
            if not profile:
                st.error("Não foi possível carregar seu perfil.")
                return

            nome = st.text_input("Nome do profissional", value=profile.get("nome") or "")
            whatsapp = st.text_input("WhatsApp (somente números)", value=profile.get("whatsapp") or "")
            pix_chave = st.text_input("Chave Pix", value=profile.get("pix_chave") or "")
            pix_nome = st.text_input("Nome do Pix", value=profile.get("pix_nome") or "")
            pix_cidade = st.text_input("Cidade do Pix", value=profile.get("pix_cidade") or "")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Salvar", use_container_width=True, type="primary"):
                    salvar_profile(
                        access_token,
                        {
                            "nome": nome.strip(),
                            "whatsapp": whatsapp.strip(),
                            "pix_chave": pix_chave.strip(),
                            "pix_nome": pix_nome.strip(),
                            "pix_cidade": pix_cidade.strip(),
                        },
                    )
                    st.success("Perfil atualizado!")
                    st.session_state.show_profile = False
                    st.rerun()
            with c2:
                if st.button("Fechar", use_container_width=True):
                    st.session_state.show_profile = False
                    st.rerun()

    if st.session_state.show_hours:
        with st.container(border=True):
            st.markdown("### ⏰ Horário de trabalho")
            st.caption("Digite horários no formato **HH:MM**, separados por vírgula. Ex: 09:00, 10:00, 15:00")

            edited = {}
            invalids = []

            for k in ["0", "1", "2", "3", "4", "5", "6"]:
                cur = working_hours.get(k, [])
                txt_default = ", ".join(cur)
                txt = st.text_input(f"{WEEKDAY_LABELS[k]}", value=txt_default, key=f"wh_{k}")
                raw = [t.strip() for t in txt.split(",")] if txt is not None else []
                cleaned = []
                for t in raw:
                    if not t:
                        continue
                    if not validar_hhmm(t):
                        invalids.append(f"{WEEKDAY_LABELS[k]}: {t}")
                    else:
                        cleaned.append(t)
                edited[k] = unique_sorted_times(cleaned)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Salvar horários", use_container_width=True, type="primary"):
                    if invalids:
                        st.error("Há horários inválidos. Corrija antes de salvar:")
                        st.code("\n".join(invalids))
                    else:
                        settings["working_hours"] = edited
                        ok, msg = save_tenant_settings_admin(access_token, tenant_id, settings)
                        if ok:
                            st.success("Horários salvos!")
                            st.session_state.show_hours = False
                            st.rerun()
                        else:
                            st.warning("Não consegui salvar no banco.")
                            st.code(msg)
            with c2:
                if st.button("Fechar", use_container_width=True):
                    st.session_state.show_hours = False
                    st.rerun()

    if st.session_state.show_services:
        with st.container(border=True):
            st.markdown("### 🧾 Serviços e valores")
            st.caption("Edite a lista e clique em salvar. Você pode adicionar linhas (dinâmico).")

            df = pd.DataFrame([{"Servico": k, "Valor": float(v)} for k, v in services_map.items()])
            df = df.sort_values("Servico").reset_index(drop=True)

            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Servico": st.column_config.TextColumn("Serviço"),
                    "Valor": st.column_config.NumberColumn("Valor", min_value=0.0, step=1.0, format="%.2f"),
                },
                key="services_editor",
            )

            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Salvar serviços", use_container_width=True, type="primary"):
                    new_map = {}
                    errors = []

                    for _, row in edited_df.iterrows():
                        name = str(row.get("Servico") or "").strip()
                        val = row.get("Valor")

                        if not name:
                            continue
                        try:
                            fval = float(val)
                            if fval < 0:
                                errors.append(f"Valor negativo em: {name}")
                                continue
                            new_map[name] = fval
                        except Exception:
                            errors.append(f"Valor inválido em: {name}")

                    if not new_map:
                        errors.append("Você precisa ter pelo menos 1 serviço.")

                    if errors:
                        st.error("Corrija antes de salvar:")
                        st.code("\n".join(errors))
                    else:
                        settings["services"] = new_map
                        ok, msg = save_tenant_settings_admin(access_token, tenant_id, settings)
                        if ok:
                            st.success("Serviços salvos!")
                            st.session_state.show_services = False
                            st.rerun()
                        else:
                            st.warning("Não consegui salvar no banco.")
                            st.code(msg)

            with c2:
                if st.button("Fechar", use_container_width=True):
                    st.session_state.show_services = False
                    st.rerun()

# ============================================================
# UI: MODO PÚBLICO (CLIENTE)
# ============================================================
def tela_publica():
    tenant = carregar_tenant_publico(PUBLIC_TENANT_ID)
    if not tenant:
        st.error("Este link não é válido, não existe ou não está público ainda.")
        st.stop()

    nome_raw = (tenant.get("nome") or "").strip()
    if not nome_raw or nome_raw.lower() in ("minha loja", "minha agenda"):
      nome_prof = "Profissional"
    else:
      nome_prof = nome_raw


    # ✅ CLIENTE: sem slogan/marketing do produto
    st.markdown(f"##            **{nome_prof}**")
    st.caption("Escolha o serviço, o dia e o horário disponível.")

    if not tenant.get("pode_operar", False):
        st.error("🔒 Agenda indisponível (assinatura vencida ou conta inativa).")
        st.stop()

    whatsapp_num = (tenant.get("whatsapp_numero") or "").strip()
    pix_chave = (tenant.get("pix_chave") or "").strip()
    pix_nome = (tenant.get("pix_nome") or "Profissional").strip()
    pix_cidade = (tenant.get("pix_cidade") or "BRASIL").strip()

    if not whatsapp_num:
        st.warning("WhatsApp deste profissional não configurado.")

    settings = tenant.get("settings") if isinstance(tenant.get("settings"), dict) else {}
    services_map = settings_get_services(settings)
    working_hours = settings_get_working_hours(settings)

    aba_agendar, aba_catalogo = st.tabs(["📅 Agendamento", "📒 Catálogo"])

    with aba_agendar:
        st.subheader("Agendar")

        nome = st.text_input("Seu nome")
        data_atendimento = st.date_input("Data do atendimento", min_value=date.today())

        servicos_escolhidos = st.multiselect(
            "Escolha o serviço (pode selecionar mais de um)",
            options=list(services_map.keys()),
            default=[],
        )
        servicos_escolhidos = normalizar_servicos(servicos_escolhidos)

        total_servico = calcular_total_servicos(servicos_escolhidos, services_map)
        valor_sinal = calcular_sinal(servicos_escolhidos)

        if servicos_escolhidos:
            st.caption(f"Total: **{fmt_brl(total_servico)}** • Sinal: **{fmt_brl(valor_sinal)}**")
        else:
            st.caption(f"Sinal: **{fmt_brl(valor_sinal)}**")

        horarios = horarios_do_dia_com_settings(data_atendimento, working_hours)
        if not horarios:
            disponiveis = []
        else:
            ocupados = horarios_ocupados_publico(PUBLIC_TENANT_ID, data_atendimento)
            disponiveis = [h for h in horarios if h not in ocupados]

        st.markdown("**Horários disponíveis**")
        if disponiveis:
            horario_escolhido = st.radio("Escolha um horário", disponiveis, label_visibility="collapsed")
        else:
            horario_escolhido = None
            st.info("Sem horários disponíveis para esse dia. Escolha outra data.")

        st.divider()

        pode_agendar = bool(disponiveis) and bool(servicos_escolhidos) and (not st.session_state.reservando)

        left, right = st.columns([1.2, 1])
        with left:
            reservar_click = st.button(
                "✅ Reservar horário",
                use_container_width=True,
                disabled=not pode_agendar,
                type="primary",
            )
        with right:
            if st.session_state.wa_link:
                st.link_button("📲 Abrir WhatsApp", st.session_state.wa_link, use_container_width=True)

        def make_reserva_key(_nome: str, data_at: date, horario: str, servicos: list) -> str:
            serv_txt = servicos_para_texto(servicos).lower()
            return f"{_nome.strip().lower()}|{data_at.isoformat()}|{horario}|{serv_txt}"

        if reservar_click:
            if not nome or not horario_escolhido or not servicos_escolhidos:
                st.error("Preencha todos os campos e selecione pelo menos 1 serviço.")
            elif not whatsapp_num:
                st.error("Este profissional ainda não configurou WhatsApp para receber a reserva.")
            else:
                st.session_state.reservando = True
                chave = make_reserva_key(nome, data_atendimento, horario_escolhido, servicos_escolhidos)

                if st.session_state.ultima_chave_reserva == chave:
                    st.warning("Você já enviou esse agendamento. Se quiser mudar, fale com o profissional.")
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
                            valor_sinal,
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
                                pix_cidade=pix_cidade,
                                services_map=services_map,
                            )
                            st.session_state.wa_link = montar_link_whatsapp(whatsapp_num, mensagem)
                            st.session_state.ultima_chave_reserva = chave
                            st.session_state.reservando = False
                            st.success("Reserva criada como **PENDENTE**. Clique em **Abrir WhatsApp** para enviar a mensagem.")
                            st.rerun()

    with aba_catalogo:
        st.subheader("📒 Catálogo")
        try:
            with open(CATALOGO_PDF, "rb") as f:
                st.download_button("⬇️ Baixar catálogo (PDF)", data=f, file_name="catalogo.pdf", mime="application/pdf")
        except FileNotFoundError:
            st.info("Sem catálogo configurado.")
        else:
            with st.spinner("Carregando catálogo..."):
                paginas = pdf_para_imagens_com_fundo_branco(CATALOGO_PDF, zoom=2.0)
            for i, img_bytes in enumerate(paginas, start=1):
                st.markdown(f"**Página {i}**")
                st.image(img_bytes, use_container_width=True)

# ============================================================
# UI: MODO ADMIN (PROFISSIONAL)
# ============================================================
def tela_admin():
    # ✅ PROFISSIONAL: mostra hero / marketing do produto
    st.markdown(
        """
        <div style="padding:14px 6px 10px 6px;">
          <div class="chip">📌 <span>Agendamentos online para <b>qualquer profissional</b></span></div>
          <h1 style="margin-top:10px;">📅 Agenda-Pro</h1>
          <div class="muted" style="font-size:1.05rem; margin-top:4px;">
            Organize seus atendimentos, compartilhe seu link e confirme reservas com facilidade.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.access_token:
        tab1, tab2 = st.tabs(["Entrar", "Criar conta"])

        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Senha", type="password", key="login_pass")
            if st.button("Entrar", type="primary"):
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
            if st.button("Criar conta", type="primary"):
                try:
                    auth_signup(email, password)
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
        st.warning("Você ainda não tem um perfil/agenda criada.")
        st.info("Criando automaticamente...")
        out = criar_tenant_se_nao_existir(access_token)
        if not out or (isinstance(out, dict) and out.get("ok") is False):
            st.error("Falhou ao criar tenant automaticamente.")
            if isinstance(out, dict):
                st.code(out)
            st.stop()
        st.success("Agenda criada! Recarregando...")
        st.rerun()

    tenant = carregar_tenant_admin(access_token)
    if not tenant:
        st.error("Não consegui carregar o tenant deste usuário.")
        st.stop()

    tenant_id = str(tenant.get("id"))

    menu_topo_comandos(access_token, tenant_id)

    # Bloqueio SaaS (mantido)
    paid_until = parse_date_iso(tenant.get("paid_until"))
    hoje = date.today()
    pago = bool(paid_until and paid_until >= hoje)
    ativo = (tenant.get("ativo") is not False)
    billing_ok = (tenant.get("billing_status") in (None, "active", "trial"))

    if (not ativo) or (not pago) or (not billing_ok):
        st.error("🔒 Assinatura mensal pendente")
        if paid_until:
            st.caption(f"Venceu em **{paid_until.strftime('%d/%m/%Y')}**.")
        st.stop()

    st.success("Acesso liberado ✅")

    if st.button("Sair", use_container_width=True):
        auth_logout()

    atualizar_finalizados_admin(access_token, tenant_id)

    st.divider()
    st.subheader("📋 Agendamentos / Reservas")

    df_admin = listar_agendamentos_admin(access_token, tenant_id)
    if df_admin.empty:
        st.info("Nenhum agendamento encontrado.")
        return

    df_admin["Data_dt"] = pd.to_datetime(df_admin["Data"], errors="coerce")

    settings = get_tenant_settings_admin(access_token, tenant_id)
    services_map = settings_get_services(settings)

    def total_from_text(texto_servico: str) -> float:
        servs = texto_para_lista_servicos(texto_servico)
        return calcular_total_servicos(servs, services_map)

    df_admin["Preço do serviço"] = df_admin["Serviço(s)"].apply(total_from_text).astype(float)

    colp1, colp2, colp3 = st.columns([1, 1, 1])
    with colp1:
        periodo = st.selectbox("Período", ["Tudo", "Mês", "Ano"], index=0)

    anos_disponiveis = sorted([int(y) for y in df_admin["Data_dt"].dropna().dt.year.unique().tolist()])
    ano_padrao = anos_disponiveis[-1] if anos_disponiveis else date.today().year

    with colp2:
        ano_sel = st.selectbox(
            "Ano",
            anos_disponiveis if anos_disponiveis else [ano_padrao],
            index=(len(anos_disponiveis) - 1) if anos_disponiveis else 0,
        )

    with colp3:
        mes_sel = st.selectbox("Mês", list(range(1, 13)), index=date.today().month - 1)

    df_filtrado = df_admin.copy()
    if periodo == "Mês":
        df_filtrado = df_filtrado[
            (df_filtrado["Data_dt"].dt.year == int(ano_sel))
            & (df_filtrado["Data_dt"].dt.month == int(mes_sel))
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

    m1, m2, m3 = st.columns(3)
    m1.metric("Quantidade", f"{qtd}")
    m2.metric("Total serviços", fmt_brl(total_servicos))
    m3.metric("Total sinais", fmt_brl(total_sinais))

    df_show = df_filtrado.drop(columns=["Data_dt"]).copy()
    df_show["Preço do serviço"] = df_show["Preço do serviço"].apply(lambda v: fmt_brl(float(v)))
    df_show["Sinal"] = df_show["Sinal"].apply(lambda v: fmt_brl(float(v)))
    st.dataframe(
    df_show.drop(columns=["id"]),
    use_container_width=True,
    height=360  # <- importante: não deixa a tabela "tomar" o scroll da página
    )
    st.divider()
st.subheader("⚡ Ações rápidas")

# =========================
# MARCAR COMO PAGO
# =========================
st.subheader("✅ Marcar como PAGO")

ag_pagar = st.selectbox(
    "Selecione o agendamento",
    df_admin["id"],
    format_func=lambda x: (
        f"{df_admin[df_admin.id == x]['Cliente'].values[0]} • "
        f"{df_admin[df_admin.id == x]['Data'].values[0]} "
        f"{df_admin[df_admin.id == x]['Horário'].values[0]}"
    ),
    key="pagar_select",
)

if st.button("Marcar como PAGO", type="primary"):
    marcar_como_pago_admin(access_token, tenant_id, int(ag_pagar))
    st.success("Agendamento marcado como PAGO.")
    st.rerun()

# =========================
# EXCLUIR AGENDAMENTO
# =========================
st.subheader("🗑️ Excluir agendamento")

ag_excluir = st.selectbox(
    "Selecione para excluir",
    df_admin["id"],
    format_func=lambda x: (
        f"{df_admin[df_admin.id == x]['Cliente'].values[0]} • "
        f"{df_admin[df_admin.id == x]['Data'].values[0]} "
        f"{df_admin[df_admin.id == x]['Horário'].values[0]}"
    ),
    key="excluir_select_unique",
)

if st.button("Excluir agendamento", type="secondary"):
    excluir_agendamento_admin(access_token, tenant_id, int(ag_excluir))
    st.warning("Agendamento excluído.")
    st.rerun()




# ============================================================
# ROUTER
# ============================================================
if IS_PUBLIC:
    tela_publica()
else:
    tela_admin()
