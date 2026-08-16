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

{{/*
`required` halts the render with a readable message instead of emitting an empty
string, which would otherwise produce the image reference `/shop/order-api:dev`
and a pull error that names neither the chart nor the missing value.
*/}}
{{- define "op.image" -}}
{{- $registry := required "global.registry is required: the container registry every image in this chart is pulled from, e.g. nexus:8082" .root.Values.global.registry -}}
{{- $tag := required "an image tag is required: CI writes these into deploy/env/<env>/values.yaml" .img.tag -}}
{{- printf "%s/%s:%s" $registry .img.repository $tag -}}
{{- end -}}

{{/*
The name of the Secret holding the registry credentials. Required for the same
reason as the registry itself: an empty `imagePullSecrets[].name` is accepted by
the API server and then fails at pull time with an authentication error that
points at the registry rather than at the chart.
*/}}
{{- define "op.imagePullSecret" -}}
{{- required "global.imagePullSecret is required: the name of the Secret holding registry credentials in this namespace" .Values.global.imagePullSecret -}}
{{- end -}}

{{/*
Configuration every service that talks to Kafka or to an AWS-compatible endpoint
consumes. Rendered as ConfigMap `data`, not as inline `env`, so that the pod
template does not change when unrelated values do — see the checksum/config note
on each Deployment.
*/}}
{{- define "op.commonConfig" -}}
KAFKA_BROKERS: {{ .Values.kafka.brokers | quote }}
KAFKA_TOPIC: {{ .Values.kafka.topic | quote }}
AWS_ENDPOINT_URL: {{ .Values.aws.endpointUrl | quote }}
AWS_DEFAULT_REGION: {{ .Values.aws.region | quote }}
{{- end -}}

{{/*
Static AWS credentials, emitted only when values supply them. They are the Floci
sentinels a local cluster needs and nothing else: on a real cluster both values
stay empty, no credential env vars are rendered, and the AWS SDK falls through to
IRSA / EKS Pod Identity via the pod's projected service account token.

Credentials live here rather than in the ConfigMap because a ConfigMap is
world-readable to anything with get access in the namespace. Anything that is
genuinely secret belongs in a Secret, the way ORDER_SIGNING_KEY does.
*/}}
{{- define "op.awsCredentialEnv" -}}
{{- with .Values.aws.accessKeyId }}
- name: AWS_ACCESS_KEY_ID
  value: {{ . | quote }}
{{- end }}
{{- with .Values.aws.secretAccessKey }}
- name: AWS_SECRET_ACCESS_KEY
  value: {{ . | quote }}
{{- end }}
{{- end -}}

{{/*
A PodDisruptionBudget for one Deployment. Rendered only when the Deployment has
more than one replica: `minAvailable: 1` against a single replica allows zero
voluntary evictions, which blocks a node drain forever
(https://kubernetes.io/docs/tasks/run-application/configure-pdb/).

The selector must match the pods, not the Deployment, and is passed in because
pricing's pods are additionally distinguished by their `version` label.
*/}}
{{- define "op.pdb" -}}
{{- if and .root.Values.podDisruptionBudget.enabled (gt (int .replicas) 1) }}
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ .pdbName | default .name }}
  labels: {{- include "op.labels" (dict "name" .name "root" .root) | nindent 4 }}
spec:
  minAvailable: {{ .root.Values.podDisruptionBudget.minAvailable }}
  selector:
    matchLabels: {{- toYaml .selector | nindent 6 }}
{{- end }}
{{- end -}}
