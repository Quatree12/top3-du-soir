# Top 3 du soir

Un script qui lit la grille TV du soir, la note selon des critères pondérés, et
sort un **top 3 expliqué** — une ligne par programme, une raison par ligne.

Le principe : une liste complète de ce qui passe ce soir, on la trouve partout.
Un classement qui tranche, non. C'est tout ce que ce dépôt essaie de faire.

## État du projet

Prototype. Trois briques sur quatre fonctionnent :

| Brique | État |
|---|---|
| 1. Récupération de la grille | Partielle — export XML TF1 Pro, en mono-chaîne |
| 2. Moteur de notation | Fonctionne |
| 3. Générateur de message | Fonctionne |
| 4. Boucle de retour | Pas commencée |

Aucune dépendance : bibliothèque standard uniquement, Python 3.10 ou plus récent.

## Utilisation

```bash
# 1. Convertir un export XML TF1 Pro en grille exploitable
python3 sources/tf1pro.py --fichier export-tf1.xml --jour 2026-11-11 \
        --chaine TF1 --sortie data/grille-2026-11-11.json

# Variante : ne garder que la soirée (à partir de 19 h)
python3 sources/tf1pro.py --fichier export-tf1.xml --jour 2026-11-11 \
        --chaine TF1 --soir-seulement --sortie data/grille-soir.json

# Lister les jours contenus dans un export
python3 sources/tf1pro.py --fichier export-tf1.xml --jour 2026-11-11 --liste

# 2. Classer
python3 top3.py data/grille-2026-11-11.json
python3 top3.py data/grille-2026-11-11.json --profil data/profil-exemple.json
python3 top3.py data/grille-2026-11-11.json --profil data/profil-exemple.json --tout
```

`--tout` affiche en plus les programmes écartés par les filtres et toutes les
notes, de la meilleure à la moins bonne.

## La source : export XML TF1 Pro

Le groupe TF1 publie une grille XML par chaîne, à récupérer depuis le site
TF1 Pro (page de la chaîne, lien « Télécharger (XML) »). Structure réelle du
fichier, vérifiée sur un export :

```xml
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
      </EMISSION>
    </JOUR>
  </GRILLE>
</EXPORT_TF1_PRO>
```

Trois limites de cette source, à connaître :

1. **Pas d'heure de fin ni de durée.** La durée se déduit de l'écart avec le
   programme suivant sur la même chaîne. Le lecteur le fait (`data/`).
2. **Pas de note de presse.** Le critère « réputation » du classement reste donc
   neutre (5/10) pour tous les programmes issus de cette source.
3. **Quatre genres seulement** : Série, Téléfilm, Divertissement, Info,
   Programme court. Ils sont traduits vers les genres attendus par `top3.py`.

**Une chaîne par export.** Le classement devient vraiment utile à partir de trois
ou quatre exports combinés : avec une seule chaîne, les critères objectifs se
ressemblent trop et le top 3 ne tranche plus rien.

M6, W9, RTS 1 et RTS 2 ne sont pas dans l'écosystème TF1 Pro : il faut une autre
source pour elles.

## Entrée : la grille

Un fichier JSON avec une liste de programmes :

```json
{
  "date": "2026-11-11",
  "programmes": [
    {
      "chaine": "TF1",
      "titre": "Esprits criminels : Evolution",
      "debut": "21:10",
      "duree_min": 110,
      "genre": "serie",
      "inedit": true,
      "note_presse": 7.5,
      "replay": true
    }
  ]
}
```

Les champs `inedit`, `note_presse` et `replay` sont optionnels. Une note de presse
absente rend le critère « réputation » neutre plutôt que de pénaliser le programme.

Genres reconnus : `serie`, `feuilleton`, `film`, `documentaire`, `divertissement`,
`magazine`, `jeu`, `info`.

## Entrée : le profil

```json
{
  "debut_soiree": "19:00",
  "heure_coucher": "23:30",
  "chaines_captees": ["TF1", "M6", "RTS Un"],
  "genres_aimes": { "serie": 8, "film": 7, "divertissement": 4 },
  "genres_exclus": ["jeu"],
  "deja_vus": ["Hunger Games"],
  "majoration_chaine": { "RTS Un": 1 }
}
```

- `debut_soiree` et `heure_coucher` délimitent la fenêtre de soirée. Un programme
  qui commence avant 19 h ou qui finit après l'heure de coucher est fortement
  pénalisé ; le critère de compatibilité horaire ne regarde pas seulement la fin.
- `chaines_captees` : vide = toutes les chaînes de la grille sont retenues.
- `genres_aimes` : une note de 0 à 10 par genre, utilisée telle quelle comme
  critère d'affinité. Un genre absent vaut 5.
- `genres_exclus` : filtre dur, le programme est écarté avant le classement.
- `deja_vus` : titres à exclure.
- `majoration_chaine` : petit bonus par chaîne, pour corriger un classement à la
  main. À utiliser avec parcimonie, c'est une béquille.

## Comment la note est calculée

Chaque programme reçoit une note de 0 à 10 par critère, puis la note finale est
la moyenne pondérée :

| Critère | Poids | Ce qu'il mesure |
|---|---|---|
| Affinité | 30 % | Genre déclaré dans le profil, ajusté par la chaîne |
| Nouveauté | 20 % | Inédit (9) ou rediffusion (5) |
| Réputation | 15 % | Note de presse, neutre si absente |
| Compatibilité horaire | 15 % | Dans la fenêtre de soirée, et fini avant le coucher |
| Confort | 10 % | Replay disponible |
| Effort | 10 % | Film ou doc plutôt que série ; pénalité au-delà de 2 h 30 |

Les poids sont dans le dictionnaire `POIDS`, en haut de `top3.py`. C'est le seul
endroit à modifier pour changer le comportement du classement — le reste en
découle.

## Le message

```text
Ce soir — mercredi 11 novembre

1. Esprits criminels : Evolution — La mémoire de l'eau — TF1, 21:10, 0 h 45.  Note 7.7
   Pourquoi : inédit, fini à 21:55, avant ton coucher, tu aimes les séries.

2. Esprits criminels : Evolution — Le dompteur — TF1, 21:55, 1 h 05.  Note 7.7
   Pourquoi : inédit, fini à 23:00, avant ton coucher, tu aimes les séries.

3. JT 20h Semaine — TF1, 20:00, 0 h 45.  Note 6.8
   Pourquoi : fini à 20:45, avant ton coucher.

Juste derrière : Koh-Lanta (TF1, 5.8)

Réponds « 1 », « 2 », « 3 » ou « aucun » pour affiner les prochains classements.
```

## Ce qui manque

- **Les autres chaînes.** Le lecteur TF1 Pro est validé pour une chaîne ; il faut
  les exports TMC, TFX et consorts, et une autre source pour M6, W9, RTS 1 et RTS 2.
- **La boucle de retour.** Le message demande une réponse, mais rien ne la lit
  encore : `genres_aimes` et `majoration_chaine` se modifient à la main.
- **L'envoi.** Le script écrit dans le terminal. Mail, message ou notification
  restent à brancher.
- **Les notes de presse.** Absentes de l'export TF1 Pro, donc le critère
  « réputation » est inerte sur cette source.

## Avertissement

Usage strictement personnel. La redistribution de grilles de programmes TV est
encadrée par des droits : vérifie la licence de ta source avant de publier ou de
diffuser quoi que ce soit qui en dépende.

## Licence

MIT — voir `LICENSE`.
