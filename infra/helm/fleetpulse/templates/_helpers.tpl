{{/* Fully-qualified name for a given service key, e.g. "fleetpulse-api" */}}
{{- define "fleetpulse.serviceName" -}}
{{ .root.Release.Name }}-{{ .name }}
{{- end -}}

{{- define "fleetpulse.labels" -}}
app.kubernetes.io/part-of: fleetpulse
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{- define "fleetpulse.image" -}}
{{- if .root.Values.global.imageRegistry -}}
{{ .root.Values.global.imageRegistry }}/{{ .svc.image }}:{{ .root.Values.global.imageTag }}
{{- else -}}
fleetpulse-{{ .svc.image }}:{{ .root.Values.global.imageTag }}
{{- end -}}
{{- end -}}
