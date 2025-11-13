def render_nginx_upstream(name: str, backends: list) -> str:
    ups = [f"    server {b};" for b in backends]
    return (
        f"upstream {name}{{\n"
        + "\n".join(ups)
        + "\n}\nserver{\n    listen 7443;\n    location / {\n        proxy_pass http://"
        + name
        + ";\n    }\n}\n"
    )
