import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import date, datetime, timedelta, timezone
import urllib.parse
import requests
import fitz  # PyMuPDF
from PIL import Image
import io
import re
import unicodedata
from supabase import create_client
from streamlit_js_eval import get_page_location

# 👇 Só depois começa o resto do app
if "page" not in st.session_state:
    st.session_state["page"] = "login"

# ============================================================
# RECOVERY MODE (reset de senha via Supabase)
# ============================================================
def handle_recovery_token():
    params = st.experimental_get_query_params()

    # quando o Supabase usa query (?access_token=)
    if "access_token" in params:
        st.session_state.access_token = params["access_token"][0]
        st.query_params.clear()
        return True

    # quando vem via hash (#access_token=) — Streamlit não lê direto
    try:
        from streamlit_js_eval import streamlit_js_eval

        token = streamlit_js_eval(
            js_expressions="window.location.hash",
            want_output=True,
            key="hash_eval",
        )

        if token and "access_token=" in token:
            parts = token.replace("#", "").split("&")
            data = dict(p.split("=") for p in parts if "=" in p)

            if "access_token" in data:
                st.session_state.access_token = data["access_token"]
                streamlit_js_eval(
                    js_expressions="window.location.hash = ''",
                    want_output=False,
                )
                return True
    except Exception:
        pass

    return False

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

st.markdown("""
<style>

/* Esconde header */
header {visibility: hidden;}

/* Esconde menu */
#MainMenu {visibility: hidden;}

/* Esconde rodapé padrão */
footer {visibility: hidden;}

/* Esconde badge "Built with Streamlit" */
div[data-testid="stStatusWidget"] {
    display: none !important;
}

/* Esconde container inferior do Streamlit Cloud */
.viewerBadge_container__1QSob {
    display: none !important;
}

/* Remove espaço inferior */
.block-container {
    padding-bottom: 6.5rem !important; /* space for fixed CTA (mobile) */
}
@media (min-width: 900px){
  .block-container{ padding-bottom: 5.0rem !important; }
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
iframe {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

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
            border-color: rgba(56, 189, 248, .55) !important;
            background: rgba(56, 189, 248, .10) !important;
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

        /* ===============================
           FIX iOS / SAFARI INPUTS
           =============================== */
        input,
        textarea,
        .stTextInput input,
        .stTextInput textarea {
          background-color: rgba(15, 23, 42, 0.95) !important;
          color: #FFFFFF !important;
          -webkit-text-fill-color: #FFFFFF !important;
          caret-color: #FFFFFF !important;
        }

        input:-webkit-autofill,
        textarea:-webkit-autofill {
            -webkit-box-shadow: 0 0 0px 1000px rgba(15, 23, 42, 0.95) inset !important;
            box-shadow: 0 0 0px 1000px rgba(15, 23, 42, 0.95) inset !important;
            -webkit-text-fill-color: #FFFFFF !important;
            caret-color: #FFFFFF !important;
        }

        ::placeholder {
          color: rgba(255, 255, 255, 0.55) !important;
        }

        input:focus,
        textarea:focus {
          outline: none !important;
          box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.45) !important;
        }

        .chip b{ color: var(--text); }
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_theme()

# ============================================================
# PASSO 1 — Rodapé fixo com botão Sair (sem "espaço vazio")
# ============================================================
st.markdown("""
<style>
.footer-logout {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 14px 16px;
  background: rgba(7, 11, 18, 0.70);
  backdrop-filter: blur(8px);
  border-top: 1px solid rgba(255,255,255,.10);
  z-index: 9999;
}

.footer-logout a {
  display: block;
  text-align: center;
  padding: 12px 14px;
  border-radius: 14px;
  text-decoration: none;
  border: 1px solid rgba(255,255,255,.16);
  background: rgba(255,255,255,.04);
  color: rgba(255,255,255,.92);
  font-weight: 700;
}

.footer-logout a:hover {
  transform: translateY(-1px);
  border-color: rgba(56, 189, 248, .55);
  background: rgba(56, 189, 248, .10);
}

/* espaço para não esconder conteúdo atrás do rodapé */
.block-container { padding-bottom: 110px !important; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# SECRETS
# ============================================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

URL_RESERVAR = st.secrets.get("URL_RESERVAR", "").strip()
URL_HORARIOS = st.secrets.get("URL_HORARIOS", "").strip()
URL_TENANT_PUBLIC = st.secrets.get("URL_TENANT_PUBLIC", "").strip()
URL_CREATE_TENANT = st.secrets.get("URL_CREATE_TENANT", "").strip()
URL_ASSINAR_PLANO = st.secrets.get("URL_ASSINAR_PLANO", "").strip()

TRIAL_DIAS = int(st.secrets.get("TRIAL_DIAS", 7))
TEMPO_EXPIRACAO_MIN = int(st.secrets.get("TEMPO_EXPIRACAO_MIN", 60))
PUBLIC_APP_BASE_URL = st.secrets.get("PUBLIC_APP_BASE_URL", "").strip()

SAAS_PIX_CHAVE = st.secrets.get("SAAS_PIX_CHAVE", "").strip()
SAAS_PIX_NOME = st.secrets.get("SAAS_PIX_NOME", "Suporte").strip()
SAAS_PIX_CIDADE = st.secrets.get("SAAS_PIX_CIDADE", "BRASIL").strip()
SAAS_MENSAL_VALOR = st.secrets.get("SAAS_MENSAL_VALOR", "R$ 1,99").strip()
SAAS_SUPORTE_WHATSAPP = st.secrets.get("SAAS_SUPORTE_WHATSAPP", "").strip()

# Bucket do catálogo (Supabase Storage)
CATALOGO_BUCKET = st.secrets.get("CATALOGO_BUCKET", "catalogos").strip() or "catalogos"

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
# STATUS (Admin + Público)
# ============================================================
STATUS_ALL = ["pendente", "pago", "finalizado", "cancelado"]
STATUS_LABELS = {
    "pendente": "🟡 pendente",
    "pago": "🔵 pago",
    "finalizado": "🟢 finalizado",
    "cancelado": "🔴 cancelado",
}
STATUS_SORT = {"pendente": 0, "pago": 1, "finalizado": 2, "cancelado": 3}

def norm_status(s: str) -> str:
    s = (s or "").strip().lower()
    return s if s in STATUS_ALL else (s or "pendente")

# ============================================================
# SUPABASE CLIENTS
# ============================================================
def sb_anon():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

from supabase import ClientOptions

def sb_user(access_token: str):
    opts = ClientOptions(headers={"Authorization": f"Bearer {access_token}"})
    sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY, options=opts)
    try:
        sb.postgrest.auth(access_token)
    except Exception:
        pass
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

def parse_date_iso(d):
    if not d:
        return None
    try:
        return date.fromisoformat(str(d))
    except Exception:
        return None

def dias_restantes(paid_until) -> int:
    if not paid_until:
        return 0
    if isinstance(paid_until, str):
        try:
            paid = date.fromisoformat(paid_until)
        except Exception:
            return 0
    elif isinstance(paid_until, date):
        paid = paid_until
    else:
        return 0
    return (paid - date.today()).days

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

def calcular_sinal(_servicos, deposit_cfg: dict | None = None):
    """
    Se deposit_cfg["enabled"] == False => sinal = 0
    Caso contrário usa deposit_cfg["value"] ou VALOR_SINAL_FIXO.
    """
    deposit_cfg = deposit_cfg or {"enabled": True, "value": float(VALOR_SINAL_FIXO)}
    if not bool(deposit_cfg.get("enabled", True)):
        return 0.0
    try:
        return float(deposit_cfg.get("value", VALOR_SINAL_FIXO))
    except Exception:
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

def assert_edge_config(must_have_create: bool = False, must_have_assinar: bool = False):
    missing = []
    if not URL_TENANT_PUBLIC:
        missing.append("URL_TENANT_PUBLIC")
    if not URL_RESERVAR:
        missing.append("URL_RESERVAR")
    if not URL_HORARIOS:
        missing.append("URL_HORARIOS")
    if must_have_create and (not URL_CREATE_TENANT):
        missing.append("URL_CREATE_TENANT")
    if must_have_assinar and (not URL_ASSINAR_PLANO):
        missing.append("URL_ASSINAR_PLANO")
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
# TELA DE RESET DE SENHA
# ============================================================
import requests
import streamlit as st
import streamlit.components.v1 as components

def tela_reset_senha():
    st.markdown("## 🔐 Redefinir senha")
    st.caption("Abra este link a partir do email que enviamos.")

    token = st.query_params.get("token")
    typ = st.query_params.get("type")

    if not token or typ != "recovery":
        st.warning("Link inválido ou expirado. Gere um novo pedido de redefinição.")
        st.stop()

    nova = st.text_input("Nova senha", type="password")
    nova2 = st.text_input("Confirmar nova senha", type="password")

    if st.button("Salvar nova senha", type="primary", use_container_width=True):
        if not nova or len(nova) < 6:
            st.error("A senha precisa ter pelo menos 6 caracteres.")
            st.stop()
        if nova != nova2:
            st.error("As senhas não coincidem.")
            st.stop()

        # 1) Troca token_hash por sessão temporária
        verify_url = f"{SUPABASE_URL}/auth/v1/verify"
        r = requests.post(
            verify_url,
            json={"type": "recovery", "token_hash": token},
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )

        if r.status_code != 200:
            st.error("Token inválido/expirado. Gere um novo pedido.")
            st.code(r.text)
            st.stop()

        data = r.json()
        access_token = data.get("access_token")
        if not access_token:
            st.error("Supabase não retornou access_token.")
            st.code(data)
            st.stop()

        # 2) Atualiza a senha via HTTP (sem depender de sessão do client)
        update_url = f"{SUPABASE_URL}/auth/v1/user"
        u = requests.put(
            update_url,
            json={"password": nova},
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )

        if u.status_code not in (200, 204):
            st.error("Não consegui atualizar a senha.")
            st.code(u.text)
            st.stop()

        st.success("✅ Senha atualizada! Agora faça login.")
        st.query_params.clear()
        st.session_state.access_token = None
        st.rerun()

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
if "show_catalog" not in st.session_state:
    st.session_state.show_catalog = False
if "show_deposit" not in st.session_state:
    st.session_state.show_deposit = False
if "payment_url" not in st.session_state:
    st.session_state.payment_url = None

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

def auth_send_reset_email(email: str):
    sb = sb_anon()
    return sb.auth.reset_password_email(
        email,
        {
            "redirect_to": "https://n2zxw5mtfmdyy25d9qgjba.streamlit.app/?reset=1"
        }
    )

def auth_update_password(access_token: str, new_password: str):
    sb = sb_user(access_token)
    return sb.auth.update_user({"password": new_password})

# ============================================================
# PROFILE (ADMIN)
# ============================================================
def carregar_profile(access_token: str):
    sb = sb_user(access_token)
    try:
        u = sb.auth.get_user(access_token).user
        if not u:
            return None

        uid = u.id
        email = u.email or ""

        # tenta buscar
        resp = (
            sb.table("profiles")
            .select("id,email,nome,whatsapp,pix_chave,pix_nome,pix_cidade")
            .eq("id", uid)
            .maybe_single()
            .execute()
        )

        if resp and resp.data:
            return resp.data

        # se não existir, cria automaticamente (primeiro acesso)
        ins = (
            sb.table("profiles")
            .insert(
                {
                    "id": uid,
                    "email": email,
                    "nome": "",
                    "whatsapp": "",
                    "pix_chave": "",
                    "pix_nome": "",
                    "pix_cidade": "",
                }
            )
            .execute()
        )

        # retorna o recém-criado
        return {
            "id": uid,
            "email": email,
            "nome": "",
            "whatsapp": "",
            "pix_chave": "",
            "pix_nome": "",
            "pix_cidade": "",
        }

    except Exception as e:
        # pra você enxergar o erro real quando acontecer
        st.error("Erro ao carregar profile (debug):")
        st.code(str(e))
        return None

def salvar_profile(access_token: str, dados: dict):
    sb = sb_user(access_token)
    uid = sb.auth.get_user(access_token).user.id
    return sb.table("profiles").update(dados).eq("id", uid).execute()

def atualizar_tenant_whatsapp(sb_or_token, uid: str, tenant_id: str, whatsapp: str):
    sb = sb_or_token if hasattr(sb_or_token, "table") else sb_user(sb_or_token)
    w = (whatsapp or "").strip()
    return (
        sb.table("tenants")
        .update({"whatsapp_numero": w, "whatsapp": w})
        .eq("id", str(tenant_id))
        .eq("owner_user_id", uid)
        .execute()
    )

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

# ============================================================
# ONBOARDING (primeira configuração após criar conta)
# ============================================================
def settings_is_onboarding_done(settings: dict) -> bool:
    try:
        return bool(settings.get("onboarding_done", False))
    except Exception:
        return False

def mark_onboarding_done(access_token: str, tenant_id: str, settings: dict):
    settings = dict(settings or {})
    settings["onboarding_done"] = True
    ok, err = save_tenant_settings_admin(access_token, tenant_id, settings)
    return ok, err

def tela_onboarding(access_token: str, tenant: dict):
    """
    Wizard simples para o usuário configurar o básico e começar a usar.
    Mostra apenas quando settings['onboarding_done'] != True.
    """
    tenant_id = str(tenant.get("id"))
    user = get_auth_user(access_token)
    uid = str(getattr(user, "id", "")) if user else ""

    settings = get_tenant_settings_admin(access_token, tenant_id) or {}
    if settings_is_onboarding_done(settings):
        return True  # já concluído

    st.markdown("## 🎉 Bem-vindo ao Agenda‑Pro")
    st.caption("Vamos configurar o básico em menos de 2 minutos.")

    # passo atual
    step = int(st.session_state.get("onboarding_step", 1))
    total_steps = 4
    st.progress(min(step, total_steps) / total_steps)

    # -------- Passo 1: WhatsApp --------
    if step == 1:
        st.markdown("### 1) Seu WhatsApp")
        w_cur = (tenant.get("whatsapp_numero") or "").strip()
        w = st.text_input("Número do WhatsApp (com DDD)", value=w_cur, placeholder="Ex.: 11999999999", key="ob_whats")
        st.caption("Esse número será usado para gerar o link wa.me na confirmação do agendamento.")

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Continuar ➜", type="primary", use_container_width=True):
                ok = True
                if uid:
                    try:
                        atualizar_tenant_whatsapp(access_token, uid, tenant_id, w)
                    except Exception:
                        ok = False
                # mesmo se falhar, deixa seguir (usuário pode ajustar depois)
                st.session_state["onboarding_step"] = 2
                st.rerun()
        with c2:
            if st.button("Pular", use_container_width=True):
                st.session_state["onboarding_step"] = 2
                st.rerun()

        st.stop()

    # -------- Passo 2: Serviços --------
    if step == 2:
        st.markdown("### 2) Cadastre um serviço")
        services = settings_get_services(settings) or {}

        with st.container(border=True):
            with st.form("ob_add_service", clear_on_submit=True):
                s_nome = st.text_input(
                    "Nome do serviço",
                    placeholder="Ex.: Alongamento em gel",
                    key="ob_serv_nome",
                )
                s_preco = st.number_input(
                    "Preço (R$)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key="ob_serv_preco",
                )
                submitted = st.form_submit_button("Adicionar serviço", use_container_width=True)

            if submitted:
                nome = (s_nome or "").strip()
                if not nome:
                    st.error("Digite o nome do serviço.")
                else:
                    settings = dict(settings or {})
                    sdict = dict(settings.get("services") or {})
                    sdict[nome] = float(s_preco or 0.0)
                    settings["services"] = sdict

                    ok, err = save_tenant_settings_admin(access_token, tenant_id, settings)
                    if ok:
                        st.success("✅ Serviço adicionado.")
                        st.rerun()
                    else:
                        st.error("Não consegui salvar. Tente novamente.")
                        st.code(err)

        # recarrega pra mostrar atualizado
        services = settings_get_services(get_tenant_settings_admin(access_token, tenant_id) or {}) or {}
        if services:
            st.caption("Serviços cadastrados:")
            st.write(list(services.keys())[:10])

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("⬅ Voltar", use_container_width=True):
                st.session_state["onboarding_step"] = 1
                st.rerun()
        with c2:
            if st.button("Continuar ➜", type="primary", use_container_width=True):
                st.session_state["onboarding_step"] = 3
                st.rerun()
        with c3:
            if st.button("Pular", use_container_width=True):
                st.session_state["onboarding_step"] = 3
                st.rerun()

        st.stop()

    # -------- Passo 3: Sinal (opcional) --------
    if step == 3:
        st.markdown("### 3) Sinal via Pix (opcional)")
        dep = settings_get_deposit(settings)
        enabled = bool(dep.get("enabled", True))
        value = float(dep.get("value", VALOR_SINAL_FIXO))

        enabled_new = st.toggle("Ativar sinal", value=enabled, key="ob_dep_enabled")
        value_new = st.number_input("Valor do sinal (R$)", min_value=0.0, value=float(value), step=1.0, key="ob_dep_value")
        st.caption("Você pode alterar isso depois nas configurações.")

        if st.button("Salvar e continuar ➜", type="primary", use_container_width=True):
            settings = dict(settings or {})
            settings["deposit"] = {"enabled": bool(enabled_new), "value": float(value_new)}
            ok, err = save_tenant_settings_admin(access_token, tenant_id, settings)
            if ok:
                st.session_state["onboarding_step"] = 4
                st.rerun()
            else:
                st.error("Não consegui salvar. Tente novamente.")
                st.code(err)

        if st.button("⬅ Voltar", use_container_width=True):
            st.session_state["onboarding_step"] = 2
            st.rerun()

        st.stop()

    # -------- Passo 4: Link público --------
    if step == 4:
        st.markdown("### 4) Seu link de agendamento")
        base = st.session_state.get("APP_URL") or ""
        # fallback: tenta montar com location
        if not base:
            try:
                loc = get_page_location()
                base = (loc or {}).get("origin", "")
            except Exception:
                base = ""
        if base:
            link = f"{base}/?t={tenant_id}"
        else:
            link = f"?t={tenant_id}"

        st.write("Copie e cole esse link na sua bio ou envie para seus clientes:")
        st.code(link)

        st.success("Pronto! Você já pode começar a receber agendamentos. ✅")

        if st.button("Concluir", type="primary", use_container_width=True):
            ok, err = mark_onboarding_done(access_token, tenant_id, settings)
            st.session_state.pop("onboarding_step", None)
            if ok:
                st.rerun()
            else:
                st.error("Não consegui finalizar o onboarding.")
                st.code(err)

        st.stop()


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

# ----------------------------
# CATÁLOGO por tenant (settings)
# settings["catalog"] = {
#   "enabled": true,
#   "items": [{"type":"image|pdf","path":"...","url":"...","caption":""}, ...]
# }
# ----------------------------
def settings_get_catalog(settings: dict):
    c = settings.get("catalog")
    if isinstance(c, dict):
        enabled = bool(c.get("enabled", True))
        items = c.get("items")
        if isinstance(items, list):
            clean = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                typ = str(it.get("type") or "image").lower().strip()
                if typ not in ("image", "pdf"):
                    typ = "image"
                url = str(it.get("url") or "").strip()
                path = str(it.get("path") or "").strip()
                caption = str(it.get("caption") or "").strip()
                if url and path:
                    clean.append({"type": typ, "url": url, "path": path, "caption": caption})
            return {"enabled": enabled, "items": clean}
        return {"enabled": enabled, "items": []}
    return {"enabled": True, "items": []}

def settings_set_catalog(settings: dict, enabled: bool, items: list):
    settings["catalog"] = {"enabled": bool(enabled), "items": items}
    return settings

def settings_get_deposit(settings: dict):
    d = settings.get("deposit")
    if isinstance(d, dict):
        enabled = bool(d.get("enabled", True))
        try:
            value = float(d.get("value", VALOR_SINAL_FIXO))
        except Exception:
            value = float(VALOR_SINAL_FIXO)
        if value < 0:
            value = 0.0
        return {"enabled": enabled, "value": value}
    return {"enabled": True, "value": float(VALOR_SINAL_FIXO)}

def settings_set_deposit(settings: dict, enabled: bool, value: float):
    try:
        v = float(value)
    except Exception:
        v = 0.0
    if v < 0:
        v = 0.0
    settings["deposit"] = {"enabled": bool(enabled), "value": v}
    return settings

# ============================================================
# STORAGE (upload / delete) para catálogo (IMAGEM + PDF)
# ============================================================
def guess_content_type(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith(".png"):
        return "image/png"
    if fn.endswith(".webp"):
        return "image/webp"
    if fn.endswith(".pdf"):
        return "application/pdf"
    return "image/jpeg"

def guess_item_type(filename: str) -> str:
    return "pdf" if (filename or "").lower().endswith(".pdf") else "image"

def sanitize_filename(name: str) -> str:
    """
    Normaliza para ASCII + permite apenas caracteres seguros.
    Evita 400 InvalidKey no Storage.
    """
    base = (name or "").strip()
    if not base:
        return "arquivo"

    # remove acentos / normaliza
    base = unicodedata.normalize("NFKD", base)
    base = base.encode("ascii", "ignore").decode("ascii")

    # troca espaços por _
    base = base.replace(" ", "_")

    # remove tudo que não é seguro
    base = re.sub(r"[^A-Za-z0-9._-]", "", base)

    # evita nome vazio
    base = base.strip("._-")
    return base or "arquivo"

def upload_catalog_file(access_token: str, tenant_id: str, uploaded_file):
    """
    Upload direto no Supabase Storage via HTTP (RLS com auth.uid()).
    Salva em: {tenant_id}/{timestamp}_{filename}
    IMPORTANTE: sem x-upsert (não exige UPDATE policy)
    """
    try:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_name = sanitize_filename(uploaded_file.name or "arquivo")
        path = f"{tenant_id}/{ts}_{safe_name}"

        content_type = guess_content_type(safe_name)
        item_type = guess_item_type(safe_name)
        file_bytes = uploaded_file.getvalue()

        url = f"{SUPABASE_URL}/storage/v1/object/{CATALOGO_BUCKET}/{path}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "apikey": SUPABASE_ANON_KEY,
            "Content-Type": str(content_type),
        }

        resp = requests.put(url, headers=headers, data=file_bytes, timeout=30)

        if resp.status_code not in (200, 201):
            try:
                return False, str(resp.json()), {}
            except Exception:
                return False, f"HTTP {resp.status_code}: {resp.text}", {}

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{CATALOGO_BUCKET}/{path}"
        item = {"type": item_type, "path": path, "url": public_url, "caption": ""}
        return True, "", item

    except Exception as e:
        return False, str(e), {}

def delete_catalog_item(access_token: str, path: str):
    try:
        if not path:
            return False, "path vazio"

        url = f"{SUPABASE_URL}/storage/v1/object/{CATALOGO_BUCKET}/{path}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "apikey": SUPABASE_ANON_KEY,
        }

        resp = requests.delete(url, headers=headers, timeout=20)
        if resp.status_code not in (200, 204):
            try:
                return False, str(resp.json())
            except Exception:
                return False, f"HTTP {resp.status_code}: {resp.text}"

        return True, ""
    except Exception as e:
        return False, str(e)

def delete_catalog_all(access_token: str, items: list):
    removed = 0
    errs = []
    for it in list(items or []):
        path = (it or {}).get("path")
        ok, msg = delete_catalog_item(access_token, path)
        if ok:
            removed += 1
        else:
            errs.append(f"{path}: {msg}")
    return removed, errs

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
            status = norm_status(r.get("status"))

            # cancelado NÃO ocupa
            if status == "cancelado":
                continue

            if status in ("pago", "finalizado"):
                ocupados.add(horario)
                continue

            if status == "pendente":
                if TEMPO_EXPIRACAO_MIN <= 0:
                    ocupados.add(horario)
                else:
                    created_at = parse_dt(r.get("created_at", ""))
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
    df["Status"] = df["Status"].astype(str).apply(norm_status)
    df["Sinal"] = df["Sinal"].apply(lambda x: float(x) if x is not None else 0.0)
    return df

def marcar_status_admin(access_token: str, tenant_id: str, ag_id: int, novo_status: str):
    novo_status = norm_status(novo_status)
    sb = sb_user(access_token)
    return (
        sb.table("agendamentos")
        .update({"status": novo_status})
        .eq("tenant_id", str(tenant_id))
        .eq("id", ag_id)
        .execute()
    )

def excluir_agendamento_admin(access_token: str, tenant_id: str, ag_id: int):
    sb = sb_user(access_token)
    return sb.table("agendamentos").delete().eq("tenant_id", str(tenant_id)).eq("id", ag_id).execute()

def atualizar_finalizados_admin(access_token: str, tenant_id: str):
    """
    Converte 'pago' -> 'finalizado' quando o horário já passou.
    (cancelado fica cancelado)
    """
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
    num = "".join([c for c in str(whatsapp_numero or "") if c.isdigit()])
    if num and not num.startswith("55"):
        if len(num) in (10, 11):
            num = "55" + num
    text_encoded = urllib.parse.quote(texto, safe="")
    return f"https://wa.me/{num}?text={text_encoded}"

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
    deposit_cfg: dict | None = None,
):
    """
    Versão SEM emojis para evitar caracteres quebrados ( ) no WhatsApp.
    """
    deposit_cfg = deposit_cfg or {"enabled": True, "value": float(valor_sinal)}
    deposit_on = bool(deposit_cfg.get("enabled", True)) and float(valor_sinal or 0) > 0

    servs = normalizar_servicos(servicos)
    total = calcular_total_servicos(servs, services_map)

    if servs:
        lista = "\n".join([f"- {s} ({fmt_brl(services_map.get(s, 0.0))})" for s in servs])
    else:
        lista = "-"

    msg = (
        "Olá! Quero agendar um atendimento.\n\n"
        f"Cliente: {nome}\n"
        f"Data: {data_atendimento.strftime('%d/%m/%Y')}\n"
        f"Horário: {horario}\n"
        "Serviço(s):\n"
        f"{lista}\n\n"
        f"Total: {fmt_brl(total)}\n"
    )

    if deposit_on:
        msg += (
            f"Sinal: {fmt_brl(valor_sinal)}\n\n"
            "Pix para pagamento do sinal:\n"
            f"Chave Pix: {pix_chave}\n"
            f"Nome: {pix_nome}\n"
            f"Cidade: {pix_cidade}\n\n"
            "Após pagar, envie o comprovante aqui para eu confirmar como PAGO."
        )
    else:
        msg += "\nMe confirme por aqui que eu valido o agendamento."

    # Normaliza unicode antes de retornar (mantém seguro)
    return unicodedata.normalize("NFC", msg)

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
# MENU (expander) com itens
# ============================================================
def menu_topo_comandos(access_token: str, tenant_id: str):
    settings = get_tenant_settings_admin(access_token, tenant_id)
    services_map = settings_get_services(settings)
    working_hours = settings_get_working_hours(settings)

    base = PUBLIC_APP_BASE_URL or "https://SEUAPP.streamlit.app"
    link_cliente = f"{base}/?t={tenant_id}"

    with st.expander("☰ Menu rápido", expanded=False):
        st.caption("Ações do seu painel (perfil, link, horários, serviços e catálogo).")

        if st.button("👤 Meu perfil", use_container_width=True):
            st.session_state.show_profile = True
            st.session_state.show_copy = False
            st.session_state.show_hours = False
            st.session_state.show_services = False
            st.session_state.show_catalog = False
            st.session_state.show_deposit = False

        if st.button("🔗 Copiar link do cliente", use_container_width=True):
            st.session_state.show_copy = True
            st.session_state.show_profile = False
            st.session_state.show_hours = False
            st.session_state.show_services = False
            st.session_state.show_catalog = False
            st.session_state.show_deposit = False

        if st.button("⏰ Horário de trabalho", use_container_width=True):
            st.session_state.show_hours = True
            st.session_state.show_profile = False
            st.session_state.show_copy = False
            st.session_state.show_services = False
            st.session_state.show_catalog = False
            st.session_state.show_deposit = False

        if st.button("🧾 Serviços e valores", use_container_width=True):
            st.session_state.show_services = True
            st.session_state.show_profile = False
            st.session_state.show_copy = False
            st.session_state.show_hours = False
            st.session_state.show_catalog = False
            st.session_state.show_deposit = False

        if st.button("💰 Sinal (opcional)", use_container_width=True):
            st.session_state.show_deposit = True
            st.session_state.show_profile = False
            st.session_state.show_copy = False
            st.session_state.show_hours = False
            st.session_state.show_services = False
            st.session_state.show_catalog = False

        if st.button("📒 Catálogo (fotos/PDF)", use_container_width=True):
            st.session_state.show_catalog = True
            st.session_state.show_profile = False
            st.session_state.show_copy = False
            st.session_state.show_hours = False
            st.session_state.show_services = False
            st.session_state.show_deposit = False

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

            # Foto do perfil (salva em tenants.settings['avatar_url'])
            settings_here = get_tenant_settings_admin(access_token, tenant_id) or {}
            avatar_cur = str(settings_here.get("avatar_url") or settings_here.get("profile_photo_url") or "").strip()

            st.markdown("#### 📷 Foto do perfil")
            if avatar_cur:
                st.image(avatar_cur, width=120)
                st.caption("Dica: use uma foto bem nítida do rosto (melhora a conversão).")

            up_avatar = st.file_uploader(
                "Enviar/atualizar foto (JPG/PNG/WEBP)",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=False,
                key="avatar_upload",
                label_visibility="collapsed",
            )

            def upload_profile_photo(access_token: str, tenant_id: str, uploaded_file):
                """Upload da foto do perfil no Supabase Storage (mesmo bucket do catálogo)."""
                try:
                    ts = datetime.now().strftime("%Y%m%d%H%M%S")
                    safe_name = sanitize_filename(uploaded_file.name or "avatar.jpg")
                    path = f"{tenant_id}/profile/{ts}_{safe_name}"
                    content_type = guess_content_type(safe_name)
                    file_bytes = uploaded_file.getvalue()

                    url = f"{SUPABASE_URL}/storage/v1/object/{CATALOGO_BUCKET}/{path}"
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "apikey": SUPABASE_ANON_KEY,
                        "Content-Type": str(content_type),
                    }
                    resp = requests.put(url, headers=headers, data=file_bytes, timeout=30)
                    if resp.status_code not in (200, 201):
                        try:
                            return False, str(resp.json()), ""
                        except Exception:
                            return False, f"HTTP {resp.status_code}: {resp.text}", ""

                    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{CATALOGO_BUCKET}/{path}"
                    return True, "", public_url
                except Exception as e:
                    return False, str(e), ""

            if up_avatar:
                if st.button("💾 Salvar foto do perfil", use_container_width=True, type="primary"):
                    okp, msgp, urlp = upload_profile_photo(access_token, tenant_id, up_avatar)
                    if okp and urlp:
                        settings_here["avatar_url"] = urlp
                        ok_save, err_save = save_tenant_settings_admin(access_token, tenant_id, settings_here)
                        if ok_save:
                            st.success("✅ Foto atualizada!")
                            st.rerun()
                        else:
                            st.error("Enviei a foto, mas não consegui salvar no banco.")
                            st.code(err_save)
                    else:
                        st.error("Não consegui enviar a foto.")
                        st.code(msgp)

            st.divider()

            nome = st.text_input("Nome da loja", value=profile.get("nome") or "")
            whatsapp = st.text_input("WhatsApp (somente números)", value=profile.get("whatsapp") or "")
            pix_chave = st.text_input("Chave Pix", value=profile.get("pix_chave") or "")
            pix_nome = st.text_input("Nome do Pix", value=profile.get("pix_nome") or "")
            pix_cidade = st.text_input("Cidade do Pix", value=profile.get("pix_cidade") or "")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Salvar", use_container_width=True, type="primary"):
                    sb = sb_user(access_token)
                    uid = sb.auth.get_user(access_token).user.id
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
                    atualizar_tenant_whatsapp(access_token, uid, tenant_id, whatsapp.strip())
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

    # ==========================
    # CATÁLOGO (fotos/PDF) - ADMIN
    # ==========================
    if st.session_state.show_catalog:
        with st.container(border=True):
            st.markdown("### 📒 Catálogo (fotos e PDF)")
            st.caption("Envie fotos do seu trabalho ou um PDF. Aparece automaticamente no seu link público.")

            catalog = settings_get_catalog(settings)
            enabled = st.checkbox("Mostrar catálogo no link público", value=catalog["enabled"])
            items = catalog["items"]

            colA, colB = st.columns([1, 1])
            with colA:
                if st.button("🧹 Limpar catálogo inteiro (apagar tudo)", use_container_width=True):
                    removed, errs = delete_catalog_all(access_token, items)
                    items = []
                    settings_set_catalog(settings, enabled=enabled, items=items)
                    okx, msgx = save_tenant_settings_admin(access_token, tenant_id, settings)
                    if okx:
                        st.success(f"Catálogo limpo! Removidos: {removed}")
                        if errs:
                            st.warning("Alguns arquivos falharam ao remover (melhor esforço):")
                            st.code("\n".join(errs))
                        st.rerun()
                    else:
                        st.error("Não consegui salvar settings após limpar.")
                        st.code(msgx)

            st.divider()
            st.markdown("**Adicionar arquivos**")
            up = st.file_uploader(
                "Selecione 1 ou mais arquivos (JPG/PNG/WEBP/PDF)",
                type=["jpg", "jpeg", "png", "webp", "pdf"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )

            if st.button("⬆️ Enviar arquivos", type="primary", use_container_width=True, disabled=not up):
                added = 0
                errs = []
                for f in (up or []):
                    ok, msg, item = upload_catalog_file(access_token, tenant_id, f)
                    if ok and item:
                        items.append(item)
                        added += 1
                    else:
                        errs.append(f"{f.name}: {msg}")

                settings_set_catalog(settings, enabled=enabled, items=items)
                ok2, msg2 = save_tenant_settings_admin(access_token, tenant_id, settings)
                if ok2:
                    st.success(f"✅ {added} arquivo(s) enviado(s).")
                    if errs:
                        st.warning("Alguns falharam:")
                        st.code("\n".join(errs))
                    st.rerun()
                else:
                    st.error("Não consegui salvar o catálogo no banco.")
                    st.code(msg2)

            st.divider()
            st.markdown("**Seus arquivos**")
            if not items:
                st.info("Você ainda não enviou nada.")
            else:
                for idx, it in enumerate(list(items)):
                    cols = st.columns([1.2, 1.8, 0.7])
                    with cols[0]:
                        if it.get("type") == "pdf":
                            st.markdown("📄 **PDF**")
                            st.link_button("Abrir PDF", it["url"], use_container_width=True)
                        else:
                            st.image(it["url"], use_container_width=True)

                    with cols[1]:
                        new_caption = st.text_input(
                            f"Legenda (opcional) • #{idx+1}",
                            value=it.get("caption", ""),
                            key=f"cap_{idx}_{it['path']}",
                        )
                        items[idx]["caption"] = new_caption.strip()
                        st.caption(it["path"])

                    with cols[2]:
                        if st.button("🗑️ Remover", key=f"rm_{idx}_{it['path']}", use_container_width=True):
                            okd, msgd = delete_catalog_item(access_token, it["path"])
                            if not okd:
                                st.error("Falha ao remover do Storage.")
                                st.code(msgd)
                            else:
                                items.pop(idx)
                                settings_set_catalog(settings, enabled=enabled, items=items)
                                ok3, msg3 = save_tenant_settings_admin(access_token, tenant_id, settings)
                                if ok3:
                                    st.success("Removido.")
                                    st.rerun()
                                else:
                                    st.error("Removi do Storage, mas não consegui atualizar o banco.")
                                    st.code(msg3)

                st.divider()
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("💾 Salvar alterações do catálogo", use_container_width=True, type="primary"):
                        settings_set_catalog(settings, enabled=enabled, items=items)
                        ok4, msg4 = save_tenant_settings_admin(access_token, tenant_id, settings)
                        if ok4:
                            st.success("Catálogo atualizado!")
                            st.rerun()
                        else:
                            st.error("Não consegui salvar.")
                            st.code(msg4)
                with c2:
                    if st.button("Fechar", use_container_width=True):
                        st.session_state.show_catalog = False
                        st.rerun()

    # ==========================
    # SINAL (opcional) - ADMIN
    # ==========================
    deposit_cfg = settings_get_deposit(settings)

    if st.session_state.show_deposit:
        with st.container(border=True):
            st.markdown("### 💰 Sinal (opcional)")
            st.caption("Se desativar, a agenda funciona normalmente sem cobrança/PIX.")

            enabled = st.checkbox("Cobrar sinal para reservar", value=deposit_cfg["enabled"])
            value = st.number_input("Valor do sinal (R$)", min_value=0.0, step=1.0, value=float(deposit_cfg["value"]))

            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Salvar sinal", use_container_width=True, type="primary"):
                    settings_set_deposit(settings, enabled=enabled, value=value)
                    ok, msg = save_tenant_settings_admin(access_token, tenant_id, settings)
                    if ok:
                        st.success("Configuração de sinal salva!")
                        st.session_state.show_deposit = False
                        st.rerun()
                    else:
                        st.error("Não consegui salvar.")
                        st.code(msg)
            with c2:
                if st.button("Fechar", use_container_width=True):
                    st.session_state.show_deposit = False
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
        nome_prof = "Nail Designer"
    else:
        nome_prof = nome_raw

    # ========= Visual (Nail Designer vibes) =========
    st.markdown(
        """
        <style>
        .nd-hero{
          text-align:center;
          margin-top: 0.2rem;
          margin-bottom: 0.9rem;
        }
        .nd-avatar{
          width: 132px;
          height: 132px;
          border-radius: 999px;
          object-fit: cover;
          border: 3px solid rgba(255,255,255,.14);
          box-shadow: 0 14px 35px rgba(0,0,0,.35);
          display:block;
          margin: 0 auto 12px auto;
          background: rgba(255,255,255,.06);
        }
        .nd-avatar-fallback{
          width: 132px;
          height: 132px;
          border-radius: 999px;
          display:flex;
          align-items:center;
          justify-content:center;
          margin: 0 auto 12px auto;
          border: 3px solid rgba(255,255,255,.14);
          box-shadow: 0 14px 35px rgba(0,0,0,.35);
          background: radial-gradient(100px 60px at 30% 20%, rgba(255,77,166,.22), transparent 60%),
                      radial-gradient(120px 70px at 75% 30%, rgba(56,189,248,.18), transparent 62%),
                      rgba(255,255,255,.05);
          font-weight: 900;
          font-size: 2.1rem;
          letter-spacing: .5px;
          color: rgba(255,255,255,.92);
        }
        .nd-name{
          font-size: 2.0rem;
          font-weight: 900;
          line-height: 1.1;
          margin: 0;
        }
        .nd-bio{
          color: rgba(255,255,255,.74);
          margin-top: .35rem;
          margin-bottom: .55rem;
          font-size: 1.02rem;
        }
        .nd-badges{
          display:flex;
          gap: 10px;
          justify-content:center;
          flex-wrap: wrap;
          margin-top: .3rem;
        }
        .nd-badge{
          display:inline-flex;
          align-items:center;
          gap: 8px;
          padding: 7px 11px;
          border-radius: 999px;
          border: 1px solid rgba(255,255,255,.12);
          background: rgba(255,255,255,.04);
          color: rgba(255,255,255,.75);
          font-size: .92rem;
        }
        
/* --- Mobile conversion tweaks --- */
@media (max-width: 520px){
  .nd-badges{
    width: 100%;
    gap: 12px;
    margin-top: .55rem;
  }
  .nd-badge{
    width: 100%;
    justify-content: center;
    padding: 12px 14px;
    font-size: .98rem;
  }
  .nd-fixed-cta{
    left: 12px;
    right: 12px;
    bottom: 12px;
  }
  .nd-fixed-cta a{
    border-radius: 18px;
    padding: 16px 16px;
    font-size: 17px;
  }
  .nd-bio span{
    display:block;
  }
  .nd-bio span + span{
    margin-top: 4px;
  }
}
@media (min-width: 521px){
  .nd-bio span{
    display:inline;
  }
  .nd-bio span + span{
    margin-left: 8px;
  }
}
.nd-fixed-cta{
          position: fixed;
          left: 14px;
          right: 14px;
          bottom: 14px;
          z-index: 99999;
        }
        .nd-fixed-cta a{
          display:block;
          text-align:center;
          padding: 14px 16px;
          border-radius: 16px;
          text-decoration:none;
          font-weight: 900;
          letter-spacing: .2px;
          color: rgba(255,255,255,.95);
          border: 1px solid rgba(255,255,255,.18);
          background: linear-gradient(90deg, rgba(255,77,166,.55), rgba(255,102,204,.35), rgba(56,189,248,.25));
          box-shadow: 0 16px 35px rgba(0,0,0,.45);
          backdrop-filter: blur(10px);
        }
        .nd-fixed-cta a:hover{
          transform: translateY(-1px);
          border-color: rgba(255,255,255,.28);
        }
        .nd-grid-caption{
          margin-top: .4rem;
          color: rgba(255,255,255,.70);
          font-size: .95rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not tenant.get("pode_operar", False):
        st.error("🔒 Agenda indisponível (assinatura vencida ou conta inativa).")
        st.stop()

    whatsapp_num = (tenant.get("whatsapp_numero") or "").strip()
    pix_chave = (tenant.get("pix_chave") or "").strip()
    pix_nome = (tenant.get("pix_nome") or "Profissional").strip()
    pix_cidade = (tenant.get("pix_cidade") or "BRASIL").strip()

    if not whatsapp_num or len("".join([c for c in whatsapp_num if c.isdigit()])) < 10:
        st.error("WhatsApp do profissional inválido. Peça para ele configurar no painel.")
        st.stop()

    settings = tenant.get("settings") if isinstance(tenant.get("settings"), dict) else {}
    services_map = settings_get_services(settings)
    working_hours = settings_get_working_hours(settings)
    catalog = settings_get_catalog(settings)
    deposit_cfg = settings_get_deposit(settings)

    # Dados de branding (opcionais, não quebram se não existir)
    bio = ""
    city = ""
    avatar_url = ""

    if isinstance(settings, dict):
        bio = str(settings.get("bio") or settings.get("descricao") or "").strip()
        city = str(settings.get("cidade") or settings.get("city") or "").strip()
        avatar_url = str(
            settings.get("avatar_url")
            or settings.get("profile_photo_url")
            or (settings.get("branding") or {}).get("avatar_url", "")
        ).strip()

    # fallback: tenta pegar de campos diretos do tenant (caso você adicione no backend)
    if not avatar_url:
        avatar_url = str(tenant.get("avatar_url") or tenant.get("profile_photo_url") or "").strip()

    
    # V10: Hide any duplicate renders of the same avatar image (Streamlit sometimes duplicates images)
    if avatar_url:
        st.markdown(f"""
        <style>
        /* hide any <img> using the same src that is NOT our premium avatar */
        img[src="{avatar_url}"]:not(.nd-avatar-img){{display:none !important;}}
        </style>
        """, unsafe_allow_html=True)
# iniciais
    def _iniciais(nome: str) -> str:
        parts = [p for p in re.split(r"\s+", (nome or "").strip()) if p]
        if not parts:
            return "ND"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][:1] + parts[-1][:1]).upper()

    initials = _iniciais(nome_prof)

    st.markdown('<div class="nd-hero">', unsafe_allow_html=True)

    # V13: Remove any duplicated huge avatar images injected by Streamlit (runtime DOM fix)
    components.html("""
    <script>
    (function(){
      function cleanup(){
        try{
          const keep = document.querySelector("img.nd-avatar-img");
          const imgs = Array.from(document.querySelectorAll("img"));
          imgs.forEach(img=>{
            if(keep && img === keep) return;
            const r = img.getBoundingClientRect();
            // only affect very top of page, and only huge images
            if(r.top < 700 && r.width > 260 && r.height > 260){
              img.style.display = "none";
            }
          });
        }catch(e){}
      }
      cleanup();
      setTimeout(cleanup, 250);
      setTimeout(cleanup, 800);
      setTimeout(cleanup, 1600);
    })();
    </script>
    """, height=0)




    if avatar_url:
        st.markdown(f"""
        <div class="nd-avatar-wrap" style="width:160px;height:160px;max-width:160px;max-height:160px;margin:0 auto 14px auto;position:relative;">
          <div class="nd-avatar-ring" aria-hidden="true"></div>
          <div class="nd-avatar-inner" style="width:100%;height:100%;border-radius:999px;overflow:hidden;position:relative;z-index:2;">
            <img class="nd-avatar-img" src="{avatar_url}" alt="foto"
                 style="width:100%;height:100%;object-fit:cover;border-radius:999px;display:block;" />
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="nd-avatar-wrap" style="width:160px;height:160px;max-width:160px;max-height:160px;margin:0 auto 14px auto;position:relative;">
          <div class="nd-avatar-ring" aria-hidden="true"></div>
          <div class="nd-avatar-inner" style="width:100%;height:100%;border-radius:999px;overflow:hidden;position:relative;z-index:2;
               display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.06);">
            <div class="nd-avatar-fallback" style="font-weight:900;font-size:40px;letter-spacing:1px;">{initials}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f'<div class="nd-name">{nome_prof}</div>', unsafe_allow_html=True)

    def _format_bio_html(raw: str) -> str:
        """Format bio as 2 lines on mobile for better readability."""
        import re as _re
        raw = (raw or "").strip()
        if not raw:
            raw = "Alongamento • Manicure • Nail Art"
        parts = [p.strip() for p in _re.split(r"[•·|]", raw) if p.strip()]
        if len(parts) >= 2:
            line1 = f"✨ {parts[0]}"
            line2 = "💅 " + " • ".join(parts[1:])
            return f"<span>{line1}</span><span>{line2}</span>"
        return f"<span>✨ {raw}</span>"

    st.markdown(f'<div class="nd-bio">{_format_bio_html(bio)}</div>', unsafe_allow_html=True)

    badges = []
    if city:
        badges.append(f"📍 {city}")
    badges.append("💬 Atendimento via WhatsApp")
    if deposit_cfg.get("enabled", True) and float(deposit_cfg.get("value", 0) or 0) > 0:
        badges.append("💰 Sinal via Pix")

    st.markdown('<div class="nd-badges">', unsafe_allow_html=True)
    for b in badges[:3]:
        st.markdown(f'<span class="nd-badge">{b}</span>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    # Botão fixo para converter mais (scroll para área de agendamento)
    st.markdown(
        f"""
        <div class="nd-fixed-cta">
          <a href="?t={PUBLIC_TENANT_ID}&view=agendar" target="_self">💅 Agendar agora</a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Navegação (robusta no Streamlit): usa query param ?view=agendar|catalogo
    view = st.query_params.get("view")
    if isinstance(view, list):
        view = view[0]
    view = (view or "").strip().lower()

    # Se veio link com view, força a aba correta
    if view == "agendar":
        st.session_state["nd_tab"] = "📅 Agendamento"
    elif view == "catalogo":
        st.session_state["nd_tab"] = "📒 Catálogo"

    if "nd_tab" not in st.session_state:
        st.session_state["nd_tab"] = "📅 Agendamento"

    tab = st.radio(
        "Navegação",
        ["📅 Agendamento", "📒 Catálogo"],
        horizontal=True,
        label_visibility="collapsed",
        key="nd_tab",
    )

    if tab == "📅 Agendamento":
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
        valor_sinal = calcular_sinal(servicos_escolhidos, deposit_cfg)

        if servicos_escolhidos:
            if deposit_cfg["enabled"] and valor_sinal > 0:
                st.caption(f"Total: **{fmt_brl(total_servico)}** • Sinal: **{fmt_brl(valor_sinal)}**")
            else:
                st.caption(f"Total: **{fmt_brl(total_servico)}**")
        else:
            if deposit_cfg["enabled"] and valor_sinal > 0:
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
                                deposit_cfg=deposit_cfg,
                            )
                            st.session_state.wa_link = montar_link_whatsapp(whatsapp_num, mensagem)
                            st.session_state.ultima_chave_reserva = chave
                            st.session_state.reservando = False
                            st.success("Reserva criada como **PENDENTE**. Clique em **Abrir WhatsApp** para enviar a mensagem.")
                            st.rerun()

    else:
        st.subheader("📒 Catálogo")

        if not catalog["enabled"]:
            st.info("Catálogo indisponível.")
            return

        if not catalog["items"]:
            st.info("Este profissional ainda não adicionou fotos no catálogo.")
            return

        # Grid 2 colunas tipo feed
        cols = st.columns(2)
        for i, it in enumerate(catalog["items"]):
            with cols[i % 2]:
                caption = (it.get("caption") or "").strip()

                if it.get("type") == "pdf":
                    st.markdown("📄 **PDF**")
                    st.link_button("Abrir PDF", it["url"], use_container_width=True)
                else:
                    st.image(it["url"], use_container_width=True)

                if caption:
                    st.markdown(f'<div class="nd-grid-caption">{caption}</div>', unsafe_allow_html=True)

# ============================================================
# ONBOARDING (primeiro acesso)
# ============================================================
def settings_is_onboarding_done(settings: dict) -> bool:
    try:
        return bool(settings.get("onboarding_done", False))
    except Exception:
        return False

def mark_onboarding_done(access_token: str, tenant_id: str, settings: dict):
    settings = dict(settings or {})
    settings["onboarding_done"] = True
    ok, err = save_tenant_settings_admin(access_token, tenant_id, settings)
    return ok, err

def tela_onboarding(access_token: str, tenant: dict):
    """
    Wizard simples para o usuário configurar o básico e começar a usar.
    Mostra apenas quando settings['onboarding_done'] != True.
    """
    tenant_id = str(tenant.get("id"))
    user = get_auth_user(access_token)
    uid = str(getattr(user, "id", "")) if user else ""

    settings = get_tenant_settings_admin(access_token, tenant_id) or {}
    if settings_is_onboarding_done(settings):
        return True  # já concluído

    st.markdown("## 🎉 Bem-vindo ao Agenda‑Pro")
    st.caption("Vamos configurar o básico em menos de 2 minutos.")

    # passo atual
    step = int(st.session_state.get("onboarding_step", 1))
    total_steps = 4
    st.progress(min(step, total_steps) / total_steps)

    # -------- Passo 1: WhatsApp --------
    if step == 1:
        st.markdown("### 1) Seu WhatsApp")
        w_cur = (tenant.get("whatsapp_numero") or "").strip()
        w = st.text_input("Número do WhatsApp (com DDD)", value=w_cur, placeholder="Ex.: 11999999999", key="ob_whats")
        st.caption("Esse número será usado para gerar o link wa.me na confirmação do agendamento.")

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Continuar ➜", type="primary", use_container_width=True):
                ok = True
                if uid:
                    try:
                        atualizar_tenant_whatsapp(access_token, uid, tenant_id, w)
                    except Exception:
                        ok = False
                # mesmo se falhar, deixa seguir (usuário pode ajustar depois)
                st.session_state["onboarding_step"] = 2
                st.rerun()
        with c2:
            if st.button("Pular", use_container_width=True):
                st.session_state["onboarding_step"] = 2
                st.rerun()

        st.stop()

    # -------- Passo 2: Serviços --------
    if step == 2:
        st.markdown("### 2) Cadastre um serviço")
        services = settings_get_services(settings) or {}

        with st.container(border=True):
            with st.form("ob_add_service", clear_on_submit=True):
                s_nome = st.text_input(
                    "Nome do serviço",
                    placeholder="Ex.: Alongamento em gel",
                    key="ob_serv_nome",
                )
                s_preco = st.number_input(
                    "Preço (R$)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key="ob_serv_preco",
                )
                submitted = st.form_submit_button("Adicionar serviço", use_container_width=True)

            if submitted:
                nome = (s_nome or "").strip()
                if not nome:
                    st.error("Digite o nome do serviço.")
                else:
                    settings = dict(settings or {})
                    sdict = dict(settings.get("services") or {})
                    sdict[nome] = float(s_preco or 0.0)
                    settings["services"] = sdict

                    ok, err = save_tenant_settings_admin(access_token, tenant_id, settings)
                    if ok:
                        st.success("✅ Serviço adicionado.")
                        st.rerun()
                    else:
                        st.error("Não consegui salvar. Tente novamente.")
                        st.code(err)

        # recarrega pra mostrar atualizado
        services = settings_get_services(get_tenant_settings_admin(access_token, tenant_id) or {}) or {}
        if services:
            st.caption("Serviços cadastrados:")
            st.write(list(services.keys())[:10])

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("⬅ Voltar", use_container_width=True):
                st.session_state["onboarding_step"] = 1
                st.rerun()
        with c2:
            if st.button("Continuar ➜", type="primary", use_container_width=True):
                st.session_state["onboarding_step"] = 3
                st.rerun()
        with c3:
            if st.button("Pular", use_container_width=True):
                st.session_state["onboarding_step"] = 3
                st.rerun()

        st.stop()

    # -------- Passo 3: Sinal (opcional) --------
    if step == 3:
        st.markdown("### 3) Sinal via Pix (opcional)")
        dep = settings_get_deposit(settings)
        enabled = bool(dep.get("enabled", True))
        value = float(dep.get("value", VALOR_SINAL_FIXO))

        enabled_new = st.toggle("Ativar sinal", value=enabled, key="ob_dep_enabled")
        value_new = st.number_input("Valor do sinal (R$)", min_value=0.0, value=float(value), step=1.0, key="ob_dep_value")
        st.caption("Você pode alterar isso depois nas configurações.")

        if st.button("Salvar e continuar ➜", type="primary", use_container_width=True):
            settings = dict(settings or {})
            settings["deposit"] = {"enabled": bool(enabled_new), "value": float(value_new)}
            ok, err = save_tenant_settings_admin(access_token, tenant_id, settings)
            if ok:
                st.session_state["onboarding_step"] = 4
                st.rerun()
            else:
                st.error("Não consegui salvar. Tente novamente.")
                st.code(err)

        if st.button("⬅ Voltar", use_container_width=True):
            st.session_state["onboarding_step"] = 2
            st.rerun()

        st.stop()

    # -------- Passo 4: Link público --------
    if step == 4:
        st.markdown("### 4) Seu link de agendamento")
        base = st.session_state.get("APP_URL") or ""
        # fallback: tenta montar com location
        if not base:
            try:
                loc = get_page_location()
                base = (loc or {}).get("origin", "")
            except Exception:
                base = ""
        if base:
            link = f"{base}/?t={tenant_id}"
        else:
            link = f"?t={tenant_id}"

        st.write("Copie e cole esse link na sua bio ou envie para seus clientes:")
        st.code(link)

        st.success("Pronto! Você já pode começar a receber agendamentos. ✅")

        if st.button("Concluir", type="primary", use_container_width=True):
            ok, err = mark_onboarding_done(access_token, tenant_id, settings)
            st.session_state.pop("onboarding_step", None)
            if ok:
                st.rerun()
            else:
                st.error("Não consegui finalizar o onboarding.")
                st.code(err)

        st.stop()

# ============================================================
# UI: MODO ADMIN (PROFISSIONAL)
# ============================================================
def tela_admin():
    # ===== handler de logout via query param =====
    if st.query_params.get("logout") == "1":
        st.query_params.clear()
        auth_logout()

    st.markdown(
        """
        <div style="padding:14px 6px 10px 6px;">
          <div class="chip">📌 <span>Agendamentos online </span></div>
          <h1 style="margin-top:10px;">📅 Agenda-Pro</h1>
          <div class="muted" style="font-size:1.05rem; margin-top:4px;">
            Organize seus atendimentos, compartilhe seu link e confirme reservas com facilidade.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.access_token:
        # Centraliza o bloco de autenticação (visual mais SaaS)
        colL, colC, colR = st.columns([1, 2, 1])
        with colC:
            tab1, tab2 = st.tabs(["Entrar", "Criar conta"])

            with tab1:
                with st.container(border=True):
                    email = st.text_input("Email", key="login_email")
                    password = st.text_input("Senha", type="password", key="login_pass")
                    if st.button("Entrar", type="primary", use_container_width=True):
                        try:
                            res = auth_login(email, password)
                            st.session_state.access_token = res.session.access_token
                            st.rerun()
                        except Exception as e:
                            st.error("Falha no login.")
                            st.code(str(e))

            with tab2:
                c1, c2 = st.columns(2, gap="large")

                with c1:
                    with st.container(border=True):
                        st.markdown("### Criar conta")
                        email = st.text_input("Email", key="cad_email")
                        password = st.text_input("Senha", type="password", key="cad_pass")
                        if st.button("🚀 Criar conta", type="primary", use_container_width=True):
                            try:
                                auth_signup(email, password)
                                st.success("Conta criada! Agora volte na aba **Entrar** e faça login.")
                            except Exception as e:
                                st.error("Falha ao criar conta.")
                                st.code(str(e))

                with c2:
                    with st.container(border=True):
                        st.markdown("### Redefinir senha")
                        st.caption("Informe seu email cadastrado para redefinir sua senha.")
                        email_reset = st.text_input("Email", key="reset_email_side")
                        if st.button("📩 Enviar link de redefinição", use_container_width=True, key="btn_reset_side"):
                            try:
                                if not email_reset.strip():
                                    st.error("Digite um email.")
                                    st.stop()
                                auth_send_reset_email(email_reset.strip())
                                st.success("Se o email existir, enviaremos um link para redefinir a senha. ✅")
                            except Exception as e:
                                st.error("Não consegui enviar o email de redefinição.")
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

    paid_until = parse_date_iso(tenant.get("paid_until"))
    dias = dias_restantes(paid_until)

    if dias > 7:
        st.markdown(
            f"""
            <div style="
                display:flex;
                gap:10px;
                flex-wrap:wrap;
                background:rgba(34,197,94,.12);
                border:1px solid rgba(34,197,94,.35);
                padding:14px;
                border-radius:14px;
                margin-bottom:14px;
            ">
                <span class="chip">✅ <b>Plano ativo</b></span>
                <span class="chip">⏳ <b>{dias} dias restantes</b></span>
                <span class="chip">🔓 <b>Acesso liberado</b></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif dias > 0:
        st.markdown(
            f"""
            <div style="
                display:flex;
                gap:10px;
                flex-wrap:wrap;
                background:rgba(245,158,11,.12);
                border:1px solid rgba(245,158,11,.35);
                padding:14px;
                border-radius:14px;
                margin-bottom:14px;
            ">
                <span class="chip">⚠️ <b>Atenção</b></span>
                <span class="chip">⏳ <b>{dias} dias restantes</b></span>
                <span class="chip">🔓 <b>Acesso liberado</b></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.error("⛔ Seu plano expirou. Renove para continuar usando.")
        st.caption(f"Valor do plano: **{SAAS_MENSAL_VALOR}**")

        st.divider()

        tenant_id = str(tenant.get("id"))

        # ✅ Primeiro: gerar pagamento (POST)
        if st.button("🚀 Gerar link de renovação", type="primary", use_container_width=True):
            try:
                if not URL_ASSINAR_PLANO:
                    st.error("Falta configurar URL_ASSINAR_PLANO no secrets.")
                    st.stop()

                resp = requests.post(
                    URL_ASSINAR_PLANO,
                    headers=fn_headers(),
                    json={
                        "tenant_id": str(tenant_id),
                        "customer_email": str(user.email or ""),
                        "customer_name": str((tenant.get("nome") or "Profissional")),
                    },
                    timeout=20,
                )

                data = resp.json() if resp.text else {}

                if resp.status_code != 200 or not data.get("ok") or not data.get("payment_url"):
                    st.error("Erro ao gerar pagamento.")
                    st.json(data)
                    st.session_state.payment_url = None
                else:
                    st.success("Pagamento gerado ✅")
                    st.session_state.payment_url = data["payment_url"]

            except Exception as e:
                st.error("Falha ao iniciar renovação.")
                st.code(str(e))
                st.session_state.payment_url = None

        # ✅ Segundo: mostrar botão "Ir para pagamento" (GET no payment_url, que é permitido)
        if st.session_state.payment_url:
            st.link_button("👉 Ir para pagamento", st.session_state.payment_url, use_container_width=True)

        # opcional: suporte
        if SAAS_SUPORTE_WHATSAPP:
            st.link_button(
                "💬 Falar com suporte",
                f"https://wa.me/{SAAS_SUPORTE_WHATSAPP}",
                use_container_width=True,
            )

        st.stop()

    tenant_id = str(tenant.get("id"))

    # Onboarding (primeiro acesso)
    tela_onboarding(access_token, tenant)

    menu_topo_comandos(access_token, tenant_id)

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

    atualizar_finalizados_admin(access_token, tenant_id)

    st.divider()
    st.subheader("📋 Agendamentos / Reservas")

    # ============================================================
    # ✅ AJUSTE DO DATAFRAME: tempo relativo + status inline
    # ============================================================
    def tempo_relativo(dt_value):
        """
        Recebe created_at (str ISO ou datetime) e retorna:
        agora | há X min | há X h | há X dias
        """
        if not dt_value:
            return ""

        dt = dt_value
        if isinstance(dt, str):
            dt = parse_dt(dt)

        if not dt:
            return ""

        # garante timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # converte pra Brasil
        dt_local = dt.astimezone(LOCAL_TZ)
        diff = agora_local() - dt_local
        secs = int(diff.total_seconds())

        if secs < 0:
            # se vier algo "no futuro" por timezone/clock, não quebra
            secs = abs(secs)

        if secs < 60:
            return "agora"
        if secs < 3600:
            return f"há {secs // 60} min"
        if secs < 86400:
            return f"há {secs // 3600} h"
        return f"há {secs // 86400} dias"

    def status_inline_com_tempo(status_norm: str, created_at_value):
        label = STATUS_LABELS.get(status_norm, status_norm)
        rel = tempo_relativo(created_at_value)
        if rel:
            return f"{label} • {rel}"
        return f"{label}"

    df_admin = listar_agendamentos_admin(access_token, tenant_id)
    if df_admin.empty:
        st.info("Nenhum agendamento encontrado.")
    else:
        # parse Data_dt
        df_admin["Data_dt"] = pd.to_datetime(df_admin["Data"], errors="coerce")

        # settings para calcular preços
        settings = get_tenant_settings_admin(access_token, tenant_id)
        services_map = settings_get_services(settings)
        deposit_cfg = settings_get_deposit(settings)
        deposit_on = bool(deposit_cfg.get("enabled", True)) and float(deposit_cfg.get("value", 0)) > 0

        def total_from_text(texto_servico: str) -> float:
            servs = texto_para_lista_servicos(texto_servico)
            return calcular_total_servicos(servs, services_map)

        df_admin["Preço do serviço"] = df_admin["Serviço(s)"].apply(total_from_text).astype(float)
        df_admin["Status_norm"] = df_admin["Status"].apply(norm_status)
        df_admin["status_ord"] = df_admin["Status_norm"].apply(lambda s: STATUS_SORT.get(s, 99))

        # ✅ NOVO: status com tempo relativo (usa a coluna "Criado em" original)
        # obs: "Criado em" já vem do rename dentro de listar_agendamentos_admin()
        if "Criado em" in df_admin.columns:
            df_admin["Status"] = df_admin.apply(
                lambda r: status_inline_com_tempo(r["Status_norm"], r["Criado em"]),
                axis=1
            )
        else:
            # fallback: mantém status label normal
            df_admin["Status"] = df_admin["Status_norm"].apply(lambda s: STATUS_LABELS.get(s, s))

        # --------- filtros ---------
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

        filtrar_status = st.checkbox("Filtrar por status", value=True)
        if filtrar_status:
            escolhas = ["Todos"] + [STATUS_LABELS[s] for s in STATUS_ALL]
            sel = st.multiselect("Status", escolhas, default=["Todos"])
            if "Todos" not in sel:
                label_to_norm = {STATUS_LABELS[s]: s for s in STATUS_ALL}
                wanted = [label_to_norm[x] for x in sel if x in label_to_norm]
                if wanted:
                    df_filtrado = df_filtrado[df_filtrado["Status_norm"].isin(wanted)]

        # --------- KPIs úteis ---------
        total_gerado = float(df_filtrado["Preço do serviço"].sum()) if not df_filtrado.empty else 0.0
        total_sinais = float(df_filtrado["Sinal"].sum()) if not df_filtrado.empty else 0.0
        qtd = int(len(df_filtrado))

        recebido = (
            float(df_filtrado[df_filtrado["Status_norm"].isin(["pago", "finalizado"])]["Preço do serviço"].sum())
            if not df_filtrado.empty else 0.0
        )
        a_receber = (
            float(df_filtrado[df_filtrado["Status_norm"].isin(["pendente"])]["Preço do serviço"].sum())
            if not df_filtrado.empty else 0.0
        )
        cancelados_qtd = int((df_filtrado["Status_norm"] == "cancelado").sum()) if not df_filtrado.empty else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Quantidade", f"{qtd}")
        m2.metric("Recebido", fmt_brl(recebido))
        m3.metric("A receber", fmt_brl(a_receber))
        m4.metric("Cancelados", f"{cancelados_qtd}")

        if deposit_on:
            ex1, ex2 = st.columns(2)
            ex1.metric("Total serviços (gerado)", fmt_brl(total_gerado))
            ex2.metric("Total sinais", fmt_brl(total_sinais))
        else:
            st.metric("Total serviços (gerado)", fmt_brl(total_gerado))

        # --------- tabela (mais legível) ---------
        df_show = df_filtrado.sort_values(["Data_dt", "Horário", "status_ord"], ascending=[True, True, True]).copy()

        # ✅ remove colunas técnicas + remove "Criado em" (não serve mais)
        drop_cols = [c for c in ["Data_dt", "Status_norm", "status_ord"] if c in df_show.columns]
        df_show = df_show.drop(columns=drop_cols, errors="ignore")

        if "Criado em" in df_show.columns:
            df_show = df_show.drop(columns=["Criado em"], errors="ignore")

        if not deposit_on and "Sinal" in df_show.columns:
            df_show = df_show.drop(columns=["Sinal"], errors="ignore")

        # formatação BRL
        df_show["Preço do serviço"] = df_show["Preço do serviço"].apply(lambda v: fmt_brl(float(v)))
        if "Sinal" in df_show.columns:
            df_show["Sinal"] = df_show["Sinal"].apply(lambda v: fmt_brl(float(v)))

        st.dataframe(
            df_show.drop(columns=["id"], errors="ignore"),
            use_container_width=True,
            height=360
        )

        # ====================================================
        # AÇÕES RÁPIDAS
        # ====================================================
        # AÇÕES RÁPIDAS
        # ====================================================
        st.divider()
        st.subheader("⚡ Ações rápidas")

        # ✅ legenda para evitar confusão (cancelar vs excluir)
        st.caption("❌ **Cancelar** mantém o registro no histórico • 🗑️ **Excluir** remove definitivamente.")

        def fmt_ag(ag_id: int) -> str:
            row = df_admin[df_admin.id == ag_id]
            if row.empty:
                return str(ag_id)
            r = row.iloc[0]
            # aqui mantemos o label simples no select (sem o "há X"),
            # pra não ficar mudando enquanto você usa o selectbox
            return f"{r['Cliente']} • {r['Data']} {r['Horário']} • {STATUS_LABELS.get(r['Status_norm'], r['Status_norm'])}"

        def resumo_ag(ag_id: int) -> str:
            """Resumo fixo para usar em mensagens de sucesso/erro."""
            row = df_admin[df_admin.id == ag_id]
            if row.empty:
                return f"ID {ag_id}"
            r = row.iloc[0]
            return f"{r['Cliente']} • {r['Data']} {r['Horário']}"

        colA, colB = st.columns(2)

        with colA:
            st.subheader("✅ Marcar como PAGO")
            pendentes_ids = df_admin[df_admin["Status_norm"] == "pendente"]["id"].tolist()
            ids_para_pagar = pendentes_ids if pendentes_ids else df_admin["id"].tolist()

            ag_pagar = st.selectbox(
                "Selecione o agendamento",
                ids_para_pagar,
                format_func=fmt_ag,
                key="pagar_select",
            )

            if st.button("Marcar como PAGO", type="primary", use_container_width=True):
                marcar_status_admin(access_token, tenant_id, int(ag_pagar), "pago")
                st.success(f"✅ Marcado como **PAGO**: {resumo_ag(int(ag_pagar))}")
                st.rerun()

        with colB:
            st.subheader("❌ Marcar como CANCELADO")
            ids_cancel = df_admin[df_admin["Status_norm"] != "cancelado"]["id"].tolist() or df_admin["id"].tolist()

            ag_cancel = st.selectbox(
                "Selecione o agendamento",
                ids_cancel,
                format_func=fmt_ag,
                key="cancel_select",
            )

            if st.button("Marcar como CANCELADO", use_container_width=True):
                marcar_status_admin(access_token, tenant_id, int(ag_cancel), "cancelado")
                st.success(f"❌ Marcado como **CANCELADO**: {resumo_ag(int(ag_cancel))}")
                st.rerun()

        st.subheader("🗑️ Excluir agendamento")
        ag_excluir = st.selectbox(
            "Selecione para excluir",
            df_admin["id"],
            format_func=fmt_ag,
            key="excluir_select_unique",
        )

        # ✅ confirmação obrigatória (protege contra erro irreversível)
        confirm_delete = st.checkbox(
            "Confirmo que desejo excluir definitivamente este agendamento",
            value=False,
            key="confirm_delete_checkbox",
        )

        if st.button("Excluir agendamento", use_container_width=True, disabled=not confirm_delete):
            excluir_agendamento_admin(access_token, tenant_id, int(ag_excluir))
            st.success(f"🗑️ **Excluído definitivamente**: {resumo_ag(int(ag_excluir))}")
            st.rerun()

    st.divider()
    if st.button("🚀 Assinar plano", type="primary", use_container_width=True):
        try:
            if not URL_ASSINAR_PLANO:
                st.error("Falta configurar URL_ASSINAR_PLANO no secrets.")
                st.stop()

            resp = requests.post(
                URL_ASSINAR_PLANO,
                headers=fn_headers(),
                json={
                    "tenant_id": str(tenant_id),
                    "customer_email": str(user.email or ""),
                    "customer_name": str((tenant.get("nome") or "Profissional")),
                },
                timeout=20,
            )

            data = resp.json() if resp.text else {}

            if resp.status_code != 200 or not data.get("ok") or not data.get("payment_url"):
                st.error("Erro ao gerar pagamento.")
                st.code(data)
            else:
                st.success("Pagamento gerado ✅")
                st.link_button("👉 Ir para pagamento", data["payment_url"], use_container_width=True)

        except Exception as e:
            st.error("Falha ao iniciar assinatura.")
            st.code(str(e))

    # ===== Rodapé fixo "Sair" (sempre no final da tela) =====
    st.markdown("""
    <div class="footer-logout">
      <a href="\1" target="_self">🚪 Sair</a>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# ROUTER
# ============================================================

if st.query_params.get("reset") == "1":
    tela_reset_senha()
    st.stop()
elif IS_PUBLIC:
    tela_publica()
else:
    tela_admin()



# ===============================
# V4 PREMIUM UI ENHANCEMENTS
# ===============================

st.markdown("""
<style>

/* Extra spacing for luxury feel */
.nd-hero h1 {
    margin-top: 18px !important;
    margin-bottom: 10px !important;
}

.nd-hero p {
    margin-bottom: 18px !important;
}

.nd-badges {
    margin-top: 14px !important;
    margin-bottom: 26px !important;
}

/* Bigger avatar */
.nd-avatar {
    width: 170px !important;
    height: 170px !important;
    border-radius: 50%;
    border: 3px solid rgba(255,255,255,.18);
    box-shadow: 0 0 25px rgba(255, 77, 166, 0.15);
}

/* Premium fixed CTA */
.nd-fixed-cta a {
    padding: 18px !important;
    font-size: 17px !important;
    font-weight: 700 !important;
    border-radius: 18px !important;
    box-shadow: 0 8px 25px rgba(255, 77, 166, 0.35);
    transition: all 0.25s ease-in-out;
}

.nd-fixed-cta a:hover {
    transform: translateY(-3px) scale(1.01);
    box-shadow: 0 12px 35px rgba(255, 77, 166, 0.5);
}

</style>
""", unsafe_allow_html=True)



# ===============================
# V5: AVATAR ANIMADO + TIPOGRAFIA PREMIUM
# ===============================
st.markdown("""
<style>

/* Tipografia mais premium */
.stApp, .stApp * {
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji" !important;
}

.nd-name{
  letter-spacing: .2px;
}

.nd-bio{
  margin-top: 10px !important;
  margin-bottom: 18px !important;
  line-height: 1.35 !important;
}

.nd-badges{
  margin-top: 14px !important;
  margin-bottom: 28px !important;
}

/* Avatar com anel gradiente animado */
.nd-avatar-wrap{
  width: clamp(120px, 32vw, 190px) !important;
  height: clamp(120px, 32vw, 190px) !important;
  max-width: 190px !important;
  max-height: 190px !important;
  border-radius: 999px;
  padding: 4px;
  margin: 0 auto 14px auto;
  background: conic-gradient(from 180deg, rgba(255,77,166,.95), rgba(56,189,248,.92), rgba(34,197,94,.88), rgba(255,77,166,.95));
  animation: ndSpin 7s linear infinite;
  box-shadow: 0 18px 45px rgba(0,0,0,.35);
}

.nd-avatar-inner{
  width: 100%;
  height: 100% !important;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.14);
  display:flex;
  align-items:center;
  justify-content:center;
}

.nd-avatar-img{
  width: 100% !important;
  height: 100% !important;
  object-fit: cover;
  border-radius: 999px;
  display:block;
}

/* fallback dentro do inner */
.nd-avatar-fallback{
  width: 100% !important;
  height: 100% !important;
  margin: 0 !important;
  border: 0 !important;
  box-shadow: none !important;
  background: radial-gradient(120px 80px at 30% 20%, rgba(255,77,166,.22), transparent 60%),
              radial-gradient(160px 90px at 75% 30%, rgba(56,189,248,.18), transparent 62%),
              rgba(255,255,255,.05) !important;
}

/* Botão fixo ainda mais premium (micro animação suave) */
.nd-fixed-cta a{
  padding: 18px !important;
  font-size: 17px !important;
  border-radius: 18px !important;
  box-shadow: 0 10px 28px rgba(255, 77, 166, 0.38);
  transition: transform 0.22s ease, box-shadow 0.22s ease, filter 0.22s ease;
}

.nd-fixed-cta a:active{
  transform: translateY(0px) scale(0.99);
  filter: brightness(1.05);
}

@keyframes ndSpin{
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

</style>
""", unsafe_allow_html=True)


# ===============================
# V7 HARD CLAMP
# ===============================

st.markdown("""
<style>
/* V7 hard clamp (extra safety on some Streamlit builds) */
.nd-avatar-wrap{ max-width: 190px !important; max-height: 190px !important; }
.nd-avatar-img{ max-width: 190px !important; max-height: 190px !important; }
</style>
""", unsafe_allow_html=True)



# ===============================
# V8 — Premium hero center + animated ring around avatar + responsive CTA
# ===============================
st.markdown("""
<style>
/* --- HERO: center everything in one aligned block --- */
.nd-hero{
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  text-align: center !important;
  margin-top: 0.4rem !important;
  margin-bottom: 1.1rem !important;
}

.nd-name{
  font-size: clamp(1.45rem, 3.8vw, 2.2rem) !important;
  font-weight: 900 !important;
  letter-spacing: .2px !important;
  margin-top: 10px !important;
  margin-bottom: 6px !important;
}

.nd-bio{
  color: rgba(255,255,255,.74) !important;
  font-size: 0.98rem !important;
  margin-bottom: 18px !important;
}

/* badges centered */
.nd-badges{
  display: flex !important;
  flex-wrap: wrap !important;
  justify-content: center !important;
  gap: 10px !important;
  margin-top: 2px !important;
  margin-bottom: 26px !important;
}
.nd-badge{
  display: inline-flex !important;
  align-items: center !important;
  gap: 8px !important;
  padding: 10px 12px !important;
  border-radius: 999px !important;
  border: 1px solid rgba(255,255,255,.14) !important;
  background: rgba(255,255,255,.04) !important;
  color: rgba(255,255,255,.86) !important;
  font-size: 0.92rem !important;
}

/* --- AVATAR: animated ring around the photo (no more big standalone orb) --- */
.nd-avatar-wrap{
  position: relative !important;
  width: clamp(120px, 32vw, 170px) !important;
  height: clamp(120px, 32vw, 170px) !important;
  max-width: 170px !important;
  max-height: 170px !important;
  margin: 0 auto 12px auto !important;
  padding: 0 !important;
  border-radius: 999px !important;
  background: transparent !important;
  animation: none !important; /* ring spins, not the whole circle */
}

/* outer glow */
.nd-avatar-wrap::after{
  content: "";
  position: absolute;
  inset: -14px;
  border-radius: 999px;
  background: conic-gradient(from 180deg,
      rgba(255,77,166,.85),
      rgba(56,189,248,.80),
      rgba(34,197,94,.72),
      rgba(255,77,166,.85));
  filter: blur(18px);
  opacity: .22;
  z-index: 0;
  pointer-events: none;
}

/* spinning ring */
.nd-avatar-wrap::before{
  content: "";
  position: absolute;
  inset: -6px;
  border-radius: 999px;
  background: conic-gradient(from 180deg,
      rgba(255,77,166,.98),
      rgba(56,189,248,.92),
      rgba(34,197,94,.84),
      rgba(255,77,166,.98));
  animation: ndSpin 7s linear infinite;
  z-index: 1;
  pointer-events: none;
}

/* inner circle (the actual photo area) */
.nd-avatar-inner{
  position: relative !important;
  z-index: 2 !important;
  width: 100% !important;
  height: 100% !important;
  border-radius: 999px !important;
  overflow: hidden !important;
  padding: 6px !important; /* thickness of the ring */
  background: rgba(7, 11, 18, 0.88) !important;
  border: 1px solid rgba(255,255,255,.10) !important;
  box-shadow: 0 16px 40px rgba(0,0,0,.38) !important;
  box-sizing: border-box !important;
}

.nd-avatar-img{
  width: 100% !important;
  height: 100% !important;
  border-radius: 999px !important;
  object-fit: cover !important;
  display: block !important;
  max-width: 100% !important;
  max-height: 100% !important;
}

.nd-avatar-fallback{
  width: 100% !important;
  height: 100% !important;
  border-radius: 999px !important;
  display:flex !important;
  align-items:center !important;
  justify-content:center !important;
  font-weight: 900 !important;
  letter-spacing: 1px !important;
  color: rgba(255,255,255,.92) !important;
  background: rgba(255,255,255,.06) !important;
}

/* --- FIXED CTA: responsive (desktop = narrower, mobile = full) --- */
.nd-fixed-cta{
  padding: 12px 14px !important;
}
.nd-fixed-cta a{
  width: min(720px, calc(100% - 0px)) !important;
  margin: 0 auto !important;
  padding: 16px 16px !important;
  border-radius: 18px !important;
  box-shadow: 0 10px 28px rgba(255, 77, 166, 0.35) !important;
  font-size: 16.5px !important;
}
@media (min-width: 900px){
  .nd-fixed-cta a{
    width: min(560px, 100%) !important;
    padding: 14px 18px !important;
    font-size: 16px !important;
    border-radius: 16px !important;
  }
}
</style>
""", unsafe_allow_html=True)



# ===============================
# V9 — Fix duplicated avatar render (hide legacy st.image avatar) + hard size lock
# ===============================
st.markdown("""
<style>
/* Streamlit sometimes renders a legacy st.image() avatar inside the hero without our classes.
   Hide any hero images that are NOT the premium avatar image. */
.nd-hero img:not(.nd-avatar-img){
  display: none !important;
}

/* Extra hard lock to prevent any stretching */
.nd-avatar-wrap{
  width: clamp(120px, 32vw, 170px) !important;
  height: clamp(120px, 32vw, 170px) !important;
  max-width: 170px !important;
  max-height: 170px !important;
}

.nd-avatar-inner{
  width: 100% !important;
  height: 100% !important;
}

.nd-avatar-img{
  width: 100% !important;
  height: 100% !important;
  max-width: 100% !important;
  max-height: 100% !important;
  object-fit: cover !important;
  border-radius: 999px !important;
}

/* Prevent the hero from letting any element overflow weirdly */
.nd-hero{
  overflow: hidden !important;
}
</style>
""", unsafe_allow_html=True)


# ===============================
# V15 — Avatar ring CSS (safe)
# ===============================
st.markdown("""
<style>
.nd-avatar-ring{
  position:absolute;
  inset:-7px;
  border-radius:999px;
  background: conic-gradient(from 180deg,
    rgba(255,77,166,.98),
    rgba(56,189,248,.92),
    rgba(34,197,94,.84),
    rgba(255,77,166,.98));
  animation: ndSpin 7s linear infinite;
  z-index:1;
  filter: drop-shadow(0 10px 22px rgba(255, 77, 166, 0.20));
  pointer-events:none;
}
@keyframes ndSpin { to { transform: rotate(360deg); } }
</style>
""", unsafe_allow_html=True)
