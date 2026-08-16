package_json(
    scripts=[
        node_build_script(
            entry_point="build",
            output_directories=["dist"],
        ),
    ],
    dependencies=[
        ":npmrc",
        ":tsconfig",
        ":vite_config",
        ":index_html",
        "./src",
        "./src:style_css",
    ],
)

file(name="npmrc", source=".npmrc")
file(name="tsconfig", source="tsconfig.json")
file(name="vite_config", source="vite.config.ts")
file(name="index_html", source="index.html")

# Not part of the Vite build — it is COPYed into the image and read by the
# port-consistency check in `checks/`.
file(name="nginx_conf", source="nginx.conf")
