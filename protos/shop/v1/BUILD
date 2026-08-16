# grpc=True generates the service stubs, not just the messages. One target feeds
# both language backends — Python via pants.backend.codegen.protobuf.python and
# Go via pants.backend.experimental.codegen.protobuf.go.
protobuf_sources(
    name="protos",
    sources=["*.proto"],
    grpc=True,
)
