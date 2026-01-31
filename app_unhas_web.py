import streamlit as st
import pandas as pd
import os
from datetime import date
import urllib.parse

# ===== CONFIGURAÇÕES =====
SENHA_ADMIN = "1234"  # <<< TROQUE SUA SENHA AQUI
WHATSAPP_NUMERO = "5548988702399"  # <<< SEU WHATSAPP (DDI+DDD+NUMERO)
CSV_FILE = "agendamentos.csv"

st.set_page_config(page_title="Agendamento de Unhas 💅", layout="centered")
st.title("💅 Agendamento de Unhas")

# ===== Criar CSV se não existir ou estiver vazio =====
if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
    pd.DataFrame(columns=["Cliente", "Data", "Horário", "Serviço"]).to_csv(CSV_FILE, index=False)

def carregar_dados():
    # Evita erro caso o CSV esteja corrompido/vazio
    try:
        df = pd.read_csv(CSV_FILE)
        # Garantir colunas
        for c in ["Cliente", "Data", "Horário", "Serviço"]:
            if c not in df.columns:
                df[c] = ""
        return df[["Cliente", "Data", "Horário", "Serviço"]]
    except Exception:
        return pd.DataFrame(columns=["Cliente", "Data", "Horário", "Serviço"])


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
df["Data"] = df["Data"].astype(str)
df["Horário"] = df["Horário"].astype(str)

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
    df["Data"] = df["Data"].astype(str)
    df["Horário"] = df["Horário"].astype(str)

    # Validação: evita duplicar horário no mesmo dia
    if ((df["Data"] == str(data)) & (df["Horário"] == str(horario))).any():
        st.error("Esse horário acabou de ser ocupado")
        st.stop()

    novo = pd.DataFrame(
        [[nome, str(data), str(horario), servico]],
        columns=["Cliente", "Data", "Horário", "Serviço"]
    )

    df = pd.concat([df, novo], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

    mensagem = f"""Olá! Barbára Vitória Gostaria de confirmar meu agendamento:

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

if senha:
    if senha != SENHA_ADMIN:
        st.error("Senha incorreta.")
    else:
        st.success("Acesso liberado ✅")

        df_admin = carregar_dados()
        df_admin["Data"] = df_admin["Data"].astype(str)
        df_admin["Horário"] = df_admin["Horário"].astype(str)

        # Ordenar por Data e Horário
        if not df_admin.empty:
            df_admin = df_admin.sort_values(by=["Data", "Horário"], ascending=True).reset_index(drop=True)

        st.subheader("📋 Agendamentos")

        # Filtro por data (opcional)
        filtrar = st.checkbox("Filtrar por data")
        if filtrar:
            data_filtro = st.date_input("Escolha a data para filtrar", value=date.today(), key="data_filtro")
            df_admin_filtrado = df_admin[df_admin["Data"] == str(data_filtro)]
        else:
            df_admin_filtrado = df_admin

        if df_admin_filtrado.empty:
            st.info("Nenhum agendamento encontrado.")
        else:
            st.dataframe(df_admin_filtrado, use_container_width=True)

            st.subheader("🗑️ Excluir um agendamento")

            opcoes = df_admin_filtrado.apply(
                lambda row: f'{row["Cliente"]} | {row["Data"]} | {row["Horário"]} | {row["Serviço"]}',
                axis=1
            ).tolist()

            escolha = st.selectbox("Selecione o agendamento para excluir", opcoes)

            if st.button("Excluir agendamento selecionado ❌"):
                idx = df_admin_filtrado.index[opcoes.index(escolha)]
                df_admin = df_admin.drop(index=idx).reset_index(drop=True)
                df_admin.to_csv(CSV_FILE, index=False)
                st.success("Agendamento excluído com sucesso ✅")
                st.rerun()

        st.subheader("⬇️ Baixar CSV")
        st.download_button(
            label="Baixar agendamentos.csv",
            data=df_admin.to_csv(index=False).encode("utf-8"),
            file_name="agendamentos.csv",
            mime="text/csv"
        )
