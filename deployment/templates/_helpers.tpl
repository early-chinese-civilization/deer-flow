{{- define "deer-flow.name" -}}
deer-flow
{{- end -}}

{{- define "deer-flow.labels" -}}
app.kubernetes.io/name: {{ include "deer-flow.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "deer-flow.imagePullSecrets" -}}
{{- if .Values.imagePullSecrets }}
imagePullSecrets:
  {{- range .Values.imagePullSecrets }}
  - name: {{ if kindIs "map" . }}{{ .name }}{{ else }}{{ . }}{{ end }}
  {{- end }}
{{- end }}
{{- end -}}

{{- define "deer-flow.securityContext" -}}
runAsNonRoot: {{ .Values.security.runAsNonRoot | default true }}
runAsUser: {{ .Values.security.runAsUser | default 1000 }}
runAsGroup: {{ .Values.security.runAsGroup | default 1000 }}
fsGroup: {{ .Values.security.fsGroup | default 1000 }}
{{- end -}}
