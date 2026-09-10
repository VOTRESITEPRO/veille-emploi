#!/usr/bin/env python3
"""
Synchronisation directe avec Google Drive, hors contexte de l'agent.

Utilise un compte de service Google (cle JSON), pas le connecteur MCP :
les fichiers ne transitent jamais par les tokens du modele.

Config requise (variables d'environnement) :
    GOOGLE_SERVICE_ACCOUNT_FILE   chemin vers la cle JSON du compte de service
    DRIVE_STATE_FILE_ID           ID du fichier vues.json sur Drive
    DRIVE_OUT_FOLDER_ID           ID du dossier out/ sur Drive

Le dossier Drive cible (Mon Drive/CLAUDE/OFFRES EMPLOI) doit etre partage
avec l'adresse email du compte de service (role Editeur), sinon les
appels echouent en 404. Voir README, section "Compte de service Drive".

Usage :
    python drive_sync.py pull-state
    python drive_sync.py push-state
    python drive_sync.py push-synthese AAAA-MM-JJ
"""
import argparse
import io
import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

BASE = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/drive"]

DRIVE_STATE_FILE_ID = os.environ.get("DRIVE_STATE_FILE_ID")
DRIVE_OUT_FOLDER_ID = os.environ.get("DRIVE_OUT_FOLDER_ID")


def service():
    keyfile = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not keyfile:
        sys.exit("GOOGLE_SERVICE_ACCOUNT_FILE absent de l'environnement.")
    creds = service_account.Credentials.from_service_account_file(keyfile, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def pull_state():
    dest = BASE / "state" / "vues.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not DRIVE_STATE_FILE_ID:
        dest.write_text("{}", encoding="utf-8")
        print("DRIVE_STATE_FILE_ID absent : etat local reinitialise a vide.")
        return
    req = service().files().get_media(fileId=DRIVE_STATE_FILE_ID)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    dest.write_bytes(buf.getvalue())
    print(f"state/vues.json recupere depuis Drive ({len(buf.getvalue())} octets)")


def push_state():
    if not DRIVE_STATE_FILE_ID:
        sys.exit("DRIVE_STATE_FILE_ID absent : voir README.")
    src = BASE / "state" / "vues.json"
    media = MediaFileUpload(str(src), mimetype="application/json", resumable=False)
    service().files().update(fileId=DRIVE_STATE_FILE_ID, media_body=media).execute()
    print("state/vues.json ecrase sur Drive.")


def push_synthese(jour):
    if not DRIVE_OUT_FOLDER_ID:
        sys.exit("DRIVE_OUT_FOLDER_ID absent : voir README.")
    src = BASE / "out" / f"synthese_{jour}.md"
    if not src.exists():
        sys.exit(f"{src} introuvable.")
    media = MediaFileUpload(str(src), mimetype="text/markdown", resumable=False)
    meta = {"name": f"synthese_{jour}.md", "parents": [DRIVE_OUT_FOLDER_ID]}
    service().files().create(body=meta, media_body=media).execute()
    print(f"synthese_{jour}.md envoyee sur Drive.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["pull-state", "push-state", "push-synthese"])
    ap.add_argument("jour", nargs="?", help="AAAA-MM-JJ, requis pour push-synthese")
    args = ap.parse_args()
    if args.action == "pull-state":
        pull_state()
    elif args.action == "push-state":
        push_state()
    else:
        if not args.jour:
            sys.exit("push-synthese necessite le jour (AAAA-MM-JJ)")
        push_synthese(args.jour)
