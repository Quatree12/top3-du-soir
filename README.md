# Top 3 du soir

Un script qui lit la grille TV du soir, la note selon des critères pondérés, et
sort un **top 3 expliqué** — une ligne par programme, une raison par ligne.

Le principe : une liste complète de ce qui passe ce soir, on la trouve partout.
Un classement qui tranche, non. C'est tout ce que ce dépôt essaie de faire.

## État du projet

Prototype. C'est la brique 2 (moteur de notation) et la brique 3 (générateur de
message) de la spécification, qui fonctionnent sur une grille fournie à la main.
La récupération automatique des programmes n'est **pas** branchée : pour l'instant
tu remplis un fichier JSON et le script fait le reste.

## Utilisation

```bash
python3 top3.py data/grille-exemple.json
python3 top3.py data/grille-exemple.json --profil data/profil-exemple.json
python3 top3.py data/grille-exemple.json --profil data/profil-exemple.json --tout
```

`--tout` affiche en plus les programmes écartés par les filtres et toutes les
notes, de la meilleure à la moins bonne.

Aucune dépendance : bibliothèque standard uniquement, Python 3.10 ou plus récent.

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
absente rend le critère « réputation » neutre (5/10) plutôt que de pénaliser le
programme.

Genres reconnus : `serie`, `feuilleton`, `film`, `documentaire`, `divertissement`,
`magazine`, `jeu`, `info`.

## Entrée : le profil

```json
{
  "heure_coucher": "23:30",
  "chaines_captees": ["TF1", "M6", "RTS Un"],
  "genres_aimes": { "serie": 8, "film": 7, "divertissement": 4 },
  "genres_exclus": ["jeu"],
  "deja_vus": ["Hunger Games"],
  "majoration_chaine": { "RTS Un": 1 }
}
```

- `heure_coucher` : sert au critère de compatibilité horaire. Un programme qui
  finit après est fortement pénalisé, surtout s'il déborde de plus de 35 minutes.
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
| Compatibilité horaire | 15 % | Fini avant l'heure de coucher, ou non |
| Confort | 10 % | Replay disponible |
| Effort | 10 % | Film ou doc plutôt que série ; pénalité au-delà de 2 h 30 |

Les poids sont dans le dictionnaire `POIDS`, en haut du script. C'est le seul
endroit à modifier pour changer le comportement du classement — le reste en
découle.

## Le message

```text
Ce soir — mercredi 11 novembre

1. Esprits criminels : Evolution — TF1, 21:10, 1 h 50.  Note 8.3
   Pourquoi : inédit, fini à 23:00, avant ton coucher, tu aimes les séries.

2. La vie rêvée des autres — RTS 1, 20:55, 1 h 40.  Note 8.1
   Pourquoi : inédit, fini à 22:35, avant ton coucher, tu aimes les films.

3. La Petite Vadrouille — RTS 2, 20:55, 1 h 40.  Note 7.2
   Pourquoi : fini à 22:35, avant ton coucher, tu aimes les films, replay disponible.

Juste derrière : Esprits criminels (W9, 6.8) · La France a un incroyable talent (M6, 6.2)

Réponds « 1 », « 2 », « 3 » ou « aucun » pour affiner les prochains classements.
```

## Ce qui manque

- **La récupération automatique de la grille.** Aujourd'hui, les programmes se
  saisissent à la main. C'est le vrai travail restant, et de loin.
- **La boucle de retour.** Le message demande une réponse, mais rien ne la lit
  encore : `genres_aimes` et `majoration_chaine` se modifient à la main.
- **L'envoi.** Le script écrit dans le terminal. Mail, message ou notification
  restent à brancher.
- **Canal+.** Les guides publics tronquent la grille des chaînes payantes, donc
  la chaîne n'apparaît pas dans les exemples.

## Sources de programmes

Trois pistes, de la plus simple à la plus lourde :

1. Saisie manuelle pour 3 ou 4 chaînes — suffisant pour juger le classement.
2. Une base EPG commerciale ou une API de programmes — fiable, souvent payante,
   et la licence d'usage est le vrai point de blocage, pas la technique.
3. Agrégation depuis les pages des chaînes — gratuit, fragile, à maintenir.

Certaines chaînes publient une grille XML officielle (TF1 Pro, par exemple), ce
qui évite le scraping pour celles-là.

## Avertissement

Usage strictement personnel. La redistribution de grilles de programmes TV est
encadrée par des droits : vérifie la licence de ta source avant de publier ou de
diffuser quoi que ce soit qui en dépende.

## Licence

MIT — voir `LICENSE`.
