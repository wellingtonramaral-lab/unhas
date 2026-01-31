import streamlit as st
import pandas as pd
import os
from datetime import date

# ===== Configuração da página =====
st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ===== Arquivo CSV =====
CSV_FILE = "agendamentos.csv"

# Criar CSV se não existir ou estiver vazio
if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
    df_init = pd.DataFrame(columns=["Cliente", "Data", "Horário", "Serviço"])
    df_init.to_csv(CSV_FILE, index=False)

# ===== Função para sempre recarregar os dados =====
def carregar_dados():
    return pd.read_csv(CSV_FILE)

# ===== Carregar dados =====
df = carregar_dados()

# ===== Entradas =====
nome = st.text_input("Nome da cliente")
data = st.date_input("Data do atendimento", min_value=date.today())
servico = st.selectbox(
    "Tipo de serviço",
    ["Alongamento em Gel", "Alongamento em Fibra de Vidro", "Pedicure"]
)

# ===== Horários possíveis =====
horarios = ["07:00", "08:30", "10:00", "13:30", "15:00", "16:30", "18:00"]

df_data = df[df["Data"] == str(data)]
disponiveis = [h for h in horarios if h not in df_data["Horário"].values]

# ===== Horários disponíveis (ROLÁVEL) =====
st.subheader("Horários disponíveis")

if disponiveis:
    with st.container(height=180):
        horario_selecionado = st.radio(
            "Escolha um horário:",
            options=disponiveis,
            label_visibility="collapsed"
        )
else:
    st.warning("Nenhum horário disponível para esta data.")
    horario_selecionado = None

# ===== Confirmar agendamento =====
if st.button("Confirmar Agendamento 💅"):
    if not nome:
        st.error("Preencha o nome da cliente.")
        st.stop()

    if not horario_selecionado:
        st.error("Selecione um horário disponível.")
        st.stop()

    # Recarregar antes de salvar (segurança)
    df = carregar_dados()

    # Verificar se o horário ainda está livre
    conflito = (
        (df["Data"] == str(data)) &
        (df["Horário"] == horario_selecionado)
    ).any()

    if conflito:
        st.error("Esse horário acabou de ser ocupado. Atualize a página.")
        st.stop()

    novo = pd.DataFrame(
        [[nome, str(data), horario_selecionado, servico]],
        columns=["Cliente", "Data", "Horário", "Serviço"]
    )

    df = pd.concat([df, novo], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

    st.success(
        f"Agendamento confirmado: {nome} - {data} às {horario_selecionado} ({servico})"
    )
    st.rerun()

# ===== Cancelar agendamento =====
st.subheader("Cancelar agendamento")

df = carregar_dados()
df_data = df[df["Data"] == str(data)]

if not df_data.empty:
    opcoes = [
        f"{row['Cliente']} às {row['Horário']} ({row['Serviço']})"
        for _, row in df_data.iterrows()
    ]

    cancelar = st.selectbox("Selecione um agendamento:", opcoes)

    if st.button("Cancelar Agendamento ❌"):
        index_cancelar = df_data.index[
            df_data.apply(
                lambda row: f"{row['Cliente']} às {row['Horário']} ({row['Serviço']})" == cancelar,
                axis=1
            )
        ][0]

        df = df.drop(index_cancelar)
        df.to_csv(CSV_FILE, index=False)

        st.success(f"Agendamento cancelado: {cancelar}")
        st.rerun()
else:
    st.info("Nenhum agendamento para esta data.")

# ===== Agenda do dia =====
st.subheader("Agenda do dia")

df = carregar_dados()
df_display = df[df["Data"] == str(data)].sort_values("Horário")

if df_display.empty:
    st.info("Nenhum agendamento para esta data.")
else:
    st.table(df_display)
