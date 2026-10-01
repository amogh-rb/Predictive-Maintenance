# Verifying the Helm chart on kind

PLAN §6.3 session 9 / §5 "Deploy: Helm chart ... verified on kind". `helm`
and `kind` were downloaded as standalone binaries (no admin rights needed)
and a real `api` + bitnami `postgresql` install was verified on a real kind
cluster — see `docs/evidence/helm/README.md` for the result and 2 real bugs
that install found and fixed. The full multi-service install below (all app
services + Strimzi + the Flink operator) wasn't run — that's a much heavier
cluster than this dev machine had spare RAM for alongside the already-running
`core` compose stack; these are the commands for doing that fuller pass.

```sh
kind create cluster --name fleetpulse --config infra/k8s-local/kind-config.yaml

# Cluster-scoped operators first (not part of the fleetpulse chart — PLAN §3):
helm repo add strimzi https://strimzi.io/charts/
helm install strimzi strimzi/strimzi-kafka-operator
kubectl apply -f https://github.com/apache/flink-kubernetes-operator/releases/latest/download/flink-kubernetes-operator.yaml

helm repo add bitnami https://charts.bitnami.com/bitnami
helm dependency build infra/helm/fleetpulse

# Build+load images kind can see (no registry needed for a local cluster):
for svc in ingest-gateway state-writer api copilot mcp-server; do
  docker build -f services/$svc/Dockerfile -t fleetpulse-$svc:latest .
  kind load docker-image fleetpulse-$svc:latest --name fleetpulse
done
docker build -t fleetpulse-web:latest ./web
kind load docker-image fleetpulse-web:latest --name fleetpulse

helm install fleetpulse infra/helm/fleetpulse
kubectl get pods -w   # "Done when": all pods Running/Ready
```

`helm lint infra/helm/fleetpulse` and `helm template infra/helm/fleetpulse`
are the quick sanity checks if a full kind cluster isn't handy.
