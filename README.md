# Sistema de Recomendación de Hoteles · NLP

**Trabajo Final — Maestría en Inteligencia Artificial · Universidad de San Andrés**  
Equipo: Federico Hofmann · Francisco Moscato · Benjamín Mackinnon

---

## Problema

Los filtros clásicos (estrellas, precio, amenities) no resuelven consultas como:

> *"Quiero algo tranquilo con linda vista al mar y buen desayuno en Río"*

Este sistema sí.

---

## Solución

Usamos **251.000 reviews reales de viajeros** como fuente de conocimiento. En lugar de etiquetar hoteles a mano, las propias reseñas hablan por ellos: si alguien busca "tranquilo con vista al mar", encontramos los hoteles con más reviews que dicen exactamente eso.

El sistema combina **búsqueda semántica** (qué dicen las reseñas) con **atributos estructurados** (extraídos por LLM) en un pipeline de 4 módulos.

---

## Módulos

| # | Notebook | Descripción |
|---|----------|-------------|
| 1 | `01_exploratory_data_analysis.ipynb` | Limpieza del dataset: 404k → 251k reviews en 67 destinos LatAm |
| 2 | `02_review_structuring.ipynb` | Extracción de 14 atributos por hotel con Qwen2.5-3B (vLLM) → `Data/hoteles.db` |
| 3 | `03_review_embeddings.ipynb` | Embeddings con `paraphrase-multilingual-MiniLM-L12-v2` → ChromaDB |
| 4 | `04_recommendation_system_chatbot.ipynb` | Agente LangChain + GPT-4o-mini + chatbot conversacional |

---

## Pipeline de recomendación

```
Usuario: "Hotel en Cartagena con buena vista y buena limpieza"
   │
   ├─ Lista A · Motor semántico (ChromaDB + sentence-transformers)
   │     Embedding de la consulta → top 300 reviews afines → agregado por hotel
   │     score_semantico = score_promedio × log(1 + reviews_afines)
   │     → top 20 candidatos
   │
   ├─ Lista B · Motor estructurado (hoteles.db)
   │     GPT-4o-mini traduce la consulta a SQL
   │     AND para requisitos duros / OR para preferencias
   │     score_hotel() normaliza por columna y suma
   │     → top 20 candidatos
   │
   └─ Ranking híbrido
         A ∩ B → recomendaciones principales
                 hybrid_score = 0.5 × semantic_score_norm + 0.5 × structured_score_norm
         A − B → alternativas semánticas (top 2)
         B − A → alternativas estructuradas (top 2)
```

---

## Dataset

404.760 reviews reales de Despegar sobre hoteles en Latinoamérica, en español y portugués, cubriendo 67 ciudades y 2.523 hoteles.

Criterios de curación (módulo 1):
- Solo reviews en español y portugués (inglés: 0.07% → excluido)
- Mínimo 20 reviews por hotel (garantiza señal suficiente)
- Mínimo 15 hoteles por ciudad (garantiza que la comparación sea útil)

---

## Datos

| Path | Descripción |
|------|-------------|
| `Data/Raw/` | Dataset original de reviews (no incluido) |
| `Data/Final/` | Reviews curadas (no incluido) |
| `Data/VectorDB/` | Índice ChromaDB (no incluido) |
| `Data/hoteles.db` | Atributos estructurados · 2.523 hoteles × 14 columnas |
| `Scripts/config_features.yaml` | Definición de las 14 categorías de atributos |

---

## Stack

| Componente | Tecnología |
|------------|------------|
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers) |
| Base vectorial | ChromaDB |
| Extracción de atributos (módulo 2) | Qwen2.5-3B-Instruct vía vLLM (Docker local) |
| Agente / SQL / chatbot (módulo 4) | LangChain + GPT-4o-mini (OpenAI) |
| Base estructurada | SQLite (`hoteles.db`) |
| Backend embeddings search | FAISS → ChromaDB |

---

## Demo — chatbot_app

`chatbot_app/` es una interfaz web para probar el sistema en vivo. Implementa exactamente el pipeline del módulo 4: mismo agente, mismos motores, misma lógica de intersección.

**Estructura**

```
chatbot_app/
├── backend.py       # servidor FastAPI — define los endpoints HTTP
├── recommender.py   # todo el pipeline (agente, motores, scoring)
└── static/
    ├── index.html   # UI
    ├── script.js    # lógica del frontend (vanilla JS, sin build)
    └── style.css    # estilos
```

**Requisitos previos**

- Haber corrido los notebooks 02 y 03 (necesita `Data/hoteles.db` y `Data/VectorDB/`)
- Tener una `OPENAI_API_KEY` en un archivo `.env` en la raíz del proyecto

```
OPENAI_API_KEY=sk-...
```

**Cómo levantar**

```bash
uvicorn chatbot_app.backend:app --reload --port 8000
```

Luego abrir `http://localhost:8000` en el navegador. El servidor tarda ~15 segundos en arrancar mientras carga el modelo de embeddings y ChromaDB.
