#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lecture d'un fichier XMLTV (XML TV Fr) et conversion pour top3.py.

Adresse des fichiers : https://xmltvfr.fr/xmltv.php
Variantes utiles : xmltv_tnt.xml.gz (TNT seule, ~1,2 Mo compressé),
xmltv_fr.xml.gz (chaînes accessibles depuis la France), xmltv.xml.gz (tout).

Format XMLTV, normalisé par le projet XMLTV :

    <tv>
      <channel id="TF1.fr"><display-name>TF1</display-name></channel>
      <programme start="20261111211000 +0100" stop="20261111215500 +0100" channel="TF1.fr">
        <title lang="fr">Esprits criminels : Evolution</title>
        <sub-title lang="fr">La mémoire de l'eau</sub-title>
        <desc lang="fr">…</desc>
        <category lang="fr">Série</category>
        <new />
        <rating><value>Déconseillé aux -12 ans</value></rating>
      </programme>
    </tv>

Deux avantages décisifs sur les exports des diffuseurs :

1. **L'heure de fin est fournie** (`stop`), donc plus de durée déduite par
   soustraction — c'est la source des artefacts qu'on traînait.
2. **Une seule URL couvre toutes les chaînes**, RTS 1 et RTS 2 comprises
   (`RTSUn.ch` et `RTSDeux.ch`) dans la variante complète.

Le fichier TNT ne contient pas les chaînes suisses : seul le guide complet les a.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# Identifiant XMLTV -> nom utilisé dans le profil.
CHAINES = {
    "TF1.fr": "TF1",
    "M6.fr": "M6",
    "W9.fr": "W9",
    "TMC.fr": "TMC",
    "NT1.fr": "TFX",
    "6ter.fr": "6ter",
    "TF1SeriesFilms.fr": "TF1 Séries Films",
    "CanalPlus.fr": "Canal+",
    "CanalPlus.ch": "Canal+ Suisse",
    "RTSUn.ch": "RTS Un",
    "RTSDeux.ch": "RTS Deux",
    "France2.fr": "France 2",
    "France3.fr": "France 3",
    "France5.fr": "France 5",
    "Arte.fr": "Arte",
}

# Catégories XMLTV -> genre utilisé par top3.py. La correspondance se fait par
# mots-clés : les libellés varient (« Série », « Série TV », « Téléfilm »…).
CATEGORIES = [
    (("série", "serie", "feuilleton", "fiction"), "serie"),
    (("téléfilm", "telefilm"), "film"),
    (("film",), "film"),
    (("documentaire", "docu"), "documentaire"),
    (("sport",), "sport"),
    (("jeu", "divertissement", "télé-réalité", "tele-realite", "téléréalité"), "divertissement"),
    (("magazine", "talk-show"), "magazine"),
    (("journal", "information", "météo", "meteo", "news"), "info"),
]

DUREE_DEFAUT_MIN = 60


def lire_grille(chemin: Path) -> tuple[dict, list]:
    racine = ET.fromstring(chemin.read_bytes())
    noms = {}
    for canal in racine.findall("channel"):
        ident = canal.get("id", "")
        noms[ident] = canal.findtext("display-name", default=ident).strip()
    return noms, racine.findall("programme")


def heure_locale(valeur: str) -> str:
    """« 20261111211000 +0100 » -> « 21:10 »."""
    if not valeur or len(valeur) < 12:
        return ""
    return f"{valeur[8:10]}:{valeur[10:12]}"


def jour_local(valeur: str) -> str:
    """« 20261111211000 +0100 » -> « 2026-11-11 »."""
    if not valeur or len(valeur) < 8:
        return ""
    return f"{valeur[0:4]}-{valeur[4:6]}-{valeur[6:8]}"


def minutes(valeur: str) -> int:
    """Minutes depuis minuit, lues sur l'horodatage complet (gère le passage de minuit)."""
    if not valeur or len(valeur) < 12:
        return 0
    return int(valeur[8:10]) * 60 + int(valeur[10:12])


def deviner_genre(categories: list[str]) -> str:
    texte = " ".join(c.lower() for c in categories)
    for mots, genre in CATEGORIES:
        if any(mot in texte for mot in mots):
            return genre
    return "inconnu"


def est_inedit(prog: ET.Element, categories: list[str]) -> bool:
    """`<new />` de XMLTV, ou la mention « inédit » dans la catégorie."""
    if prog.find("new") is not None:
        return True
    return bool(re.search(r"in[ée]dit", " ".join(categories), re.I))


def convertir(programmes: list, noms: dict, jour: str, chaines_voulues: set[str],
              debut_min: int | None, fin_min: int | None) -> list[dict]:
    sortie = []
    for prog in programmes:
        ident = prog.get("channel", "")
        if chaines_voulues and ident not in chaines_voulues:
            continue
        start = prog.get("start", "")
        if jour_local(start) != jour:
            continue

        debut = heure_locale(start)
        stop = prog.get("stop", "")
        if stop and jour_local(stop) != jour:
            # Le programme franchit minuit : on compte jusqu'à 30 h.
            duree = (minutes(stop) + 24 * 60 - minutes(start))
        else:
            duree = (minutes(stop) - minutes(start)) if stop else 0
        duree = duree or DUREE_DEFAUT_MIN

        titre = prog.findtext("title", default="").strip()
        if not titre:
            continue
        sous_titre = (prog.findtext("sub-title", default="") or "").strip()
        desc = (prog.findtext("desc", default="") or "").strip()
        categories = [(c.text or "").strip() for c in prog.findall("category")]

        # Fenêtre : minutes depuis 19 h (négatif = avant minuit, positif = après)
        m = minutes(start)
        decalage = m - 19 * 60 if m >= 19 * 60 else m + 24 * 60 - 19 * 60
        if debut_min is not None and decalage < debut_min:
            continue
        if fin_min is not None and decalage > fin_min:
            continue

        nom_chaine = CHAINES.get(ident, noms.get(ident, ident))
        titre_complet = f"{titre} — {sous_titre}" if sous_titre else titre
        sortie.append({
            "chaine": nom_chaine,
            "titre": titre_complet,
            "debut": debut,
            "duree_min": duree,
            "genre": deviner_genre(categories),
            "inedit": est_inedit(prog, categories),
            "replay": False,
            "description": desc[:400],
            "_categories": categories,
        })
    sortie.sort(key=lambda p: (p["debut"], p["chaine"]))
    return sortie


def main() -> int:
    ap = argparse.ArgumentParser(description="Convertit un fichier XMLTV pour top3.py.")
    ap.add_argument("--fichier", required=True, help="fichier XMLTV (.xml)")
    ap.add_argument("--jour", required=True, help="date AAAA-MM-JJ à convertir")
    ap.add_argument("--chaines", default=None,
                    help="identifiants XMLTV séparés par des virgules (défaut : toutes)")
    ap.add_argument("--soir-seulement", action="store_true",
                    help="ne garder que de 19 h à 1 h du matin")
    ap.add_argument("--sortie", default=None, help="fichier JSON à écrire")
    ap.add_argument("--liste", action="store_true", help="lister les chaînes et sortir")
    args = ap.parse_args()

    noms, programmes = lire_grille(Path(args.fichier))

    if args.liste:
        pour = set(args.chaines.split(",")) if args.chaines else set()
        for ident, nom in noms.items():
            marque = "*" if not pour or ident in pour else " "
            print(f"{marque} {ident:<24} {nom}")
        print(f"\n{len(noms)} chaînes, {len(programmes)} programmes dans le fichier")
        return 0

    voulues = set(args.chaines.split(",")) if args.chaines else set()
    sortie = convertir(programmes, noms, args.jour, voulues,
                       0 if args.soir_seulement else None,
                       6 * 60 if args.soir_seulement else None)

    if not sortie:
        print(f"Aucun programme pour le {args.jour} avec ces filtres.", file=sys.stderr)
        return 1

    grille = {
        "date": args.jour,
        "source": "XML TV Fr (format XMLTV)",
        "recupere_le": datetime.now().isoformat(timespec="seconds"),
        "programmes": sortie,
    }

    if args.sortie:
        p = Path(args.sortie)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(grille, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Écrit : {p} ({len(sortie)} programmes, "
              f"{len(set(x['chaine'] for x in sortie))} chaîne(s))")
    else:
        print(json.dumps(grille, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
