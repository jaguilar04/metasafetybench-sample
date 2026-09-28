"""Anota la batería completa con la Batch API de OpenAI (mitad de precio, corre en sus servidores).

Se puede apagar el ordenador en cualquier momento: el trabajo lo hace OpenAI y el estado se
guarda en disco. Basta con volver a lanzar el mismo comando; cada vez hace lo que falte:

    .venv/bin/python lote.py                  # envía, consulta, recoge y dibuja (idempotente)
    .venv/bin/python lote.py --dims Ul Op     # solo esas dimensiones
    .venv/bin/python lote.py --reintentar     # reenvía solo las filas con error de proveedor

Por dimensión, en anotaciones/<anotador>/:
    {DIM}.jsonl            resultado final; si existe, la dimensión está hecha y no se toca
    {DIM}.jsonl.job.json   lote enviado y aún sin recoger (compatible con `propel-annotate status`)
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from propensity import (get_provider, load_annotations, load_dimensions, load_instances,
                        load_presentation, load_rubric, save_annotation_plots, write_table)
from propensity.annotation import build_requests, collect, rows_from_completions, submit, summarise
from propensity.modelling.io import read_table

parser = argparse.ArgumentParser()
parser.add_argument("--dims", nargs="+", default=None, help="códigos (por defecto las 15)")
parser.add_argument("--instancias", default="metasafetybench-sample/sample_battery/items.jsonl")
parser.add_argument("--modelo", default="gpt-5.1")
parser.add_argument("--reintentar", action="store_true",
                    help="reenviar las filas con error de proveedor de las dimensiones ya hechas")
args = parser.parse_args()

load_dotenv()

provider = get_provider("openai", model=args.modelo, request_options={"reasoning_effort": "none"})
annotator = f"openai:{args.modelo}"
catalogo = load_dimensions()
dims = args.dims or list(catalogo)
salida = Path("anotaciones") / annotator.replace(":", "_")
salida.mkdir(parents=True, exist_ok=True)

instances = load_instances(args.instancias)
presentation = load_presentation()


def enviar(dim, instancias, job_path, reintento=False):
    rubric = load_rubric(dim)
    requests = build_requests(instancias, propensity_name=catalogo[dim].name, rubric=rubric,
                              presentation=presentation)
    batch_id = submit(provider, requests)
    job = {"batch_id": batch_id, "dimension": dim, "reintento": reintento,
           "question_ids": [r.custom_id for r in requests],
           "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")  # antes de nada más
    print(f"[{dim}] enviado lote {batch_id} con {len(requests)} peticiones")


def recoger(dim, job_path, archivo):
    job = json.loads(job_path.read_text(encoding="utf-8"))
    estado = provider.poll_batch(job["batch_id"])
    if estado in ("failed", "cancelled"):
        print(f"[{dim}] el lote {job['batch_id']} terminó como {estado}; se reenvía")
        job_path.unlink()
        return
    if estado != "completed":
        print(f"[{dim}] lote {job['batch_id']}: {estado}")
        return

    ids = set(job["question_ids"])
    instancias = [i for i in instances if i["question_id"] in ids]
    rubric = load_rubric(dim)
    requests = build_requests(instancias, propensity_name=catalogo[dim].name, rubric=rubric,
                              presentation=presentation)
    completions = collect(provider, job["batch_id"], requests)
    rows = rows_from_completions(instancias, completions, dimension=dim,
                                 annotator=annotator, rubric=rubric)
    if job.get("reintento"):  # sustituir solo las filas reintentadas
        previas = [r for r in read_table(archivo).to_dict(orient="records")
                   if r["question_id"] not in ids]
        rows = previas + rows
    write_table(rows, archivo)
    job_path.unlink()
    print(f"[{dim}] recogido: {summarise(rows)}")


for dim in dims:
    archivo = salida / f"{dim}.jsonl"
    job_path = salida / f"{dim}.jsonl.job.json"

    if job_path.exists():
        recoger(dim, job_path, archivo)
        if job_path.exists():  # aún en curso
            continue

    if not archivo.exists():
        if not job_path.exists():
            enviar(dim, instances, job_path)
        continue

    if args.reintentar:
        fallidas = {r["question_id"] for r in read_table(archivo).to_dict(orient="records")
                    if r.get("error")}
        if fallidas:
            enviar(dim, [i for i in instances if i["question_id"] in fallidas], job_path,
                   reintento=True)
            continue
    print(f"[{dim}] hecho")

pendientes = [d for d in dims if not (salida / f"{d}.jsonl").exists()
              or (salida / f"{d}.jsonl.job.json").exists()]
if pendientes:
    print(f"\nPendientes: {' '.join(pendientes)}. Vuelve a lanzar este comando más tarde.")
else:
    anotaciones = pd.concat([load_annotations(a) for a in sorted(salida.glob("*.jsonl"))],
                            ignore_index=True)
    plots = save_annotation_plots(anotaciones, salida / "plots")
    print(f"\nTodo hecho. {len(plots)} plots en {salida / 'plots'}")
