#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chaîne complète du soir : télécharge la grille, classe, écrit le top 3.

C'est le script que fait tourner le workflow GitHub Actions. Il enchaîne :

    1. téléchargement du fichier XMLTV FR (TNT, ou complet si chaînes suisses) ;
    2. extraction de la soirée pour les chaînes du profil ;
    3. classement par top3.py ;
    4. écriture de top3/AAAA-MM-JJ.md et top3/dernier.md ;
    5. impression du top 3, que le workflow reprend pour ouvrir une issue.

Usage :
    python3 scripts/soir.py --profil data/profil.json
    python3 scripts/soir.py --profil data/profil.json --jour 2026-11-11
"""

from __future__ import annotations

import argparse
import gzip
import json
import lzma
import subprocess
import sys
import urllib.request
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Le guide TNT suffit pour les chaînes françaises et pèse ~1,2 Mo compressé.
# Le guide complet (~782 chaînes, 8 Mo compressé) ajoute les chaînes suisses.
URL_TNT = "https://xmltvfr.fr/xmltv/xmltv_tnt.xml.gz"
URL_COMPLET = "https://xmltvfr.fr/xmltv/xmltv.xml.gz"

AGENT = "top3-du-soir/0.2 (usage personnel)"

# Identifiants XMLTV des chaînes françaises concernées.
CHAINES_TNT = [
    "TF1.fr", "M6.fr", "W9.fr", "TMC.fr", "NT1.fr", "6ter.fr",
    "TF1SeriesFilms.fr", "France2.fr", "France3.fr", "France5.fr", "Arte.fr",
]

# Chaînes qu'on n'a que dans le guide complet.
CHAINES_SUISSE = ["RTSUn.ch", "RTSDeux.ch"]


def telecharger(url: str, essais: int = 2) -> bytes | None:
    derniere = None
    for _ in range(essais):
        try:
            requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(requete, timeout=60) as reponse:
                if reponse.status != 200:
                    return None
                return reponse.read()
        except Exception as e:
            derniere = e
    print(f"Téléchargement impossible ({url}) : {derniere}", file=sys.stderr)
    return None


def decompresser(donnees: bytes, url: str) -> bytes | None:
    """Le fichier annoncé .gz peut arriver gzippé, zippé ou brut."""
    if donnees[:2] == b"\x1f\x8b":                     # gzip
        return gzip.decompress(donnees)
    if donnees[:2] == b"PK":                           # zip
        with zipfile.ZipFile(BytesIO(donnees)) as z:
            nom = z.namelist()[0]
            return z.read(nom)
    if donnees[:6] == b"\xfd7zXZ\x00":                 # xz
        return lzma.decompress(donnees)
    if donnees.lstrip()[:5] == b"<?xml":               # déjà du XML
        return donnees
    print(f"Format de compression non reconnu pour {url}", file=sys.stderr)
    return None


def recuperer_grille(jour: str, profil: dict) -> Path | None:
    """Télécharge, décompresse et convertit la grille du soir."""
    veut_suisse = any(c.startswith("RTS") for c in profil.get("chaines_captees", []))
    urls = [URL_COMPLET] if veut_suisse else [URL_TNT]
    identifiants = CHAINES_TNT + (CHAINES_SUISSE if veut_suisse else [])

    for url in urls:
        brut = telecharger(url)
        if not brut:
            continue
        xml = decompresser(brut, url)
        if not xml:
            continue
        temporaire = RACINE / "data" / "xmltv.xml"
        temporaire.parent.mkdir(parents=True, exist_ok=True)
        temporaire.write_bytes(xml)
        print(f"Grille téléchargée : {len(xml) // 1024} Ko décompressés", file=sys.stderr)

        sortie = RACINE / "data" / f"grille-{jour}.json"
        commande = [
            sys.executable, str(RACINE / "sources" / "xmltv.py"),
            "--fichier", str(temporaire),
            "--jour", jour,
            "--chaines", ",".join(identifiants),
            "--soir-seulement",
            "--sortie", str(sortie),
        ]
        resultat = subprocess.run(commande, capture_output=True, text=True)
        if resultat.returncode != 0:
            print(resultat.stderr.strip(), file=sys.stderr)
            continue
        print(resultat.stdout.strip(), file=sys.stderr)
        temporaire.unlink(missing_ok=True)
        return sortie
    return None


def classer(grille: Path, profil: Path, jour: str) -> str | None:
    libelle = datetime.strptime(jour, "%Y-%m-%d").strftime("%d/%m/%Y")
    commande = [sys.executable, str(RACINE / "top3.py"), str(grille),
                "--profil", str(profil), "--date", libelle]
    resultat = subprocess.run(commande, capture_output=True, text=True)
    if resultat.returncode != 0:
        print(resultat.stderr.strip(), file=sys.stderr)
        return None
    return resultat.stdout.strip()


def ecrire_fichiers(message: str, jour: str) -> Path:
    dossier = RACINE / "top3"
    dossier.mkdir(parents=True, exist_ok=True)
    du_jour = dossier / f"{jour}.md"
    du_jour.write_text(message + "\n", encoding="utf-8")
    (dossier / "dernier.md").write_text(message + "\n", encoding="utf-8")
    return du_jour


def main() -> int:
    ap = argparse.ArgumentParser(description="Chaîne complète : grille, classement, fichiers.")
    ap.add_argument("--profil", default=str(RACINE / "data" / "profil-exemple.json"))
    ap.add_argument("--jour", default=None, help="date AAAA-MM-JJ (défaut : aujourd'hui)")
    args = ap.parse_args()

    jour = args.jour or date.today().isoformat()
    profil = json.loads(Path(args.profil).read_text(encoding="utf-8"))

    grille = recuperer_grille(jour, profil)
    if not grille:
        print("Aucune grille récupérée : le classement n'a pas pu être fait.", file=sys.stderr)
        return 1

    message = classer(grille, Path(args.profil), jour)
    if not message:
        print("Le classement a échoué.", file=sys.stderr)
        return 1

    fichier = ecrire_fichiers(message, jour)
    print(f"Écrit : {fichier}", file=sys.stderr)
    print("\n===== TOP 3 =====\n")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
