#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Récupération automatique des grilles TF1 Pro, puis conversion et classement.

TF1 Pro sert un export XML par chaîne et par semaine, à cette adresse :

    https://tf1pro.com/grilles-xml/<numéro de chaîne>/<samedi de la semaine>

Numéros relevés sur TF1 Pro (semaine 46, 7 au 13 novembre 2026) :

    17 -> TF1              https://tf1pro.com/grilles-xml/17/2026-11-07
    18 -> TFX              https://tf1pro.com/grilles-xml/18/2026-11-07
    22 -> TMC              https://tf1pro.com/grilles-xml/22/2026-11-07

L'accès est ouvert, sans compte. Les numéros de TF1 Séries Films et de LCI
restent à confirmer : c'est ce que `--sonder` sert à faire.

Ce script enchaîne les trois étapes :

    1. téléchargement de l'export de chaque chaîne ;
    2. conversion vers le format de top3.py (via sources/tf1pro.py) ;
    3. fusion des chaînes en une seule grille, puis classement.

Usage :
    # Quelles chaînes répondent ?
    python3 sources/recuperer.py --sonder

    # La soirée du 11 novembre, sur toutes les chaînes connues
    python3 sources/recuperer.py --jour 2026-11-11 --profil data/profil-exemple.json

    # Une seule chaîne, et on garde les fichiers intermédiaires
    python3 sources/recuperer.py --jour 2026-11-11 --chaines 22 --garder
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
URL_MODELE = "https://tf1pro.com/grilles-xml/{chaine}/{semaine}"
AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Numéro de chaîne dans l'écosystème TF1 Pro -> nom.
CHAINES = {
    "17": "TF1",
    "18": "TFX",
    "22": "TMC",
    "1": "TF1 Séries Films",
    "3": "LCI",
}
# Numéros relevés dans l'URL du lien « Télécharger (XML) » sur TF1 Pro.
CHAINES_CONFIRMEES = {"17", "18", "22"}
CHAINES_HYPOTHESE = {"1", "3"}


def samedi_de_la_semaine(jour: date) -> date:
    """Le samedi qui ouvre la semaine d'export contenant `jour`.

    Les exports TF1 Pro vont du samedi au vendredi (semaine 46 : 07/11 -> 13/11).
    """
    return jour - timedelta(days=(jour.weekday() - 5) % 7)


def telecharger(url: str, essais: int = 2) -> bytes | None:
    for _ in range(essais):
        try:
            requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(requete, timeout=30) as reponse:
                if reponse.status != 200:
                    return None
                return reponse.read()
        except urllib.error.HTTPError:
            return None                     # 404 : ce numéro n'existe pas
        except Exception:
            continue                        # réseau : une seconde tentative
    return None


def sonder(jour: date) -> dict[str, bool]:
    """Teste chaque numéro de chaîne connu et dit lesquels répondent."""
    semaine = samedi_de_la_semaine(jour).isoformat()
    print(f"Semaine testée : {semaine}\n")
    resultats = {}
    for numero, nom in CHAINES.items():
        url = URL_MODELE.format(chaine=numero, semaine=semaine)
        contenu = telecharger(url, essais=1)
        ok = bool(contenu) and b"EXPORT_TF1_PRO" in contenu
        resultats[numero] = ok
        marque = "OK  " if ok else "échec"
        note = "  <- numéro deviné, à confirmer" if numero in CHAINES_HYPOTHESE else ""
        taille = f"{len(contenu) // 1024} Ko" if contenu else "-"
        print(f" [{marque}] {numero:>3}  {nom:<16} {taille:>8}{note}")
    return resultats


def recuperer_une_chaine(numero: str, nom: str, jour: date, dossier: Path) -> Path | None:
    """Télécharge l'export et le convertit ; renvoie le chemin du JSON produit."""
    semaine = samedi_de_la_semaine(jour).isoformat()
    url = URL_MODELE.format(chaine=numero, semaine=semaine)
    contenu = telecharger(url)
    if not contenu or b"EXPORT_TF1_PRO" not in contenu:
        print(f"  {nom} : rien récupéré", file=sys.stderr)
        return None

    brut = dossier / f"export-{numero}-{semaine}.xml"
    brut.write_bytes(contenu)

    sortie = dossier / f"grille-{numero}-{jour.isoformat()}.json"
    commande = [
        sys.executable, str(RACINE / "sources" / "tf1pro.py"),
        "--fichier", str(brut),
        "--jour", jour.isoformat(),
        "--chaine", nom,
        "--sortie", str(sortie),
    ]
    resultat = subprocess.run(commande, capture_output=True, text=True)
    if resultat.returncode != 0:
        print(f"  {nom} : conversion impossible — {resultat.stderr.strip()}", file=sys.stderr)
        return None
    print(f"  {nom} : {resultat.stdout.strip()}", file=sys.stderr)
    return sortie


def fusionner(chemins: list[Path], jour: date, dossier: Path) -> Path:
    """Réunit les grilles de plusieurs chaînes en une seule soirée."""
    programmes, sources = [], []
    for chemin in chemins:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        programmes.extend(contenu["programmes"])
        sources.append(contenu.get("source", chemin.name))

    programmes.sort(key=lambda p: (p["debut"], p["chaine"]))
    grille = {
        "date": jour.isoformat(),
        "source": " + ".join(sources),
        "programmes": programmes,
    }
    sortie = dossier / f"grille-{jour.isoformat()}.json"
    sortie.write_text(json.dumps(grille, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGrille fusionnée : {sortie} ({len(programmes)} programmes, "
          f"{len(chemins)} chaîne(s))", file=sys.stderr)
    return sortie


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Récupère, convertit et classe les grilles du soir.")
    ap.add_argument("--jour", default=None, help="date AAAA-MM-JJ (défaut : aujourd'hui)")
    ap.add_argument("--chaines", default=None,
                    help="numéros de chaîne séparés par des virgules (défaut : tous ceux connus)")
    ap.add_argument("--profil", default=None, help="profil JSON pour top3.py")
    ap.add_argument("--dossier", default=None, help="où écrire les fichiers (défaut : data/)")
    ap.add_argument("--sonder", action="store_true", help="teste les numéros de chaîne et sort")
    ap.add_argument("--garder", action="store_true", help="conserve les exports XML téléchargés")
    args = ap.parse_args()

    jour = date.fromisoformat(args.jour) if args.jour else date.today()

    if args.sonder:
        resultats = sonder(jour)
        trouves = [n for n, ok in resultats.items() if ok]
        if not trouves:
            print("\nAucune chaîne n'a répondu. Vérifie l'URL ou la connexion.", file=sys.stderr)
            return 1
        print("\nNuméros confirmés : " + ", ".join(f"{n} ({CHAINES[n]})" for n in trouves))
        inconnus = [n for n in CHAINES if n not in trouves]
        if inconnus:
            print("Non confirmés : " + ", ".join(f"{n} ({CHAINES[n]})" for n in inconnus))
            print("Ouvre la page de la chaîne sur TF1 Pro et relève son lien « Télécharger (XML) ».")
        return 0

    dossier = Path(args.dossier) if args.dossier else RACINE / "data"
    dossier.mkdir(parents=True, exist_ok=True)

    numeros = ([n.strip() for n in args.chaines.split(",") if n.strip()]
               if args.chaines else list(CHAINES))

    print(f"Soirée du {jour.isoformat()} — {len(numeros)} chaîne(s) à interroger\n", file=sys.stderr)
    chemins = []
    for numero in numeros:
        nom = CHAINES.get(numero, f"chaîne {numero}")
        chemin = recuperer_une_chaine(numero, nom, jour, dossier)
        if chemin:
            chemins.append(chemin)

    if not chemins:
        print("Rien à classer.", file=sys.stderr)
        return 1

    grille = fusionner(chemins, jour, dossier)

    commande = [sys.executable, str(RACINE / "top3.py"), str(grille),
                "--date", jour.strftime("%d/%m/%Y")]
    if args.profil:
        commande += ["--profil", args.profil]
    resultat = subprocess.run(commande, capture_output=True, text=True)
    print()
    print(resultat.stdout.strip() or resultat.stderr.strip())
    return resultat.returncode


if __name__ == "__main__":
    raise SystemExit(main())
