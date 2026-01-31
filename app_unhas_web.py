import streamlit as st
import pandas as pd
import os
from datetime import date
import urllib.parse

# ===== CONFIGURAÇÕES =====
SENHA_ADMIN = "1234"  # <<< TROQUE SUA SENHA AQUI
WHATSAPP_NUMERO = "5548988702399"  # <<< SEU WHATSAPP
CSV_FILE = "agendamentos.csv"

st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ===== Criar CSV =====
if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
    pd.DataFrame(columns=["Cliente", "Data", "Horário", "Serviço"]).to_csv(CSV_FILE, index=False)

def carregar_dados():
    return pd.read_csv(CSV_FILE)

# ===== ENTRADAS CLIENTE =====
st.subheader("Agende seu horário")

nome = st.text_input("Nome da cliente")
data = st.date_input("Data do atendimento", min_value=date.today())
servico = st.selectbox(
    "Tipo de serviço",
    ["Alongamento em Gel", "Alongamento em Fibra de Vidro", "Pedicure"]
)

horarios = ["07:00", "08:30", "10:00", "13:30", "15:00", "16:30", "18:00"]

df = carregar_dados()
df_data = df[df["Data"] == str(data)]
disponiveis = [h for h in horarios if h not in df_data["Horário"].values]

st.subheader("Horários disponíveis")

if disponiveis:
    with st.container(height=180):
        horario = st.radio(
            "Escolha um horário",
            disponiveis,
            label_visibility="collapsed"
        )
else:
    horario = None
    st.warning("Nenhum horário disponível")

# ===== CONFIRMAR AGENDAMENTO =====
if st.button("Confirmar Agendamento 💅"):
    if not nome or not horario:
        st.error("Preencha todos os campos")
        st.stop()

    df = carregar_dados()
    if ((df["Data"] == str(data)) & (df["Horário"] == horario)).any():
        st.error("Esse horário acabou de ser ocupado")
        st.stop()

    novo = pd.DataFrame(
        [[nome, str(data), horario, servico]],
        columns=["Cliente", "Data", "Horário", "Serviço"]
    )

    df = pd.concat([df, novo], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

    mensagem = f"""
Olá! 💅 Gostaria de confirmar meu agendamento:

👩 Cliente: {nome}
📅 Data: {data}
⏰ Horário: {horario}
💅 Serviço: {servico}
"""

    mensagem_url = urllib.parse.quote(mensagem)
    link_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={mensagem_url}"

    st.success("Agendamento registrado! 💖")
    st.markdown(
        f"""
        <a href="{link_whatsapp}" target="_blank">
            <button style="
                background-color:#25D366;
                color:white;
                padding:12px 20px;
                border:none;
                border-radius:8px;
                font-size:16px;
                cursor:pointer;
            ">
                📲 Confirmar no WhatsApp
            </button>
        </a>
        """,
        unsafe_allow_html=True
    )

# ===== ÁREA ADMIN =====
st.divider()
st.subheader("Área administrativa 🔐")

senha = st.text_input("Senha da profissional", type="password")
