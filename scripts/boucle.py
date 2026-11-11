#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boucle de retour : lit la réponse aux issues et ajuste le profil.

Ce que le script fait, et rien de plus :

    1. il retrouve la date à traiter (la plus récente grille enregistrée) ;
    2. il lit les commentaires de l'issue « Top 3 du soir — AAAA-MM-JJ »
       et garde ceux qui contiennent uniquement « 1 », « 2 », « 3 » ou « aucun » ;
    3. il retrouve le genre du programme choisi ;
    4. il ajuste d'UN SEUL cran le poids de ce genre (+0,2, ou -0,2 sur « aucun ») ;
    5. il réécrit data/profil.json et note le changement dans data/apprentissage.json.

Pourquoi un seul cran : apprendre sur une décision par soir, c'est très peu de
signal. Des ajustements brutaux rendraient le classement instable.

Le script ne doit JAMAIS faire échouer le workflow : s'il ne trouve rien, il le
dit et rend la main avec le code 0.

Usage :
    python3 scripts/boucle.py
    python3 scripts/boucle.py --jour 2026-11-11
    python3 scripts/boucle.py --essai
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PROFIL = RACINE / "data" / "profil.json"
JOURNAL = RACINE / "data" / "apprentissage.json"

CRAN = 0.2                       # amplitude d'un ajustement, en points de 0 à 10
BORNE_MIN, BORNE_MAX = 0.0, 10.0
REPONSES_VALIDES = {"1", "2", "3", "aucun"}


def api(chemin: str) -> list | dict | None:
    """Appel à l'API GitHub avec le jeton fourni par les secrets."""
    jeton = os.environ.get("PROFIL_TOKEN")
    if not jeton:
        print("PROFIL_TOKEN absent : la boucle ne peut pas lire les issues.", file=sys.stderr)
        return None
    requete = urllib.request.Request(
        f"https://api.github.com{chemin}",
        headers={
            "Authorization": f"Bearer {jeton}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "top3-du-soir",
        },
    )
    try:
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            return json.loads(reponse.read())
    except Exception as e:
        print(f"Appel API impossible ({chemin}) : {e}", file=sys.stderr)
        return None


def dernier_jour_traite() -> str | None:
    """La date la plus récente pour laquelle on a un top 3."""
    dossier = RACINE / "top3"
    if not dossier.exists():
        return None
    fichiers = sorted(dossier.glob("20??-??-??.md"))
    return fichiers[-1].stem if fichiers else None


def reponses_pour(jour: str) -> list[str]:
    """Réponses valides trouvées dans l'issue du jour, dans l'ordre."""
    depot = os.environ.get("GITHUB_REPOSITORY")      # « proprietaire/depot »
    if not depot:
        print("GITHUB_REPOSITORY absent : impossible de savoir quel dépôt interroger.",
              file=sys.stderr)
        return []

    issues = api(f"/repos/{depot}/issues?state=all&per_page=100")
    if not issues:
        return []

    titre_vise = f"Top 3 du soir — {jour}"
    trouvailles = []
    for issue in issues:
        if issue.get("title") != titre_vise:
            continue
        commentaires = api(f"/repos/{depot}/issues/{issue['number']}/comments") or []
        for commentaire in commentaires:
            texte = (commentaire.get("body") or "").strip().lower()
            if texte in REPONSES_VALIDES:
                trouvailles.append(texte)
    return trouvailles


def genre_du_rang(jour: str, rang: int) -> str | None:
    """Genre du programme classé à ce rang, lu dans la grille du jour.

    La grille est le fichier écrit par scripts/soir.py. Si elle a disparu — le
    workflow peut tourner le lendemain — on se rabat sur les journaux conservés
    dans top3/, qui gardent la trace du classement.
    """
    grille = RACINE / "data" / f"grille-{jour}.json"
    if grille.exists():
        try:
            contenu = json.loads(grille.read_text(encoding="utf-8"))
            programmes = contenu.get("programmes", [])
            if rang < len(programmes):
                return programmes[rang].get("genre")
        except Exception as e:
            print(f"Grille illisible ({grille.name}) : {e}", file=sys.stderr)

    # Repli : retrouver le genre dans le fichier de notes s'il existe.
    autres = sorted((RACINE / "data").glob(f"grille-*.json"))
    if autres:
        try:
            contenu = json.loads(autres[-1].read_text(encoding="utf-8"))
            programmes = contenu.get("programmes", [])
            if rang < len(programmes):
                print(f"Grille du {jour} absente : repli sur {autres[-1].name}.",
                      file=sys.stderr)
                return programmes[rang].get("genre")
        except Exception:
            pass

    print(f"Grille du {jour} introuvable : impossible de retrouver le genre.", file=sys.stderr)
    return None


def ajuster(profil: dict, genre: str, sens: int) -> tuple[float, float]:
    """Un seul genre bouge, d'un seul cran."""
    poids = profil.get("genres_aimes", {})
    avant = float(poids.get(genre, 5.0))
    apres = max(BORNE_MIN, min(BORNE_MAX, avant + sens * CRAN))
    poids[genre] = round(apres, 2)
    profil["genres_aimes"] = poids
    return avant, apres


def main() -> int:
    ap = argparse.ArgumentParser(description="Boucle de retour : ajuste le profil.")
    ap.add_argument("--jour", default=None, help="date AAAA-MM-JJ (défaut : la plus récente)")
    ap.add_argument("--essai", action="store_true", help="affiche sans écrire")
    args = ap.parse_args()

    jour = args.jour or dernier_jour_traite()
    if not jour:
        print("Aucun top 3 enregistré : rien à apprendre. Le profil ne bouge pas.")
        return 0

    reponses = reponses_pour(jour)
    if not reponses:
        print(f"Aucune réponse pour le {jour}. Le profil ne bouge pas.")
        return 0

    derniere = reponses[-1]
    rang = 0 if derniere == "aucun" else int(derniere) - 1
    sens = -1 if derniere == "aucun" else +1

    genre = genre_du_rang(jour, rang)
    if not genre:
        print("Genre introuvable : le profil ne bouge pas.")
        return 0

    profil = json.loads(PROFIL.read_text(encoding="utf-8"))
    avant, apres = ajuster(profil, genre, sens)
    print(f"Réponse « {derniere} » — genre « {genre} » : {avant} -> {apres}")

    if args.essai:
        print("(essai : rien n'a été écrit)")
        return 0

    PROFIL.write_text(json.dumps(profil, ensure_ascii=False, indent=2), encoding="utf-8")

    historique = []
    if JOURNAL.exists():
        try:
            historique = json.loads(JOURNAL.read_text(encoding="utf-8"))
        except Exception:
            historique = []
    historique.append({"jour": jour, "reponse": derniere, "genre": genre,
                       "avant": avant, "apres": apres})
    JOURNAL.write_text(json.dumps(historique, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Profil mis à jour. Historique dans {JOURNAL.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
