# MapReduce on Kubernetes

Final project for **INF-419 Principles of Distributed Systems**, Technical University of Crete.

## Team

- Stefanos Chatzis — schatzis@tuc.gr
- Ioannis Chalkiopoulos — ichalkiopoulos@tuc.gr

## What it does

A multi-tenant MapReduce platform on Kubernetes. Users submit a job with a custom mapper and reducer (any Python script) plus an input file; the manager service partitions the input, schedules MAP and REDUCE worker pods, handles fault tolerance, and returns the final output via MinIO.

## Services

| Service | Role |
|---|---|
| `authentication_service` | JWT signup / login / user admin |
| `manager_service` | Job & task orchestration, fault-tolerance loop |
| `manager_worker` | Generic worker (runs the user script as a subprocess) |
| `ui_service/cli.py` | Typer-based CLI client |
| MinIO + Postgres ×2 | Object storage and metadata |

## Run it

Kubernetes (used for the demo):

```bash
minikube start --driver=docker --memory=6144 --cpus=2
eval $(minikube docker-env) && docker compose build
bash k8s/scripts/deploy.sh
bash k8s/scripts/deploy_manager.sh
```

Or local docker-compose: `cp example.env .env && docker compose up --build`.

## CLI

```bash
python ui_service/cli.py signup
python ui_service/cli.py login
python ui_service/cli.py jobs submit --input input.txt --mapper map.py --reducer reduce.py --mappers 4 --reducers 2
python ui_service/cli.py jobs status <job_id>
python ui_service/cli.py jobs result <job_id>
```

Pre-loaded benchmarks: **word count** (`map.py` / `reduce.py`) and **inverted index** (`invert_map.py` / `invert_reduce.py`).
