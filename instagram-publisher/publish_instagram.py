#!/usr/bin/env python3
"""Publish an image or carousel to Instagram via the Meta Graph API."""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

CAROUSEL_MIN_ITEMS = 2
CAROUSEL_MAX_ITEMS = 10
CONTAINER_POLL_ATTEMPTS = 24
CONTAINER_POLL_INTERVAL_SECONDS = 5


def load_env():
    """Search this script's directory and its parents for a .env file."""
    here = Path(__file__).resolve().parent
    for candidate_dir in [here, *here.parents]:
        env_file = candidate_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            return env_file
    return None


ENV_FILE = load_env()
IG_ID = os.getenv("INSTAGRAM_BUSINESS_ID")
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
API_VERSION = os.getenv("META_API_VERSION", "v19.0")
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"


def require_credentials():
    missing = [
        name
        for name, value in [
            ("INSTAGRAM_BUSINESS_ID", IG_ID),
            ("INSTAGRAM_ACCESS_TOKEN", ACCESS_TOKEN),
        ]
        if not value
    ]
    if missing:
        where = f" (procurei um .env a partir de {Path(__file__).resolve().parent})"
        print(f"ERRO: faltando no .env{where}: {', '.join(missing)}")
        print("Copie .env.example para .env e preencha os valores reais.")
        sys.exit(1)


def _run_git(repo_dir: Path, args: list) -> None:
    result = subprocess.run(
        ["git", *args], cwd=repo_dir, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} falhou em {repo_dir}:\n{result.stderr.strip()}"
        )


def host_image_via_github(image_path: str) -> str:
    """Copy the image into a git repo the user controls, push it, and return
    its public raw.githubusercontent.com URL so Meta's servers can fetch it.

    Preferred over an anonymous public file host: the repo is owned by the
    user, is already used to store this account's real assets, and can be
    audited or cleaned up later.
    """
    repo_dir_value = os.getenv("IMAGE_HOST_REPO_DIR")
    github_repo = os.getenv("IMAGE_HOST_GITHUB_REPO")
    branch = os.getenv("IMAGE_HOST_BRANCH", "main")
    subdir = os.getenv("IMAGE_HOST_SUBDIR", "instagram-publisher/uploads")
    if not repo_dir_value or not github_repo:
        raise RuntimeError(
            "Para hospedar via GitHub, defina IMAGE_HOST_REPO_DIR (caminho local "
            "do clone) e IMAGE_HOST_GITHUB_REPO (ex.: Reherrmann/vera) no .env."
        )

    repo_dir = Path(repo_dir_value)
    dest_dir = repo_dir / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)

    src = Path(image_path)
    dest_name = f"{int(time.time() * 1000)}_{src.name}"
    dest_path = dest_dir / dest_name
    shutil.copyfile(src, dest_path)

    rel_path = f"{subdir}/{dest_name}"
    _run_git(repo_dir, ["add", "--", rel_path])
    _run_git(repo_dir, ["commit", "-m", f"instagram-publisher: add {dest_name}"])
    _run_git(repo_dir, ["push", "origin", branch])

    url = f"https://raw.githubusercontent.com/{github_repo}/{branch}/{rel_path}"
    print(f"  Hospedada (GitHub): {url}")
    return url


def host_image_via_catbox(image_path: str) -> str:
    """Upload the image to catbox.moe, an anonymous public file host.

    Anyone with the URL can view the file indefinitely and it is outside
    your control (no login, no reliable delete). Prefer --host github
    unless you have a specific reason to use this.
    """
    print("  Aviso: catbox.moe é um host público e anônimo — o arquivo fica")
    print("  acessível a qualquer pessoa com o link, fora do seu controle.")
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (Path(image_path).name, f, "image/png")},
            timeout=60,
        )
    url = resp.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Falha no upload para catbox.moe: {url}")
    print(f"  Hospedada (catbox.moe): {url}")
    return url


HOST_STRATEGIES = {
    "github": host_image_via_github,
    "catbox": host_image_via_catbox,
}


def create_media_container(image_url: str, is_carousel_item: bool) -> str:
    data = {"access_token": ACCESS_TOKEN, "image_url": image_url}
    if is_carousel_item:
        data["is_carousel_item"] = "true"
    resp = requests.post(f"{BASE_URL}/{IG_ID}/media", data=data, timeout=60)
    result = resp.json()
    if "id" not in result:
        raise RuntimeError(f"Erro ao criar container de mídia: {result}")
    print(f"  Container: {result['id']}")
    return result["id"]


def create_carousel_container(media_ids: list, caption: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/{IG_ID}/media",
        data={
            "access_token": ACCESS_TOKEN,
            "media_type": "CAROUSEL",
            "children": ",".join(media_ids),
            "caption": caption,
        },
        timeout=30,
    )
    result = resp.json()
    if "id" not in result:
        raise RuntimeError(f"Erro ao criar carrossel: {result}")
    print(f"  Carrossel: {result['id']}")
    return result["id"]


def wait_until_ready(container_id: str) -> bool:
    for attempt in range(CONTAINER_POLL_ATTEMPTS):
        resp = requests.get(
            f"{BASE_URL}/{container_id}",
            params={"fields": "status_code", "access_token": ACCESS_TOKEN},
            timeout=15,
        )
        status = resp.json().get("status_code", "")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            raise RuntimeError(f"Container com erro: {resp.json()}")
        print(f"  Processando... {attempt * CONTAINER_POLL_INTERVAL_SECONDS}s")
        time.sleep(CONTAINER_POLL_INTERVAL_SECONDS)
    return False


def publish_container(container_id: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/{IG_ID}/media_publish",
        data={"access_token": ACCESS_TOKEN, "creation_id": container_id},
        timeout=30,
    )
    result = resp.json()
    if "id" not in result:
        raise RuntimeError(f"Erro ao publicar: {result}")
    return result["id"]


def verify_connection() -> None:
    require_credentials()
    resp = requests.get(
        f"{BASE_URL}/{IG_ID}",
        params={"fields": "id,username,name", "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    result = resp.json()
    if "error" in result:
        print(f"ERRO ao validar conexão: {result['error']}")
        sys.exit(1)
    print("Conexão OK:")
    print(f"  Conta: @{result.get('username', '?')}")
    print(f"  Nome:  {result.get('name', '?')}")
    print(f"  ID:    {result.get('id', '?')}")


def run(images: list, caption: str, host: str, dry_run: bool) -> None:
    for image_path in images:
        if not Path(image_path).is_file():
            print(f"ERRO: imagem não encontrada: {image_path}")
            sys.exit(1)
    if not images:
        print("ERRO: informe ao menos uma imagem em --images.")
        sys.exit(1)
    if len(images) > CAROUSEL_MAX_ITEMS:
        print(f"ERRO: máximo de {CAROUSEL_MAX_ITEMS} imagens por carrossel.")
        sys.exit(1)
    if not caption.strip():
        print("ERRO: --caption não pode ser vazio.")
        sys.exit(1)

    is_carousel = len(images) >= CAROUSEL_MIN_ITEMS
    kind = "carrossel" if is_carousel else "post de imagem única"
    print(f"\n{len(images)} imagem(ns) — publicando como {kind}.")

    if dry_run:
        print("[DRY RUN] Nada foi enviado. Remova --dry-run para publicar de fato.")
        return

    require_credentials()
    host_fn = HOST_STRATEGIES[host]

    print("\nPasso 1 — Hospedando imagens e criando containers...")
    container_ids = [
        create_media_container(host_fn(img), is_carousel_item=is_carousel)
        for img in images
    ]

    if is_carousel:
        print("\nPasso 2 — Montando carrossel...")
        final_container_id = create_carousel_container(container_ids, caption)
    else:
        final_container_id = container_ids[0]
        # Single-image posts take the caption directly on their own container.
        requests.post(
            f"{BASE_URL}/{final_container_id}",
            data={"access_token": ACCESS_TOKEN, "caption": caption},
            timeout=30,
        )

    print("\nPasso 3 — Aguardando processamento...")
    if not wait_until_ready(final_container_id):
        print("ERRO: timeout esperando o container ficar pronto.")
        sys.exit(1)

    print("\nPasso 4 — Publicando...")
    post_id = publish_container(final_container_id)
    print(f"\nPublicado com sucesso! Post ID: {post_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images", nargs="+", required=False, help="Caminhos das imagens (1 a 10)."
    )
    parser.add_argument("--caption", required=False, default="", help="Legenda do post.")
    parser.add_argument(
        "--host",
        choices=sorted(HOST_STRATEGIES),
        default=os.getenv("IMAGE_HOST_STRATEGY", "github"),
        help="Onde hospedar as imagens publicamente antes de enviar à Graph API.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Valida tudo sem publicar de fato."
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Só testa a conexão com a Graph API (ignora --images/--caption).",
    )
    args = parser.parse_args()

    if args.verify:
        verify_connection()
        return

    if not args.images:
        parser.error("--images é obrigatório (a menos que use --verify).")

    run(args.images, args.caption, args.host, args.dry_run)


if __name__ == "__main__":
    main()
