"""Gera e valida a assinatura Ed25519 do manifesto de atualizacao."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
# Manifesto da série 2.x (o que o release assina e publica).
DEFAULT_MANIFEST_PATH = ROOT_DIR / "docs" / "updates" / "v2" / "manifest.json"
DEFAULT_SIGNATURE_PATH = ROOT_DIR / "docs" / "updates" / "v2" / "manifest.sig"
# Manifesto legado da série 1.x, congelado em 1.7.0: nunca é reassinado (qualquer
# byte alterado faria a 1.x rejeitá-lo); só é verificado antes de cada publicação.
LEGACY_MANIFEST_PATH = ROOT_DIR / "docs" / "updates" / "manifest.json"
LEGACY_SIGNATURE_PATH = ROOT_DIR / "docs" / "updates" / "manifest.sig"
LEGACY_LATEST_VERSION = "1.7.0"
DEFAULT_PRIVATE_KEY_PATH = ROOT_DIR / "secrets" / "update_signing_private_key.pem"
DEFAULT_PUBLIC_KEY_PATH = ROOT_DIR / "backend" / "data" / "update_manifest_public_key.pem"


def generate_key_pair(private_key_path: Path, public_key_path: Path) -> None:
    if private_key_path.exists() or public_key_path.exists():
        raise FileExistsError(
            "A geracao foi cancelada porque uma das chaves ja existe. "
            "As chaves de atualizacao nunca devem ser sobrescritas automaticamente."
        )

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)

    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def load_private_key(path: Path) -> Ed25519PrivateKey:
    if not path.is_file():
        raise FileNotFoundError(f"Chave privada nao encontrada: {path}")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("A chave privada informada nao e Ed25519.")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    if not path.is_file():
        raise FileNotFoundError(f"Chave publica nao encontrada: {path}")
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("A chave publica informada nao e Ed25519.")
    return key


def sign_manifest(
    manifest_path: Path,
    signature_path: Path,
    private_key_path: Path,
) -> bytes:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifesto nao encontrado: {manifest_path}")

    signature = load_private_key(private_key_path).sign(manifest_path.read_bytes())
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(
        base64.b64encode(signature).decode("ascii") + "\n",
        encoding="ascii",
    )
    return signature


def verify_manifest(
    manifest_path: Path,
    signature_path: Path,
    public_key_path: Path,
) -> None:
    if not signature_path.is_file():
        raise FileNotFoundError(f"Assinatura nao encontrada: {signature_path}")

    signature = base64.b64decode(
        signature_path.read_text(encoding="ascii").strip(),
        validate=True,
    )
    load_public_key(public_key_path).verify(signature, manifest_path.read_bytes())


def verify_legacy_manifest(public_key_path: Path) -> None:
    """Confere que o manifesto legado continua congelado em 1.7.0 e com assinatura válida."""
    import json

    data = json.loads(LEGACY_MANIFEST_PATH.read_bytes())
    if data.get("latest_version") != LEGACY_LATEST_VERSION:
        raise ValueError(
            f"Manifesto legado alterado: latest_version={data.get('latest_version')!r}, "
            f"esperado {LEGACY_LATEST_VERSION!r}. Ele deve ficar congelado para a série 1.x."
        )
    verify_manifest(LEGACY_MANIFEST_PATH, LEGACY_SIGNATURE_PATH, public_key_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assina o manifesto de atualizacao do Sentinela com Ed25519."
    )
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Gera o par de chaves antes de assinar. Use somente na configuracao inicial.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--signature", type=Path, default=DEFAULT_SIGNATURE_PATH)
    parser.add_argument("--private-key", type=Path, default=DEFAULT_PRIVATE_KEY_PATH)
    parser.add_argument("--public-key", type=Path, default=DEFAULT_PUBLIC_KEY_PATH)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Só verifica as assinaturas (série 2.x e legado), sem assinar nada.",
    )
    args = parser.parse_args()

    if args.manifest.resolve() == LEGACY_MANIFEST_PATH.resolve():
        raise SystemExit(
            "Recusado: o manifesto legado (docs/updates/manifest.json) fica congelado em "
            f"{LEGACY_LATEST_VERSION} para a série 1.x e nunca é reassinado."
        )

    if args.verify_only:
        verify_manifest(args.manifest, args.signature, args.public_key)
        verify_legacy_manifest(args.public_key)
        print(f"Assinatura validada: {args.signature}")
        print(f"Manifesto legado intacto ({LEGACY_LATEST_VERSION}): {LEGACY_MANIFEST_PATH}")
        return

    if args.generate_key:
        generate_key_pair(args.private_key, args.public_key)
        print(f"Chave privada criada em: {args.private_key}")
        print(f"Chave publica criada em: {args.public_key}")

    sign_manifest(args.manifest, args.signature, args.private_key)
    verify_manifest(args.manifest, args.signature, args.public_key)
    verify_legacy_manifest(args.public_key)
    print(f"Manifesto assinado: {args.manifest}")
    print(f"Assinatura validada: {args.signature}")
    print(f"Manifesto legado intacto ({LEGACY_LATEST_VERSION}): {LEGACY_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
