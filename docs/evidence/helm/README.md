# Helm chart evidence (PLAN §5 "Deploy: Helm chart (HPA, PDB, probes, NetworkPolicy) verified on kind")

`helm`, `kind` and `terraform` weren't preinstalled in this sandbox and
there's no admin access for a normal package-manager install — all three
were downloaded as standalone binaries instead (no install needed) so the
chart could be verified for real rather than left as untested YAML.

**Static checks:**
- `helm lint infra/helm/fleetpulse` — passes.
- `helm dependency build` — resolves and downloads the real `postgresql`/`redis`/`mongodb` bitnami subcharts.
- `helm template fleetpulse infra/helm/fleetpulse` — renders the full manifest set with no errors: `resource_kinds.txt` is the real output kind count (7 Deployments, 4 HPAs, 7 PDBs, 9 NetworkPolicies, 9 Services, plus the bitnami subcharts' own StatefulSets/ConfigMaps/PVCs).
- `api_deployment_example.yaml` — one real rendered Deployment (the `api` service), showing the values (image, env, port) actually substituted correctly.

**Live `kind` cluster install — `kind_pods_running.txt`:**
Created a real `kind` cluster (`infra/k8s-local/kind-config.yaml`), built and
`kind load docker-image`d the real `api` image, and `helm install`ed the
chart (with `redis`/`mongodb` disabled and the other app services scaled to
zero via a values override, to fit the sandbox's spare RAM — postgres +
api is enough to prove the chart mechanics for real). Result: both
`fleetpulse-api` (Deployment) and `fleetpulse-postgresql` (bitnami
StatefulSet) reached `1/1 Running`, and `/healthz` answered `200` through
the real `Service`, not just a `kubectl exec`.

**2 real bugs found and fixed by actually running this, not just templating it:**
1. `imagePullPolicy` was defaulting to Kubernetes' own `Always` (since the image tag is `latest`), which 404s on kind — these images are `kind load docker-image`d locally, never pushed to a registry. Fixed: `templates/deployment.yaml` now sets `imagePullPolicy: IfNotPresent` explicitly.
2. Bitnami stopped publishing new dated tags to the free `docker.io/bitnami/*` repos in 2025 and 404s the older tags each chart version still defaults to (confirmed live: `postgresql:16.4.0-debian-12-r14` 404s, `postgresql:latest` pulls fine) — the same class of issue as session 1's MinIO→Garage swap. Fixed: `values.yaml` pins `image.tag: latest` for all three bitnami dependencies, with a comment that a real production rollout should pin a scanned digest instead.

Torn down cleanly afterward (`helm uninstall`, `kind delete cluster`) and the
paused local `core`-profile containers (`flink-jobmanager/taskmanager`,
`copilot`, `mcp-server`, `grafana`, `prometheus`, `otel-collector`) were
restarted and the Flink job resubmitted — see PROGRESS.md.
