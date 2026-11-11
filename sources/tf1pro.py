#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lecture de l'export XML officiel de TF1 Pro et conversion vers le format de `top3.py`.

Structure réelle du fichier (vérifiée sur un export du 7 au 13 novembre 2026) :

    <EXPORT_TF1_PRO>
      <DERNIERE_MAJ>10/11/2026</DERNIERE_MAJ>
      <GRILLE numeroSemaine="46" dateDebut="07/11/2026" dateFin="13/11/2026">
        <JOUR id="4" date="11/11/2026">
          <EMISSION heureDiffusion="21.10">
            <titre><![CDATA[Esprits criminels : Evolution]]></titre>
            <sousTitre><![CDATA[La mémoire de l'eau]]></sousTitre>
            <typeEmission><![CDATA[Série]]></typeEmission>
            <partieJour><![CDATA[1 PS]]></partieJour>
            <ineditTV valeur="1"><![CDATA[INEDIT]]></ineditTV>
            <replay valeur="0"/>
            <duree>...</duree>          (absent sur cet export)
          </EMISSION>

Trois choses que l'export ne donne PAS, et qu'il faut donc savoir :

1. **Pas d'heure de fin, pas de durée.** Elle se déduit de l'heure de diffusion du
   programme suivant sur la même chaîne. Le dernier de la journée est laissé à
   60 minutes par défaut, ce qui n'a aucune importance : il commence après minuit.
2. **Pas de note de presse.** Le critère « réputation » reste donc neutre.
3. **Pas de genre normalisé** : quatre valeurs seulement (Série, Téléfilm,
   Divertissement, Info, Programme court). La table ci-dessous les traduit vers
   les genres attendus par `top3.py`.

Le paramètre `--jour` accepte une date au format AAAA-MM-JJ ; si la date demandée
n'est pas dans l'export, le script le dit et liste ce que le fichier contient,
plutôt que de classer la mauvaise soirée en silence.

Usage :
    python3 sources/tf1pro.py --fichier export.xml --jour 2026-11-11 --sortie data/grille-2026-11-11.json
    python3 sources/tf1pro.py --fichier export.xml --jour 2026-11-11 --soir-seulement
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# Chaîne de l'export. Un export TF1 Pro est publié par chaîne ; le nom n'est pas
# dans le fichier, il vient de l'URL de téléchargement. À passer en --chaine.
CHAINES_EXPORT = {"1": "TF1"}

# typeEmission (4 valeurs dans l'export) -> genre utilisé par top3.py
GENRES = {
    "série": "serie",
    "serie": "serie",
    "téléfilm": "film",
    "telefilm": "film",
    "film": "film",
    "divertissement": "divertissement",
    "info": "info",
    "programme court": "divertissement",
    "documentaire": "documentaire",
    "magazine": "magazine",
    "jeu": "jeu",
}

# Programmes qui ne sont pas des candidats sérieux à une soirée TV.
TITRES_IGNORES = re.compile(
    r"^(météo|meteo|petits plats en équilibre|loto|programmes de nuit|bande[- ]annonce)$",
    re.I,
)

DUREE_DEFAUT_MIN = 60


# --------------------------------------------------------------------------
# 1. Lecture
# --------------------------------------------------------------------------

def _texte(emission: ET.Element, nom: str) -> str:
    """Contenu texte d'une balise enfant, CDATA ou non."""
    for enfant in emission:
        if enfant.tag.split("}")[-1] == nom:
            return (enfant.text or "").strip()
    return ""


def _valeur(emission: ET.Element, nom: str) -> str:
    """Attribut `valeur` d'une balise comme <ineditTV valeur="1"/>."""
    for enfant in emission:
        if enfant.tag.split("}")[-1] == nom:
            return (enfant.get("valeur") or "").strip()
    return ""


def lire_heure(valeur: str) -> str | None:
    """« 21.10 » (format de l'export) ou « 21:10 » -> « 21:10 »."""
    if not valeur:
        return None
    m = re.match(r"^\s*(\d{1,2})[.:h](\d{2})", valeur)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def minutes(heure: str) -> int:
    h, m = (int(x) for x in heure.split(":"))
    return h * 60 + m


def lire_export(chemin: Path) -> dict:
    racine = ET.fromstring(chemin.read_bytes())
    jours = {}
    for jour in racine.iter("JOUR"):
        date_brute = jour.get("date", "")
        try:
            clef = datetime.strptime(date_brute, "%d/%m/%Y").date().isoformat()
        except ValueError:
            continue
        emissions = []
        for em in jour.findall("EMISSION"):
            heure = lire_heure(em.get("heureDiffusion", ""))
            titre = _texte(em, "titre")
            if not heure or not titre:
                continue
            emissions.append({
                "heure": heure,
                "titre": titre,
                "sous_titre": _texte(em, "sousTitre"),
                "type": _texte(em, "typeEmission"),
                "partie_jour": _texte(em, "partieJour"),
                "inedit": _valeur(em, "ineditTV") == "1",
                "replay": _valeur(em, "replay") == "1",
                "resume": re.sub(r"<[^>]+>", " ", _texte(em, "resume")).strip(),
            })
        jours[clef] = emissions
    return jours


# --------------------------------------------------------------------------
# 2. Conversion
# --------------------------------------------------------------------------

def deviner_genre(type_emission: str, titre: str, sous_titre: str) -> str:
    """Le type déclaré d'abord ; le titre sert seulement de secours."""
    genre = GENRES.get(type_emission.strip().lower())
    if genre:
        return genre
    indice = f"{titre} {sous_titre}".lower()
    if "journal" in indice or "météo" in indice:
        return "info"
    return "divertissement"


def convertir(emissions: list[dict], chaine: str, soir_seulement: bool) -> list[dict]:
    """Ajoute les durées calculées, filtre, et met au format attendu par top3.py."""
    # Durée = écart avec le programme suivant, sur la même chaîne.
    for courant, suivant in zip(emissions, emissions[1:]):
        ecart = minutes(suivant["heure"]) - minutes(courant["heure"])
        courant["duree_min"] = ecart if ecart > 0 else DUREE_DEFAUT_MIN
    if emissions:
        emissions[-1]["duree_min"] = DUREE_DEFAUT_MIN

    programmes = []
    for em in emissions:
        if TITRES_IGNORES.match(em["titre"]):
            continue
        # La soirée commence à 20 h 30 ; on garde la fin de journée au passage.
        if soir_seulement and minutes(em["heure"]) < minutes("19:00"):
            continue
        titre_complet = em["titre"]
        if em["sous_titre"] and em["sous_titre"] != "-":
            titre_complet = f"{em['titre']} — {em['sous_titre']}"
        programmes.append({
            "chaine": chaine,
            "titre": titre_complet,
            "debut": em["heure"],
            "duree_min": em["duree_min"],
            "genre": deviner_genre(em["type"], em["titre"], em["sous_titre"]),
            "inedit": em["inedit"],
            "replay": em["replay"],
            "description": em["resume"][:400],
            "_type_source": em["type"],
        })
    return programmes


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Convertit un export XML TF1 Pro pour top3.py.")
    ap.add_argument("--fichier", required=True, help="export XML de TF1 Pro")
    ap.add_argument("--jour", required=True, help="date AAAA-MM-JJ à convertir")
    ap.add_argument("--chaine", default="TF1", help="nom de la chaîne de l'export")
    ap.add_argument("--sortie", default=None, help="fichier JSON à écrire")
    ap.add_argument("--soir-seulement", action="store_true", help="ne garder qu'à partir de 19 h")
    ap.add_argument("--liste", action="store_true", help="lister les jours du fichier et sortir")
    args = ap.parse_args()

    jours = lire_export(Path(args.fichier))

    if args.liste:
        for clef in sorted(jours):
            print(f"{clef} : {len(jours[clef])} émission(s)")
        return 0

    if args.jour not in jours:
        print(f"Le {args.jour} n'est pas dans cet export.", file=sys.stderr)
        print("Jours disponibles : " + ", ".join(sorted(jours)), file=sys.stderr)
        return 1

    programmes = convertir(jours[args.jour], args.chaine, args.soir_seulement)
    if not programmes:
        print(f"Aucun programme exploitable pour le {args.jour}.", file=sys.stderr)
        return 1

    grille = {
        "date": args.jour,
        "source": f"export XML TF1 Pro — {args.chaine}",
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
