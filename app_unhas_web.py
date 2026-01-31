import streamlit as st
import pandas as pd
from datetime import date
import urllib.parse
from supabase import create_client
import streamlit.components.v1 as components

# ======================
# SECRETS
# ======================
SENHA_ADMIN = st.secrets["SENHA_ADMIN"]
WHATSAPP_NUMERO = st.secrets["WHATSAPP_NUMERO"]  # só números: 55 + DDD + número
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ======================
# STATE (WhatsApp UX)
# ======================
if "wa_link" not in st.session_state:
    st.session_state.wa_link = None
if "wa_should_open" not in st.session_state:
    st.session_state.wa_should_open = False

# ======================
# FUNÇÕES SUPABASE
# ======================
def listar_agendamentos():
    resp = (
        supabase.table("agendamentos")
        .select("id,cliente,data,horario,servico")
        .order("data")
        .order("horario")
        .execute()
    )
    rows = resp.data or []
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["id", "Cliente", "Data", "Horário", "Serviço"])

    df.rename(columns={
        "cliente": "Cliente",
        "data": "Data",
        "horario": "Horário",
        "servico": "Serviço",
    }, inplace=True)

    df["Data"] = df["Data"].astype(str)
    df["Horário"] = df["Horário"].astype(str)
    return df


def horarios_ocupados(data_escolhida: date):
    resp = (
        supabase.table("agendamentos")
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
    # api.whatsapp.com é bem estável em desktop
    return f"https://api.whatsapp.com/send?phone={WHATSAPP_NUMERO}&text={mensagem_url}"


# ======================
# AUTO-OPEN WhatsApp (1x)
# ======================
# Se wa_should_open = True, abre em nova aba UMA vez e desliga a flag
if st.session_state.wa_should_open and st.session_state.wa_link:
    components.html(
        f"""
        <script>
          // tenta abrir em nova aba
          window.open("{st.session_state.wa_link}", "_blank");
        </script>
        """,
        height=0,
    )
    st.session_state.wa_should_open = False


# ======================
# CLIENTE (form = UX melhor)
# ======================
st.subheader("Agende seu horário")

ocupados = set()
horario_escolhido = None

with st.form("form_agendamento", clear_on_submit=False):
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
        horario_escolhido = st.radio(
            "Escolha um horário",
            disponiveis,
            label_visibility="collapsed"
        )
    else:
        st.warning("Nenhum horário disponível")
        horario_escolhido = None

    confirmar = st.form_submit_button("Confirmar Agendamento 💅")

if confirmar:
    if not nome or not horario_escolhido:
        st.error("Preencha todos os campos.")
    else:
        resp = inserir_agendamento(nome, data_atendimento, horario_escolhido, servico)

        # o client nem sempre joga exception; checa resp.error
        if getattr(resp, "error", None):
            st.error("Esse horário acabou de ser ocupado. Escolha outro.")
        else:
            # gera link e guarda no state (não some)
            st.session_state.wa_link = montar_link_whatsapp(
                nome, data_atendimento, horario_escolhido, servico
            )
            # marca para abrir automaticamente em nova aba
            st.session_state.wa_should_open = True

            st.success("Agendamento registrado! Abrindo o WhatsApp para confirmar… ✅")
            st.toast("Se o navegador bloquear pop-up, use o botão abaixo.", icon="📲")


# ======================
# BLOCO FIXO: CONFIRMAR NO WHATSAPP
# (fica visível até você limpar)
# ======================
if st.session_state.wa_link:
    st.divider()
    st.subheader("📲 Confirmar no WhatsApp")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.link_button("Abrir WhatsApp agora", st.session_state.wa_link)
        st.caption("Se não abrir, copie e cole o link abaixo no navegador:")
        st.code(st.session_state.wa_link)

    with col2:
        if st.button("Limpar confirmação ✅", use_container_width=True):
            st.session_state.wa_link = None
            st.session_state.wa_should_open = False
            st.rerun()


# ======================
# ÁREA ADMIN
# ======================
st.divider()
st.subheader("Área administrativa 🔐")

if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False

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
        data_filtro = st.date_input("Escolha a data", value=date.today(), key="data_filtro")
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
