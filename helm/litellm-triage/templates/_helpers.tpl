{{/*
Expand the name of the chart.
*/}}
{{- define "litellm-triage.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "litellm-triage.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "litellm-triage.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "litellm-triage.labels" -}}
helm.sh/chart: {{ include "litellm-triage.chart" . }}
{{ include "litellm-triage.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "litellm-triage.selectorLabels" -}}
app.kubernetes.io/name: {{ include "litellm-triage.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
LiteLLM component labels
*/}}
{{- define "litellm-triage.litellm.labels" -}}
{{ include "litellm-triage.labels" . }}
app.kubernetes.io/component: litellm
{{- end }}

{{- define "litellm-triage.litellm.selectorLabels" -}}
{{ include "litellm-triage.selectorLabels" . }}
app.kubernetes.io/component: litellm
{{- end }}

{{/*
Presidio Analyzer component labels
*/}}
{{- define "litellm-triage.presidio-analyzer.labels" -}}
{{ include "litellm-triage.labels" . }}
app.kubernetes.io/component: presidio-analyzer
{{- end }}

{{- define "litellm-triage.presidio-analyzer.selectorLabels" -}}
{{ include "litellm-triage.selectorLabels" . }}
app.kubernetes.io/component: presidio-analyzer
{{- end }}

{{/*
Presidio Anonymizer component labels
*/}}
{{- define "litellm-triage.presidio-anonymizer.labels" -}}
{{ include "litellm-triage.labels" . }}
app.kubernetes.io/component: presidio-anonymizer
{{- end }}

{{- define "litellm-triage.presidio-anonymizer.selectorLabels" -}}
{{ include "litellm-triage.selectorLabels" . }}
app.kubernetes.io/component: presidio-anonymizer
{{- end }}

{{/*
Ollama component labels
*/}}
{{- define "litellm-triage.ollama.labels" -}}
{{ include "litellm-triage.labels" . }}
app.kubernetes.io/component: ollama
{{- end }}

{{- define "litellm-triage.ollama.selectorLabels" -}}
{{ include "litellm-triage.selectorLabels" . }}
app.kubernetes.io/component: ollama
{{- end }}

{{/*
API key secret name
*/}}
{{- define "litellm-triage.apiKeySecretName" -}}
{{- if .Values.cloudModel.apiKeySecret.name }}
{{- .Values.cloudModel.apiKeySecret.name }}
{{- else }}
{{- include "litellm-triage.fullname" . }}-api-keys
{{- end }}
{{- end }}
