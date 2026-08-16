{{/*
The label set Helm's chart best-practices guide calls recommended. `helm.sh/chart`
and `app.kubernetes.io/instance` were both missing: the first is how you tell
which chart version produced a live object, which is the first thing you want in
an incident; the second is what keeps two releases of this chart in one namespace
from colliding on every resource.

Deliberately NOT applied to `selector.matchLabels`, which stay `name` only. A
Deployment's selector is immutable, so anything added there can never be changed
again without deleting and recreating the workload. Labels you might want to
change belong on the object, not in the selector.
*/}}
{{- define "op.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/part-of: order-platform
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{- end -}}

{{- define "op.image" -}}
{{- printf "%s/%s:%s" .root.Values.global.registry .img.repository .img.tag -}}
{{- end -}}

{{/*
Common env shared by both services. Keeping this in one place is the whole
reason we wrote a chart instead of two YAML files.
*/}}
{{- define "op.commonEnv" -}}
- name: KAFKA_BROKERS
  value: {{ .Values.kafka.brokers | quote }}
- name: KAFKA_TOPIC
  value: {{ .Values.kafka.topic | quote }}
- name: AWS_ENDPOINT_URL
  value: {{ .Values.aws.endpointUrl | quote }}
- name: AWS_DEFAULT_REGION
  value: {{ .Values.aws.region | quote }}
- name: AWS_ACCESS_KEY_ID
  value: "test"
- name: AWS_SECRET_ACCESS_KEY
  value: "test"
{{- end -}}