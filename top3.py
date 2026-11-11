#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Top 3 du soir — prototype.

Entrée  : un fichier JSON de grille (voir data/grille-exemple.json).
Sortie  : un top 3 commenté, texte prêt à coller dans un message.

Usage :
    python3 top3.py data/grille-exemple.json
    python3 top3.py data/grille-exemple.json --profil data/profil-exemple.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# --------------------------------------------------------------------------
# 1. Configuration : les poids du classement et le profil par défaut.
#    Tout ce qui est subjectif est ici, nulle part ailleurs.
# --------------------------------------------------------------------------

POIDS = {
    "affinite": 0.30,       # proximité avec les genres aimés / détestés
    "nouveaute": 0.20,      # inédit plutôt que rediffusion
    "reputation": 0.15,     # note presse / spectateurs, quand elle existe
    "compatibilite": 0.15,  # durée compatible avec l'heure de coucher
    "confort": 0.10,        # chaîne captée, replay disponible
    "effort": 0.10,         # engageant ou pas : série en cours, film long
}

PROFIL_DEFAUT = {
    "debut_soiree": "19:00",
    "heure_coucher": "23:30",
    "chaines_captees": [],
    "genres_aimes": {},
    "genres_exclus": [],
    "deja_vus": [],
    "majoration_chaine": {},
}

GENRES_CONFORTABLES = {"film", "documentaire", "divertissement", "magazine", "jeu"}
GENRES_ENGAGEANTS = {"serie", "feuilleton"}

# Libellés lisibles pour le message
NOMS_GENRES = {
    "serie": "série",
    "feuilleton": "feuilleton",
    "film": "film",
    "documentaire": "documentaire",
    "divertissement": "divertissement",
    "magazine": "magazine",
    "jeu": "jeu",
    "info": "information",
}
NOMS_CHAINES = {
    "TF1": "TF1", "M6": "M6", "W9": "W9", "TMC": "TMC",
    "RTS Un": "RTS 1", "RTS Deux": "RTS 2", "Canal+": "Canal+",
}


# --------------------------------------------------------------------------
# 2. Modèle de données
# --------------------------------------------------------------------------

@dataclass
class Programme:
    chaine: str
    titre: str
    debut: str                 # "21:10"
    duree_min: int
    genre: str
    inedit: bool = False
    note_presse: float | None = None
    replay: bool = False
    description: str = ""
    note: float = 0.0
    detail: dict = field(default_factory=dict)

    @property
    def debut_dt(self) -> datetime:
        h, m = (int(x) for x in self.debut.split(":"))
        return datetime(2000, 1, 1, h, m)

    @property
    def fin_dt(self) -> datetime:
        return self.debut_dt + timedelta(minutes=self.duree_min)

    @property
    def fin(self) -> str:
        return self.fin_dt.strftime("%H:%M")

    @property
    def duree_lisible(self) -> str:
        if self.duree_min % 60 == 0:
            return f"{self.duree_min // 60} h"
        return f"{self.duree_min // 60} h {self.duree_min % 60:02d}"

    @property
    def chaine_lisible(self) -> str:
        return NOMS_CHAINES.get(self.chaine, self.chaine)

    @property
    def genre_lisible(self) -> str:
        return NOMS_GENRES.get(self.genre, self.genre)


# --------------------------------------------------------------------------
# 3. Chargement
# --------------------------------------------------------------------------

def charger_programmes(chemin: Path) -> list[Programme]:
    brut = json.loads(chemin.read_text(encoding="utf-8"))
    programmes = []
    for item in brut["programmes"]:
        programmes.append(Programme(
            chaine=item["chaine"],
            titre=item["titre"],
            debut=item["debut"],
            duree_min=int(item["duree_min"]),
            genre=item.get("genre", "inconnu").lower(),
            inedit=bool(item.get("inedit", False)),
            note_presse=item.get("note_presse"),
            replay=bool(item.get("replay", False)),
            description=item.get("description", ""),
        ))
    return programmes


def charger_profil(chemin: Path | None) -> dict:
    profil = dict(PROFIL_DEFAUT)
    if chemin:
        profil.update(json.loads(chemin.read_text(encoding="utf-8")))
    return profil


# --------------------------------------------------------------------------
# 4. Filtres : ce qui sort du classement avant même d'être noté
# --------------------------------------------------------------------------

def filtrer(programmes: list[Programme], profil: dict) -> tuple[list[Programme], list[str]]:
    gardes, ecartes = [], []
    captees = [c.lower() for c in profil.get("chaines_captees", [])]
    exclus = [g.lower() for g in profil.get("genres_exclus", [])]
    deja_vus = [t.lower() for t in profil.get("deja_vus", [])]

    for p in programmes:
        if captees and p.chaine.lower() not in captees:
            ecartes.append(f"{p.titre} ({p.chaine_lisible}) — chaîne non captée")
        elif p.genre in exclus:
            ecartes.append(f"{p.titre} ({p.chaine_lisible}) — genre exclu : {p.genre_lisible}")
        elif p.titre.lower() in deja_vus:
            ecartes.append(f"{p.titre} ({p.chaine_lisible}) — déjà vu")
        else:
            gardes.append(p)
    return gardes, ecartes


# --------------------------------------------------------------------------
# 5. Notation : une note de 0 à 10 par critère, puis la moyenne pondérée
# --------------------------------------------------------------------------

def noter(p: Programme, profil: dict) -> Programme:
    aimes = {k.lower(): v for k, v in profil.get("genres_aimes", {}).items()}
    majoration = {k.lower(): v for k, v in profil.get("majoration_chaine", {}).items()}

    # Affinité : genre déclaré + coup de pouce éventuel sur la chaîne.
    affinite = aimes.get(p.genre, 5.0)
    affinite = max(0.0, min(10.0, affinite + majoration.get(p.chaine.lower(), 0.0)))

    # Nouveauté
    nouveaute = 9.0 if p.inedit else 5.0

    # Réputation : neutre tant qu'on n'a pas de note
    reputation = 5.0 if p.note_presse is None else max(0.0, min(10.0, p.note_presse))

    # Compatibilité horaire : le programme doit tomber dans la fenêtre de soirée.
    # Un critère qui ne regardait que « est-ce fini avant le coucher » notait 10/10
    # une émission de 5 h 50 du matin : la borne de début manquait.
    debut_soiree = datetime(2000, 1, 1, *[int(x) for x in profil.get("debut_soiree", "19:00").split(":")])
    coucher = datetime(2000, 1, 1, *[int(x) for x in profil.get("heure_coucher", "23:30").split(":")])

    if p.debut_dt < debut_soiree:
        # Hors de la fenêtre : d'autant plus bas qu'on s'en éloigne.
        avance = (debut_soiree - p.debut_dt).total_seconds() / 60
        compatibilite = max(0.0, 3.0 - avance / 120)          # 6 h d'avance => 0
    else:
        marge = (coucher - p.fin_dt).total_seconds() / 60
        if marge >= 15:
            compatibilite = 10.0
        elif marge >= 0:
            compatibilite = 8.0
        else:
            compatibilite = max(0.0, 6.0 + marge / 6)          # -36 min => 0

    # Confort : replay disponible
    confort = 9.0 if p.replay else 6.0

    # Effort : un film ou un doc se laisse regarder ; une série demande de suivre.
    effort = 7.5 if p.genre in GENRES_CONFORTABLES else 6.0 if p.genre in GENRES_ENGAGEANTS else 6.5
    if p.duree_min > 150:
        effort = max(0.0, effort - 2.0)   # un format très long décourage en semaine

    detail = {
        "affinite": affinite,
        "nouveaute": nouveaute,
        "reputation": reputation,
        "compatibilite": compatibilite,
        "confort": confort,
        "effort": effort,
    }
    p.note = round(sum(detail[c] * POIDS[c] for c in POIDS), 1)
    p.detail = detail
    return p


# --------------------------------------------------------------------------
# 6. Le message du soir
# --------------------------------------------------------------------------

def raisons(p: Programme) -> list[str]:
    """Les raisons lisibles, dérivées des critères les mieux notés."""
    out = []
    if p.detail["nouveaute"] >= 9:
        out.append("inédit")
    if p.detail["compatibilite"] >= 8:
        out.append(f"fini à {p.fin}, avant ton coucher")
    elif p.detail["compatibilite"] <= 3:
        out.append(f"attention, ça finit à {p.fin}")
    if p.detail["affinite"] >= 7:
        out.append(f"tu aimes les {p.genre_lisible}s" if p.genre != "film" else "tu aimes les films")
    if p.replay:
        out.append("replay disponible")
    if p.detail["effort"] >= 7:
        out.append("format facile à suivre")
    if p.note_presse is not None and p.note_presse >= 8:
        out.append(f"bien noté ({p.note_presse:.0f}/10)")
    return out[:3] or ["le mieux placé du soir"]


def construire_message(programmes: list[Programme], ecartes: list[str], date: str) -> str:
    complete = sorted(programmes, key=lambda p: (-p.note, p.debut))
    top3 = complete[:3]
    suivants = complete[3:5]

    lignes = [f"Ce soir — {date}", ""]
    for i, p in enumerate(top3, start=1):
        lignes.append(f"{i}. {p.titre} — {p.chaine_lisible}, {p.debut}, {p.duree_lisible}.  Note {p.note:.1f}")
        lignes.append(f"   Pourquoi : {', '.join(raisons(p))}.")
        lignes.append("")

    if suivants:
        lignes.append("Juste derrière : " + " · ".join(
            f"{p.titre} ({p.chaine_lisible}, {p.note:.1f})" for p in suivants))
        lignes.append("")

    if ecartes:
        lignes.append(f"Écartés avant classement : {len(ecartes)} programme(s). La liste est dans le log.")
        lignes.append("")

    lignes.append("Réponds « 1 », « 2 », « 3 » ou « aucun » pour affiner les prochains classements.")
    return "\n".join(lignes)


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Top 3 des programmes de la soirée.")
    ap.add_argument("grille", help="fichier JSON de la grille du soir")
    ap.add_argument("--profil", help="fichier JSON de profil (optionnel)")
    ap.add_argument("--date", default=None, help="libellé de date, ex. « mercredi 11 novembre »")
    ap.add_argument("--tout", action="store_true", help="affiche aussi les programmes écartés")
    args = ap.parse_args()

    programmes = charger_programmes(Path(args.grille))
    profil = charger_profil(Path(args.profil) if args.profil else None)

    gardes, ecartes = filtrer(programmes, profil)
    if not gardes:
        print("Aucun programme retenu : vérifie les filtres du profil.", file=sys.stderr)
        return 1

    for p in gardes:
        noter(p, profil)

    date = args.date or datetime.now().strftime("%d/%m/%Y")
    print(construire_message(gardes, ecartes, date))

    if args.tout:
        print("\n--- Programmes écartés ---")
        for ligne in ecartes:
            print(" -", ligne)
        print("\n--- Notes complètes ---")
        for p in sorted(gardes, key=lambda x: -x.note):
            print(f" {p.note:>4.1f}  {p.chaine:<10} {p.titre} ({p.debut}-{p.fin})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
