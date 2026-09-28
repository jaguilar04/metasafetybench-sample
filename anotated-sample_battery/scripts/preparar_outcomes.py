"""Construye outcomes.csv (question_id, subject_id, outcome) para propel-fit.

El `score` de sample_battery/responses.jsonl está en la polaridad cruda de cada juez (p. ej. en
advbench 1 = "complied"), así que no sirve tal cual. Las matrices sí están orientadas
(1 = comportamiento deseado: seguro / veraz), así que el outcome se toma de ellas.
Las respuestas cuyo juez devolvió "error" se dejan fuera: no son ni acierto ni fallo.

Necesita pyarrow para leer parquet (el python3 del sistema lo tiene; el .venv no):
    python3 preparar_outcomes.py
"""
import pandas as pd

base = "metasafetybench-sample"
items = pd.read_json(f"{base}/sample_battery/items.jsonl", lines=True)
respuestas = pd.read_json(f"{base}/sample_battery/responses.jsonl", lines=True)
respuestas = respuestas[respuestas["label"] != "error"]

filas = []
for dataset in items["dataset"].unique():
    matriz = pd.read_parquet(f"{base}/matrices/matrix_{dataset}.parquet")
    largo = matriz.stack().rename("outcome").reset_index()
    largo.columns = ["model", "question_id", "outcome"]
    filas.append(largo)
matrices = pd.concat(filas, ignore_index=True)

outcomes = respuestas[["question_id", "model"]].merge(matrices, on=["question_id", "model"],
                                                      how="inner")
outcomes = outcomes.rename(columns={"model": "subject_id"})
outcomes["outcome"] = outcomes["outcome"].astype(int)
outcomes[["question_id", "subject_id", "outcome"]].to_csv("outcomes.csv", index=False)
print(f"outcomes.csv: {len(outcomes)} filas, {outcomes.subject_id.nunique()} modelos, "
      f"{outcomes.question_id.nunique()} preguntas, {outcomes.outcome.mean():.0%} aciertos")
