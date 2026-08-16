# Deliberately NOT in templates/. Helm renders every file under templates/ as a
# manifest, so a BUILD file there fails the whole chart with
# `YAML parse error on order-platform/templates/BUILD`.
file(name="order-api-template", source="templates/order-api.yaml")
