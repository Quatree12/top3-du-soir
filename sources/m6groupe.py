#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lecture des exports XML du groupe M6 (M6, W9, 6ter) et conversion pour top3.py.

Adresse de l'export, une chaîne et une semaine :

    https://pro.m6.fr/<chaîne>/grille/<année>-<numéro de semaine>.xml

Le fichier est un flux RSS :

    <grille_programmes>
      <chaine>M6</chaine>
      <semaine>
        <num_semaine>46</num_semaine>
        <date_debut>2026-11-07</date_debut>
        <date_fin>2026-11-13</date_fin>
        <jours>
          <jour>
            <date>2026-11-11</date>
            <diffusions>
              <diffusion>
                <dateheure>2026-11-11 21:10</dateheure>
                <titreprogramme>La France a un incroyable talent</titreprogramme>
                <soustitredif>Saison 21 : Émission 6</soustitredif>
                <format>Jeu</format>
                <signaletique>
                  <inedit>true</inedit>
                </signaletique>
                <resume>...</resume>
              </diffusion>

Avantages sur l'export TF1 Pro :

- la date figure sur chaque diffusion, donc pas d'ambiguïté de jour ;
- `inedit` est un vrai booléen, pas un CDATA à interpréter ;
- le format est explicite (Jeu, Magazine, Long Métrage, Téléfilm, Documentaire…).

Ce qui manque toujours : **pas d'heure de fin**. La durée se déduit, comme pour
TF1 Pro, de l'écart avec la diffusion suivante de la même chaîne.

Note : depuis l'arrivée de la source XMLTV FR (`sources/xmltv.py`), ce lecteur
est utile surtout si l'on veut les données brutes du diffuseur. XMLTV FR couvre
les mêmes chaînes avec les heures de fin réelles.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# Le fichier donne le nom en majuscules (« 6TER ») et parfois rien du tout :
# on normalise vers le nom que le profil attend.
CHAINES_EXPORT = {"m6": "M6", "w9": "W9", "6ter": "6ter", "paris-premiere": "Paris Première"}
NOMS_NORMALISES = {"m6": "M6", "w9": "W9", "6ter": "6ter", "6t": "6ter", "6teren": "6ter"}

# format (groupe M6) -> genre utilisé par top3.py
GENRES = {
    "série": "serie",
    "serie": "serie",
    "long métrage": "film",
    "long metrage": "film",
    "téléfilm": "film",
    "telefilm": "film",
    "documentaire": "documentaire",
    "magazine": "magazine",
    "jeu": "jeu",
    "divertissement": "divertissement",
    "information": "info",
    "météo": "info",
    "meteo": "info",
    "émission": "divertissement",
    "emission": "divertissement",
    "téléachat": "magazine",
    "teleachat": "magazine",
    "vidéoclip": "divertissement",
    "videoclip": "divertissement",
    "animation": "divertissement",
}

TITRES_IGNORES = re.compile(
    r"^(météo|meteo|programmes de nuit|my boutique téléshop'?|téléachat|bande[- ]annonce)$",
    re.I,
)

DUREE_DEFAUT_MIN = 60


def texte(element: ET.Element, nom: str) -> str:
    """Contenu d'une balise, cherchée d'abord en enfant direct, puis n'importe où.

    L'arbre est <rss><grille_programmes><chaine>… : un `find` au premier niveau
    ne voit rien, d'où la recherche élargie.
    """
    trouve = element.find(nom)
    if trouve is None:
        trouve = element.find(f".//{nom}")
    return (trouve.text or "").strip() if trouve is not None else ""


def lire_jour(chemin: Path, jour: str) -> list[dict]:
    """Diffusions d'un jour donné, telles quelles."""
    racine = ET.fromstring(chemin.read_bytes())
    nom_brut = texte(racine, "chaine") or "?"
    clef = nom_brut.strip().lower().replace(" ", "")
    nom_chaine = NOMS_NORMALISES.get(clef, nom_brut.strip())

    diffusions = []
    for bloc_jour in racine.iter("jour"):
        if texte(bloc_jour, "date") != jour:
            continue
        for d in bloc_jour.iter("diffusion"):
            dateheure = texte(d, "dateheure")
            titre = texte(d, "titreprogramme")
            if not dateheure or not titre:
                continue
            diffusions.append({
                "chaine": nom_chaine,
                "heure": dateheure.split(" ")[-1][:5],
                "titre": titre,
                "sous_titre": texte(d, "soustitredif") or texte(d, "titreepisode"),
                "format": texte(d, "format"),
                "inedit": texte(d, "signaletique/inedit").lower() == "true",
                "resume": texte(d, "resume"),
            })
    return diffusions


def minutes(heure: str) -> int:
    h, m = (int(x) for x in heure.split(":"))
    return h * 60 + m


def deviner_genre(format_source: str, titre: str) -> str:
    genre = GENRES.get(format_source.strip().lower())
    if genre:
        return genre
    if "météo" in titre.lower():
        return "info"
    return "divertissement"


def convertir(diffusions: list[dict], soir_seulement: bool) -> list[dict]:
    for courant, suivant in zip(diffusions, diffusions[1:]):
        ecart = minutes(suivant["heure"]) - minutes(courant["heure"])
        courant["duree_min"] = ecart if ecart > 0 else DUREE_DEFAUT_MIN
    if diffusions:
        diffusions[-1]["duree_min"] = DUREE_DEFAUT_MIN

    programmes = []
    for d in diffusions:
        if TITRES_IGNORES.match(d["titre"]):
            continue
        if soir_seulement and minutes(d["heure"]) < minutes("19:00"):
            continue
        titre = d["titre"]
        if d["sous_titre"]:
            titre = f"{titre} — {d['sous_titre']}"
        programmes.append({
            "chaine": d["chaine"],
            "titre": titre,
            "debut": d["heure"],
            "duree_min": d["duree_min"],
            "genre": deviner_genre(d["format"], d["titre"]),
            "inedit": d["inedit"],
            "replay": False,
            "description": d["resume"][:400],
            "_format_source": d["format"],
        })
    return programmes


def main() -> int:
    ap = argparse.ArgumentParser(description="Convertit un export XML du groupe M6 pour top3.py.")
    ap.add_argument("--fichier", required=True, help="export XML (M6, W9, 6ter…)")
    ap.add_argument("--jour", required=True, help="date AAAA-MM-JJ à convertir")
    ap.add_argument("--sortie", default=None, help="fichier JSON à écrire")
    ap.add_argument("--soir-seulement", action="store_true", help="ne garder qu'à partir de 19 h")
    ap.add_argument("--liste", action="store_true", help="lister les jours du fichier et sortir")
    args = ap.parse_args()

    chemin = Path(args.fichier)
    racine = ET.fromstring(chemin.read_bytes())
    nom_chaine = texte(racine, "chaine") or "?"

    if args.liste:
        for bloc in racine.iter("jour"):
            d = texte(bloc, "date")
            n = len(list(bloc.iter("diffusion")))
            print(f"{d} : {n} diffusion(s)")
        return 0

    diffusions = lire_jour(chemin, args.jour)
    if not diffusions:
        jours = [texte(b, "date") for b in racine.iter("jour")]
        print(f"Le {args.jour} n'est pas dans cet export.", file=sys.stderr)
        print("Jours disponibles : " + ", ".join(jours), file=sys.stderr)
        return 1

    programmes = convertir(diffusions, args.soir_seulement)
    if not programmes:
        print(f"Aucun programme exploitable pour le {args.jour}.", file=sys.stderr)
        return 1

    grille = {
        "date": args.jour,
        "source": f"export XML groupe M6 — {nom_chaine}",
        "recupere_le": datetime.now().isoformat(timespec="seconds"),
        "programmes": programmes,
    }

    if args.sortie:
        sortie = Path(args.sortie)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        sortie.write_text(json.dumps(grille, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Écrit : {sortie} ({len(programmes)} programmes)")
    else:
        print(json.dumps(grille, ensure_ascii=False, indent=2))

    print("\n--- Détail ---", file=sys.stderr)
    for p in programmes:
        fin = minutes(p["debut"]) + p["duree_min"]
        print(f" {p['debut']}-{fin // 60:02d}:{fin % 60:02d}  {p['genre']:<14} "
              f"{'inédit' if p['inedit'] else 'rediff':<7} {p['titre']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
