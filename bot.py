
# app.py
import streamlit as st
import pandas as pd
import pyodbc
import json
from openai import AzureOpenAI
from urllib.parse import quote_plus

from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# ───────────────────────────────────────────────
# 1) Configuration — now using environment vars
# ───────────────────────────────────────────────
SQLSERVER_HOST = os.getenv("SQLSERVER_HOST")
SQLSERVER_DB   = os.getenv("SQLSERVER_DB")
SQLSERVER_USER = os.getenv("SQLSERVER_USER")
SQLSERVER_PWD  = os.getenv("SQLSERVER_PWD")

AZURE_OAI_ENDPOINT = os.getenv("AZURE_OAI_ENDPOINT")
AZURE_OAI_MODEL    = os.getenv("AZURE_OAI_MODEL")
AZURE_OAI_API_KEY  = os.getenv("AZURE_OAI_API_KEY")

AZURE_SEARCH_EP  = os.getenv("AZURE_SEARCH_EP")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

is_debugging_enabled = os.getenv("IS_DEBUGGING_ENABLED", "False").lower() == "true"


# ───────────────────────────────────────────────
# 2) Helpers
# ───────────────────────────────────────────────

def debug_log(msg):
    if is_debugging_enabled:
        st.text(f"[DEBUG] {msg}")


def run_sql_on_sqlserver(sql: str) -> pd.DataFrame:
    """Execute the SQL on your SQL Server and return a pandas DataFrame."""
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={SQLSERVER_HOST};"
        f"DATABASE={SQLSERVER_DB};"
        f"UID={SQLSERVER_USER};"
        f"PWD={SQLSERVER_PWD}"
    )
    conn = pyodbc.connect(conn_str)
    df = pd.read_sql(sql, conn)
    return df


def call_llm_generate_sql(prompt: str) -> str:
    client = AzureOpenAI(
        azure_endpoint=AZURE_OAI_ENDPOINT,
        api_key=AZURE_OAI_API_KEY,
        api_version="2025-01-01-preview",
    )
    system_prompt = (
        "You are an AI assistant specialized in transforming natural language into SQL Server queries. "
        "Return only the SQL query without explanations or comments. "
        "The dataset includes embedding vectors representing predefined query patterns. "
        "Use these embeddings to adapt the generated SQL queries, aligning them with patterns found "
        "in the embedding dataset attached to the query."
        "Do not use MySQL/PostgreSQL-specific syntax like LIMIT."  
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": prompt}
    ]

    completion = client.chat.completions.create(
        model=AZURE_OAI_MODEL,
        messages=messages,
        max_tokens=800,
        temperature=0.67,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stream=False,
        extra_body={
            "data_sources": [{
                "type": "azure_search",
                "parameters": {
                    "endpoint": AZURE_SEARCH_EP,
                    "index_name": "serene-diamond-r8pp11ww7f",
                    "authentication": {
                        "type": "api_key",
                        "key": AZURE_SEARCH_KEY
                    },
                    "semantic_configuration": "azureml-default",
                    "query_type": "simple",
                    "filter": None,
                    "in_scope": True,
                    "strictness": 3,
                    "top_n_documents": 5
                }
            }]
        }
    )

    raw = completion.to_json()
    text = json.loads(raw)["choices"][0]["message"]["content"]
    return text.replace("```sql", "").replace("```", "").strip()

# ───────────────────────────────────────────────
# 3) Streamlit UI
# ───────────────────────────────────────────────
st.title("🧠 English → SQL → SSMS Explorer")
st.markdown(
    """
    Enter your question in plain English (for example:  
    *“Show me total sales by month for 2024”*),  
    click **Run**, and this app will:
    1. Generate a SQL query via Azure OpenAI  
    2. Run it against your SQL Server via pyodbc  
    3. Display the raw DataFrame result
    """
)
prompt = st.text_area(
    "Your question:",
    height=100,
    placeholder="e.g. Show me total trips by day in July 2024"
)

if st.button("Run"):
    if not prompt.strip():
        st.error("Please enter a question first.")
    else:
        with st.spinner("Generating SQL…"):
            try:
                sql = call_llm_generate_sql(prompt)
                st.code(sql, language="sql")
            except Exception as e:
                st.error(f"❌ LLM generation failed: {e}")
                st.stop()

        with st.spinner("Executing on SQL Server…"):
            try:
                df = run_sql_on_sqlserver(sql)
                if df.empty:
                    st.warning("⚠️ Query returned no rows.")
                else:
                    st.success(f"Returned {len(df)} rows")
                    st.dataframe(df)
            except Exception as e:
                st.error(f"❌ SQL execution failed: {e}")

