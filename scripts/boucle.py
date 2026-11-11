#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boucle de retour : lit les réponses aux issues et ajuste le profil.

Ce que le script fait, et rien de plus :

    1. il cherche les issues « Top 3 du soir » et les commentaires qui contiennent
       une réponse : « 1 », « 2 », « 3 » ou « aucun » ;
    2. il retrouve le genre des programmes concernés dans la grille du jour ;
    3. il ajuste d'UN SEUL cran le poids du genre choisi (+0,2) ou, sur « aucun »,
       le poids du genre proposé en premier (-0,2) ;
    4. il réécrit data/profil.json et note ce qu'il a changé.

Pourquoi un seul cran : apprendre sur une décision par soir, c'est très peu de
signal. Des ajustements brutaux rendraient le classement instable — il bougerait
sans raison visible d'un jour à l'autre. +0,2 par soir, jamais plus.

Usage :
    python3 scripts/boucle.py
    python3 scripts/boucle.py --essai     (affiche sans rien écrire)
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

CRAN = 0.2          # l'amplitude d'un ajustement, en points de 0 à 10
BORNE_MIN, BORNE_MAX = 0.0, 10.0
DEPOT = "Quatree12/top3-du-soir"


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


def reponses_du_jour(jour: str) -> list[dict]:
    """Réponses trouvées dans les issues du soir."""
    issues = api(f"/repos/{DEPOT}/issues?state=all&per_page=50")
    if not issues:
        return []

    trouvailles = []
    for issue in issues:
        titre = issue.get("title", "")
        if "Top 3 du soir" not in titre or jour.replace("-", "-") not in titre:
            continue
        commentaires = api(f"/repos/{DEPOT}/issues/{issue['number']}/comments") or []
        for commentaire in commentaires:
            texte = (commentaire.get("body") or "").strip().lower()
            if texte in {"1", "2", "3", "aucun"}:
                trouvailles.append({"reponse": texte, "le": commentaire.get("created_at")})
    return trouvailles


def genres_du_jour(jour: str) -> list[dict]:
    """Les trois premiers programmes de la grille, avec leur genre."""
    fichier = RACINE / "top3" / f"{jour}.md"
    if not fichier.exists():
        return []
    lignes = [ligne for ligne in fichier.read_text(encoding="utf-8").splitlines()
              if ligne[:2] in {"1.", "2.", "3."}]
    grille = RACINE / "data" / f"grille-{jour}.json"
    if not grille.exists():
        return []
    contenu = json.loads(grille.read_text(encoding="utf-8"))
    return contenu.get("programmes", [])


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

    dossier = RACINE / "top3"
    if args.jour:
        jour = args.jour
    else:
        fichiers = sorted(dossier.glob("20??-??-??.md")) if dossier.exists() else []
        if not fichiers:
            print("Aucun top 3 enregistré : rien à apprendre.", file=sys.stderr)
            return 0
        jour = fichiers[-1].stem

    reponses = reponses_du_jour(jour)
    if not reponses:
        print(f"Aucune réponse pour le {jour}. Le profil ne bouge pas.")
        return 0

    derniere = reponses[-1]["reponse"]
    programmes = genres_du_jour(jour)
    if not programmes:
        print(f"Grille du {jour} introuvable : impossible de retrouver le genre.", file=sys.stderr)
        return 1

    profil = json.loads(PROFIL.read_text(encoding="utf-8"))

    if derniere == "aucun":
        genre = programmes[0].get("genre", "inconnu")
        sens = -1
    else:
        rang = int(derniere) - 1
        if rang >= len(programmes):
            print(f"Réponse « {derniere} » hors du top 3 : rien à ajuster.")
            return 0
        genre = programmes[rang].get("genre", "inconnu")
        sens = +1

    avant, apres = ajuster(profil, genre, sens)
    print(f"Réponse « {derniere} » — genre « {genre} » : {avant} -> {apres}")

    if args.essai:
        print("(essai : rien n'a été écrit)")
        return 0

    PROFIL.write_text(json.dumps(profil, ensure_ascii=False, indent=2), encoding="utf-8")

    historique = []
    if JOURNAL.exists():
        historique = json.loads(JOURNAL.read_text(encoding="utf-8"))
    historique.append({"jour": jour, "reponse": derniere, "genre": genre,
                       "avant": avant, "apres": apres})
    JOURNAL.write_text(json.dumps(historique, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Profil mis à jour. Historique dans {JOURNAL.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
