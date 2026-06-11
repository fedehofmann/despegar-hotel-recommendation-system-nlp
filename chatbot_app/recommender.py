"""
Motor de recomendación de hoteles.

Implementa el pipeline híbrido del notebook 04
(04_recommendation_system_chatbot.ipynb):

  Motor A  — búsqueda semántica (ChromaDB + sentence-transformers)
  Motor B  — motor estructurado (GPT-4o-mini genera SQL → hoteles.db)
  Híbrido  — A∩B como principales · A−B y B−A como alternativas
"""

# Librerías
import os
import re
import json
import sqlite3
import unicodedata
import warnings
import yaml
import pandas as pd
import numpy as np
import chromadb
from typing import Optional

from dotenv import load_dotenv

warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ── Rutas ──────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE, "Data", "VectorDB")
PARQUET_PATH = os.path.join(BASE, "Data", "Final", "eda_final_dataset.parquet")
SQLITE_PATH = os.path.join(BASE, "Data", "hoteles.db")
YAML_PATH = os.path.join(BASE, "Scripts", "config_features.yaml")

# ── Constantes — mismas que notebook 04 ────────────────────────────────────────
TOP_K_REVIEWS = 300 # Reviews a recuperar de ChromaDB antes de agregar por hotel
TOP_K_SEMANTICO = 20 # Candidatos del motor semántico (Lista A)
TOP_K_ESTRUCTURADO = 20 # Candidatos del motor estructurado (Lista B)
TOP_N_PRINCIPALES = 5 # Recomendaciones principales a devolver (A∩B)
TOP_N_ALTERNATIVAS = 2 # Alternativas por tipo (A−B y B−A)

# Atributos definidos en Scripts/config_features.yaml
ATRIBUTOS_VALIDOS = {
    "wifi", "vista", "ubicacion", "ruido", "limpieza", "transporte",
    "personal", "desayuno", "restaurante", "habitacion",
    "aire_acondicionado", "estacionamiento", "seguridad", "checkin",
}

# Keywords prohibidos para prevenir SQL injection
_SQL_FORBIDDEN = ("drop", "delete", "update", "insert", "alter", "create", "union", "--", ";")

# ── Singletons — cargados en init() ───────────────────────────────────────────
_modelo = None # SentenceTransformer
_coleccion = None # ChromaDB collection "reviews_hoteles"
_destinos = [] # Lista de destinos válidos (formato "País - Ciudad")
_nombres_por_id = {} # {hotel_id_review: nombre} para enriquecer resultados del motor B
_conn = None # SQLite — hoteles.db
_llm = None # ChatOpenAI(gpt-4o-mini)
_executor = None # LangChain AgentExecutor
_last_result = None # último resultado del pipeline (lo lee chat() después del agente)
_query_prompt = "" # QUERY_GENERATOR_PROMPT construido desde el YAML en init()


# ─────────────────────────────────────────────────────────────────────────────
# Inicialización
# ─────────────────────────────────────────────────────────────────────────────

def init():
    """Carga todos los recursos y construye el agente LangChain. Llamar UNA VEZ al startup."""
    global _modelo, _coleccion, _destinos, _nombres_por_id, _conn
    global _llm, _executor, _query_prompt

    from sentence_transformers import SentenceTransformer
    from langchain_openai import ChatOpenAI
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.tools import tool

    load_dotenv()

    # 1. Modelo de embeddings — mismo que notebook 03
    _modelo = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    # 2. ChromaDB — colección construida en notebook 03
    cliente = chromadb.PersistentClient(path = CHROMA_PATH)
    _coleccion = cliente.get_collection(name = "reviews_hoteles")

    # 3. Destinos válidos y mapeo hotel_id → nombre (del dataset final del módulo 1)
    df_ref = pd.read_parquet(PARQUET_PATH, columns=["hotel_id_review", "name", "destino"])
    _destinos = sorted(df_ref["destino"].unique().tolist())
    _nombres_por_id = (
        df_ref.drop_duplicates("hotel_id_review")
              .set_index("hotel_id_review")["name"]
              .to_dict()
    )

    # 4. SQLite — hoteles.db construido en notebook 02
    _conn = sqlite3.connect(SQLITE_PATH, check_same_thread = False)

    # 5. LLM — GPT-4o-mini, igual que notebook 04
    _llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # 6. Prompt SQL — construido dinámicamente desde el YAML, igual que notebook 04
    with open(YAML_PATH, "r", encoding = "utf-8") as f:
        config = yaml.safe_load(f)
    categorias_texto = "\n".join(
        f'- {c["nombre"]}: score de {c["descripcion"]}'
        for c in config["categorias"]
    )
    _query_prompt = _build_query_prompt(categorias_texto)

    # 7. Tools del agente — mismas dos tools que notebook 04

    @tool
    def listar_destinos_disponibles() -> list:
        """Devuelve los destinos disponibles en el sistema. Formato: 'País - Ciudad'."""
        return _destinos

    @tool
    def buscar_hoteles_hibrido(
        destino: str,
        consulta_semantica: str,
        consulta_atributos: str,
        top_n_principales: int = 5,
        top_n_alternativas: int = 2,
    ) -> str:
        """
        Recomienda hoteles usando el sistema híbrido (motor semántico + motor estructurado).

        Parámetros:
        - destino: destino validado, formato 'País - Ciudad'.
        - consulta_semantica: parte descriptiva/subjetiva de la consulta del usuario.
          Ejemplos: 'hotel tranquilo para descansar', 'vista al mar', 'romántico para pareja'.
        - consulta_atributos: atributos concretos mencionados por el usuario.
          Mantener palabras como 'fundamental' o 'imprescindible' si el usuario las usa.
          Ejemplos: 'con buen desayuno y vista', 'fundamental limpieza y wifi'.
        - top_n_principales: cantidad de hoteles principales a devolver (A∩B).
        - top_n_alternativas: cantidad de alternativas por tipo (A−B y B−A).
        """
        global _last_result
        resultado = _pipeline_hibrido(
            destino, consulta_semantica, consulta_atributos,
            top_n_principales, top_n_alternativas,
        )
        _last_result = resultado

        # Devolvemos solo los nombres al LLM para que redacte la respuesta.
        # Los datos estructurados (cards, reviews, atributos) los lee chat() desde _last_result.
        nombres = [h["name"] for h in resultado["hoteles"]]
        lista   = "\n".join(f"- {n}" for n in nombres)
        return (
            f"Encontré {len(nombres)} hoteles en {destino}:\n{lista}\n\n"
            "Describí cada hotel en una oración respondiendo al pedido del usuario. "
            "No menciones scores ni cifras. Respondé en español."
        )

    tools = [listar_destinos_disponibles, buscar_hoteles_hibrido]

    # 8. System prompt — idéntico al del notebook 04
    system_prompt = """Sos un asistente experto en recomendación de hoteles para turistas en Latinoamérica.

Tu trabajo es interpretar lo que el usuario busca y usar las herramientas disponibles para darle recomendaciones explicables y personalizadas.

REGLAS DE USO:

1. Siempre que el usuario mencione un destino, verificá que existe usando 'listar_destinos_disponibles'.
   - Los destinos tienen el formato 'País - Ciudad' (ej: 'Brasil - Rio De Janeiro').
   - Si el usuario menciona solo la ciudad, inferí el destino completo desde la lista.
   - Si el destino no existe, decíselo amablemente y sugerí destinos similares disponibles.

2. Para recomendar hoteles, usá 'buscar_hoteles_hibrido'.

3. Antes de llamar a 'buscar_hoteles_hibrido', separé la consulta del usuario en dos partes:

   - consulta_semantica: intención descriptiva o subjetiva del usuario.
     No la reduzcas demasiado. Incluir palabras como tranquilo, romántico, familiar,
     cerca de la playa, vista al mar, ideal para trabajar o descansar.
     Ejemplos: 'hotel tranquilo para descansar', 'linda vista al mar', 'romántico para pareja'.

   - consulta_atributos: atributos concretos del hotel que puedan mapearse a categorías
     del sistema: wifi, vista, ubicacion, ruido, limpieza, transporte, personal, desayuno,
     restaurante, habitacion, aire_acondicionado, estacionamiento, seguridad, checkin.
     Mantener palabras como 'fundamental' o 'imprescindible' si el usuario las usa.
     Ejemplos: 'con buen desayuno y vista', 'fundamental limpieza y wifi'.

4. Al presentar los resultados:
   - Describí cada hotel en una oración respondiendo al pedido del usuario.
   - No menciones scores ni cifras técnicas.

5. Respondé en español (o portugués si el usuario escribe en portugués).
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agente = create_tool_calling_agent(_llm, tools, prompt)
    _executor = AgentExecutor(
        agent = agente,
        tools = tools,
        verbose = False,
        max_iterations = 5,
        handle_parsing_errors = True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline híbrido
# ─────────────────────────────────────────────────────────────────────────────

def _pipeline_hibrido(
    destino: str,
    consulta_semantica: str,
    consulta_atributos: str,
    top_n_principales: int = TOP_N_PRINCIPALES,
    top_n_alternativas: int = TOP_N_ALTERNATIVAS,
) -> dict:
    """
    Pipeline híbrido — replica obtener_ranking_hibrido() del notebook 04.

    1. Motor A: ChromaDB → top TOP_K_SEMANTICO candidatos semánticos.
    2. Motor B: GPT-4o-mini genera SQL → hoteles.db → top TOP_K_ESTRUCTURADO candidatos.
    3. A∩B → principales con hybrid_score = 0.5×sem + 0.5×estr.
    4. A−B → alternativas semánticas.
    5. B−A → alternativas estructuradas.
    """
    ranking_sem = _motor_semantico(consulta_semantica, destino)
    ranking_estr, query_sql = _motor_estructurado(destino, consulta_atributos)

    ids_A = set(ranking_sem["hotel_id"].tolist())
    ids_B = set(ranking_estr["hotel_id"].tolist()) if not ranking_estr.empty else set()

    ids_principales = ids_A & ids_B
    ids_alt_semantico = ids_A - ids_B
    ids_alt_estructurado = ids_B - ids_A

    # ── Principales (A∩B) ─────────────────────────────────────────────────────
    if ids_principales:
        sem_cols  = ["hotel_id", "hotel_name", "semantic_score_norm",
                     "score_promedio", "reviews_afines", "ejemplos_reviews"]
        estr_cols = ["hotel_id", "structured_score_norm"]

        df_p = (
            ranking_sem[ranking_sem["hotel_id"].isin(ids_principales)][sem_cols]
            .merge(
                ranking_estr[ranking_estr["hotel_id"].isin(ids_principales)][estr_cols],
                on = "hotel_id", how = "inner",
            )
        )
        # hybrid_score = 0.5×semántico + 0.5×estructurado (notebook 04)
        df_p["hybrid_score"] = (
            0.5 * df_p["semantic_score_norm"] + 0.5 * df_p["structured_score_norm"]
        )
        df_p = df_p.sort_values("hybrid_score", ascending = False).head(top_n_principales)
    else:
        # Sin intersección: usar semánticos como principales (no dejar sin resultados)
        df_p = ranking_sem.head(top_n_principales).copy()
        df_p["hybrid_score"] = df_p["semantic_score_norm"]

    # ── Alternativas semánticas (A−B) ─────────────────────────────────────────
    df_alt_sem = (
        ranking_sem[ranking_sem["hotel_id"].isin(ids_alt_semantico)]
        .sort_values("semantic_score_norm", ascending = False)
        .head(top_n_alternativas)
    ) if ids_principales else pd.DataFrame()  # si no hubo intersección ya están en principales

    # ── Alternativas estructuradas (B−A) ──────────────────────────────────────
    df_alt_estr = (
        ranking_estr[ranking_estr["hotel_id"].isin(ids_alt_estructurado)]
        .sort_values("structured_score_norm", ascending = False)
        .head(top_n_alternativas)
    ) if not ranking_estr.empty else pd.DataFrame()

    # ── Atributos raw de hoteles.db para los chips del frontend ───────────────
    todos_ids = list(
        set(df_p["hotel_id"].tolist())
        | (set(df_alt_sem["hotel_id"].tolist()) if not df_alt_sem.empty else set())
        | (set(df_alt_estr["hotel_id"].tolist()) if not df_alt_estr.empty else set())
    )
    atributos_por_hotel = _atributos_db(todos_ids)

    # ── Must/nice del SQL para los chips ──────────────────────────────────────
    must_haves, nice_to_haves = _parse_must_nice(query_sql) if query_sql else ([], [])

    # ── Serializar resultados ─────────────────────────────────────────────────
    def _fmt_principal(row):
        hid = int(row["hotel_id"])
        return {
            "name":            row["hotel_name"],
            "score":           round(float(row["hybrid_score"]), 3),
            "reviews_afines":  int(row["reviews_afines"]) if "reviews_afines" in row.index else 0,
            "ejemplos_reviews": row["ejemplos_reviews"] if "ejemplos_reviews" in row.index else [],
            "atributos":       atributos_por_hotel.get(hid, {}),
        }

    def _fmt_alt_sem(row):
        hid = int(row["hotel_id"])
        return {
            "name":            row["hotel_name"],
            "score":           round(float(row["semantic_score_norm"]), 3),
            "reviews_afines":  int(row["reviews_afines"]),
            "ejemplos_reviews": row["ejemplos_reviews"],
            "atributos":       atributos_por_hotel.get(hid, {}),
        }

    def _fmt_alt_estr(row):
        hid = int(row["hotel_id"])
        return {
            "name":            _nombres_por_id.get(hid, "Hotel desconocido"),
            "score":           round(float(row["structured_score_norm"]), 3),
            "reviews_afines":  0,
            "ejemplos_reviews": [],
            "atributos":       atributos_por_hotel.get(hid, {}),
        }

    return {
        "destino":                   destino,
        "hoteles":                   [_fmt_principal(r) for _, r in df_p.iterrows()],
        "alternativas_semanticas":   [_fmt_alt_sem(r) for _, r in df_alt_sem.iterrows()] if not df_alt_sem.empty else [],
        "alternativas_estructuradas": [_fmt_alt_estr(r) for _, r in df_alt_estr.iterrows()] if not df_alt_estr.empty else [],
        "filtro": {
            "aplicado":    bool(query_sql and ids_B),
            "must_haves":  must_haves,
            "nice_to_haves": nice_to_haves,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Motor A — semántico
# ─────────────────────────────────────────────────────────────────────────────

def _motor_semantico(consulta: str, destino: str) -> pd.DataFrame:
    """
    Motor A — búsqueda semántica con ChromaDB.
    Replica obtener_ranking_semantico() del notebook 04.

    Vectoriza la consulta → recupera TOP_K_REVIEWS reviews afines del destino →
    agrega por hotel → score = score_promedio × log(1 + reviews_afines) →
    normaliza a [0,1] → devuelve top TOP_K_SEMANTICO hoteles.
    """
    q_emb = _modelo.encode(
        [consulta], convert_to_numpy = True, normalize_embeddings = True
    ).astype("float32").tolist()

    res = _coleccion.query(
        query_embeddings=q_emb,
        n_results=TOP_K_REVIEWS,
        where={"destino": destino},
        include=["documents", "metadatas", "distances"],
    )

    # ChromaDB devuelve distancia coseno → convertimos a similitud
    similitudes = [1 - d for d in res["distances"][0]]
    metadatas   = res["metadatas"][0]
    documentos  = res["documents"][0]

    recuperadas = pd.DataFrame({
        "hotel_id":   [m["hotel_id"]   for m in metadatas],
        "hotel_name": [m["hotel_name"] for m in metadatas],
        "texto":      documentos,
        "score":      similitudes,
    })

    # Agrega por hotel: score = score_promedio × log(1 + reviews_afines)
    agregado = (
        recuperadas.groupby(["hotel_id", "hotel_name"])
        .agg(score_promedio = ("score", "mean"), reviews_afines = ("score", "size"))
        .reset_index()
    )
    agregado["semantic_score"] = agregado["score_promedio"] * np.log1p(agregado["reviews_afines"])

    # Normaliza a [0, 1]
    max_sem = agregado["semantic_score"].max()
    agregado["semantic_score_norm"] = agregado["semantic_score"] / max_sem if max_sem > 0 else 0.0

    # Top-3 reviews afines por hotel (para mostrar en las cards del frontend)
    agregado["ejemplos_reviews"] = agregado["hotel_id"].apply(
        lambda hid: (
            recuperadas[recuperadas["hotel_id"] == hid]
            .sort_values("score", ascending = False)
            .head(3)["texto"]
            .tolist()
        )
    )

    return (
        agregado.sort_values("semantic_score", ascending = False)
        .head(TOP_K_SEMANTICO)
        .reset_index(drop=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Motor B — estructurado
# ─────────────────────────────────────────────────────────────────────────────

def _motor_estructurado(destino: str, consulta_atributos: str) -> tuple:
    """
    Motor B — scoring por atributos estructurados.
    Replica obtener_ranking_estructurado() del notebook 04.

    GPT-4o-mini genera SQL → ejecuta contra hoteles.db →
    score_hotel() normaliza y suma → normaliza a [0,1] →
    devuelve (DataFrame top TOP_K_ESTRUCTURADO, query_sql generada).
    """
    query_sql = _generar_sql(destino, consulta_atributos)
    if not query_sql:
        return pd.DataFrame(), None

    try:
        df = pd.read_sql_query(query_sql, _conn)
    except Exception:
        return pd.DataFrame(), query_sql

    if df.empty:
        return pd.DataFrame(), query_sql

    df = _score_hotel(df)

    # Normaliza a [0, 1] para poder combinarlo con el score semántico
    max_estr = df["hotel_score"].max()
    df["structured_score_norm"] = df["hotel_score"] / max_estr if max_estr > 0 else 0.0
    df["structured_score"] = df["hotel_score"]

    # Renombra la PK para consistencia con el motor semántico
    df = df.rename(columns={"hotel_id_review": "hotel_id"})

    return df.head(TOP_K_ESTRUCTURADO).reset_index(drop=True), query_sql


def _score_hotel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza scores de atributos por columna (max-scaling) y suma en hotel_score.
    Replica exactamente score_hotel() del notebook 02 y 04.
    """
    cols_excluir = {"hotel_id_review", "destino"}
    score_cols   = [c for c in df.columns if c not in cols_excluir]

    out = df.copy()
    out[score_cols] = out[score_cols].clip(lower=0)  # negativos → 0

    for col in score_cols:
        max_val = out[col].max()
        out[col] = out[col] / max_val if max_val > 0 else 0.0

    out["hotel_score"] = out[score_cols].sum(axis=1)
    return out.sort_values("hotel_score", ascending=False)


def _generar_sql(destino: str, consulta: str) -> Optional[str]:
    """
    Usa GPT-4o-mini para traducir la consulta a SQL.
    Replica generar_query_sql() del notebook 04.
    """
    if not consulta or not consulta.strip():
        return None

    # Indicamos el destino exacto al inicio del mensaje, igual que notebook 04
    mensaje = f"Destino a usar EXACTAMENTE: '{destino}'\nConsulta del usuario: {consulta}"
    try:
        respuesta = _llm.invoke([
            ("system", _query_prompt),
            ("human", mensaje),
        ])
        data = json.loads(respuesta.content.strip())
        sql  = data.get("query", "")
    except Exception:
        return None

    # Guard básico contra SQL injection
    if any(kw in sql.lower() for kw in _SQL_FORBIDDEN):
        return None

    return sql


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _atributos_db(hotel_ids: list) -> dict:
    """
    Devuelve {hotel_id: {atributo: score_raw}} con todos los atributos > 0.
    Una sola query a hoteles.db para enriquecer las cards del frontend.
    """
    if not hotel_ids or _conn is None:
        return {}
    placeholders = ",".join("?" * len(hotel_ids))
    cols_str = ", ".join(sorted(ATRIBUTOS_VALIDOS))
    query = (
        f"SELECT hotel_id_review, {cols_str} FROM hoteles "
        f"WHERE hotel_id_review IN ({placeholders})"
    )
    try:
        df = pd.read_sql_query(query, _conn, params=hotel_ids)
    except Exception:
        return {}
    return {
        int(row["hotel_id_review"]): {
            c: int(row[c]) for c in ATRIBUTOS_VALIDOS if row[c] > 0
        }
        for _, row in df.iterrows()
    }


def _parse_must_nice(sql: str) -> tuple:
    """
    Extrae must_haves (AND) y nice_to_haves (OR) del WHERE generado.
    Usado para colorear los chips de atributos en el frontend:
      - must_haves  → chip cyan  (imprescindible)
      - nice_to_haves → chip violeta (preferencia)
    """
    if not sql:
        return [], []

    # Extraemos el bloque de condiciones después de destino = '...' AND
    m = re.search(
        r"destino\s*=\s*['\"][^'\"]+['\"]\s*AND\s+(.+?)$",
        sql, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return [], []
    where = m.group(1).strip().rstrip(";")

    # Atributos dentro de paréntesis → nice (OR); el resto → must (AND)
    paren = re.search(r"\(([^)]+)\)", where)
    if paren:
        nice = [t for t in re.findall(r"[a-z_]+", paren.group(1).lower()) if t in ATRIBUTOS_VALIDOS]
        rest = where.replace(paren.group(0), "")
        must = [t for t in re.findall(r"[a-z_]+", rest.lower()) if t in ATRIBUTOS_VALIDOS]
    else:
        must = [t for t in re.findall(r"[a-z_]+", where.lower()) if t in ATRIBUTOS_VALIDOS]
        nice = []

    return _dedup(must), _dedup(nice)


def _fuzzy_destino(destino: str) -> Optional[str]:
    """Matchea el destino del usuario contra los destinos válidos, tolerando variaciones."""
    if destino in _destinos:
        return destino
    partes = [p for p in _normalize(destino).replace("-", " ").split() if len(p) > 2]
    mejor, mejor_score = None, 0
    for d in _destinos:
        score = sum(1 for p in partes if p in _normalize(d))
        if score > mejor_score:
            mejor_score, mejor = score, d
    return mejor if mejor_score >= 1 else None


def _normalize(s: str) -> str:
    """Quita tildes y convierte a minúsculas para comparaciones fuzzy."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


def _dedup(lst: list) -> list:
    """Elimina duplicados preservando orden."""
    seen, out = set(), []
    for x in lst:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _build_query_prompt(categorias_texto: str) -> str:
    """Construye el QUERY_GENERATOR_PROMPT con las categorías del YAML. Replica notebook 04."""
    return f"""
Sos un generador de queries SQL.
Tu tarea es entender las necesidades hoteleras del usuario y traducirlas a una query SQL válida.

IMPORTANTE: el sistema te va a indicar el destino EXACTO al inicio del mensaje del usuario
(en la línea "Destino a usar EXACTAMENTE: '...'"). Usá ese destino exactamente, sin modificarlo.

Devolvé SOLO un JSON válido con esta estructura:
{{"query": "..."}}

No agregues explicaciones, markdown ni texto adicional.

Nombre de la tabla: hoteles

Columnas disponibles:
- hotel_id_review: identificador del hotel
- destino: lugar donde se encuentra el hotel
{categorias_texto}

Template SQL obligatorio:
SELECT hotel_id_review, destino, <<categorias mencionadas>>
FROM hoteles
WHERE destino = '<<destino exacto>>'
AND <<condiciones por categoría>>

Reglas para las condiciones:

1) Identificá las categorías relevantes mencionadas por el usuario.

2) Clasificá cada categoría:

   - IMPORTANTE: alta prioridad ("fundamentalmente", "es clave", "necesito sí o sí").
     → AND categoria > 0

   - NO IMPORTANTE: preferencia deseable ("me gustaría", "con buena vista", "ojalá").
     → dentro de un bloque OR: (1=1 OR categoria > 0)

3) Si hay IMPORTANTES y NO IMPORTANTES: IMPORTANTES con AND, bloque OR conectado con AND.

4) Si solo hay NO IMPORTANTES: AND (1=1 OR categoria_a > 0 OR categoria_b > 0)

5) Si solo hay IMPORTANTES: AND categoria_a > 0 AND categoria_b > 0

Ejemplo:

Entrada:
Destino a usar EXACTAMENTE: 'Brasil - Rio De Janeiro'
Consulta del usuario: Quiero un hotel con buena vista y buen desayuno. Es fundamental una buena ubicacion.

Respuesta:
{{"query": "SELECT hotel_id_review, destino, ubicacion, vista, desayuno FROM hoteles WHERE destino = 'Brasil - Rio De Janeiro' AND ubicacion > 0 AND (1=1 OR vista > 0 OR desayuno > 0)"}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def _respuesta_vacia(mensaje: str, error=None) -> dict:
    """Estructura de respuesta vacía (sin hoteles)."""
    return {
        "response":                   mensaje,
        "hoteles":                    [],
        "alternativas_semanticas":    [],
        "alternativas_estructuradas": [],
        "destination":                None,
        "filtro": {"aplicado": False, "must_haves": [], "nice_to_haves": []},
        "error":  error,
    }


def list_destinations() -> list:
    return _destinos


def chat(message: str) -> dict:
    """Corre el agente LangChain + GPT-4o-mini. Devuelve respuesta + datos estructurados."""
    global _last_result
    _last_result = None
    try:
        result = _executor.invoke({"input": message})
        output = result.get("output", "")

        if _last_result:
            return {
                "response":                   output,
                "hoteles":                    _last_result["hoteles"],
                "alternativas_semanticas":    _last_result["alternativas_semanticas"],
                "alternativas_estructuradas": _last_result["alternativas_estructuradas"],
                "destination":                _last_result["destino"],
                "filtro":                     _last_result["filtro"],
                "error":                      None,
            }
        return _respuesta_vacia(output)

    except Exception as e:
        return _respuesta_vacia("Ocurrió un error procesando tu consulta. Intentá de nuevo.", str(e))


def direct_search(query: str, destination: str, top_n: int = 5) -> dict:
    """Búsqueda directa sin agente. Usa la misma consulta para ambos motores."""
    destino = _fuzzy_destino(destination)
    if not destino:
        return _respuesta_vacia(
            f"El destino '{destination}' no está disponible. Solo cubrimos Latinoamérica.",
            "destination_not_found",
        )
    resultado = _pipeline_hibrido(destino, query, query, top_n, TOP_N_ALTERNATIVAS)
    return {
        "response":                   f"Resultados para '{query}' en {destino}.",
        "hoteles":                    resultado["hoteles"],
        "alternativas_semanticas":    resultado["alternativas_semanticas"],
        "alternativas_estructuradas": resultado["alternativas_estructuradas"],
        "destination":                destino,
        "filtro":                     resultado["filtro"],
        "error":                      None,
    }
