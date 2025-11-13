import json
import os


def parse_requirements(path: str) -> list[dict[str, str]]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "==" in line:
                name, version = line.split("==", 1)
            else:
                name, version = line, ""
            out.append({"name": name.strip(), "version": version.strip(), "ecosystem": "pypi", "file": path})
    return out


def parse_cargo_toml(path: str) -> list[dict[str, str]]:
    out = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    in_deps = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("["):
            in_deps = s == "[dependencies]"
            continue
        if in_deps and s and not s.startswith("#") and "=" in s:
            name = s.split("=")[0].strip()
            out.append({"name": name, "version": "*", "ecosystem": "crates", "file": path})
    return out


def generate_repo_sbom(root: str) -> dict[str, list[dict[str, str]]]:
    pkgs: list[dict[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if fn == "requirements.txt":
                pkgs.extend(parse_requirements(p))
            elif fn == "Cargo.toml":
                pkgs.extend(parse_cargo_toml(p))
    return {"packages": pkgs}


def save_sbom(root: str, out_path: str):
    sbom = generate_repo_sbom(root)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sbom, f, indent=2)
