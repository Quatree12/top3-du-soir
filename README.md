# Top 3 du soir

Un script qui lit la grille TV du soir, la note selon des critères pondérés, et
sort un **top 3 expliqué** — une ligne par programme, une raison par ligne.

Le principe : une liste complète de ce qui passe ce soir, on la trouve partout.
Un classement qui tranche, non. C'est tout ce que ce dépôt essaie de faire.

## État du projet

| Brique | État |
|---|---|
| 1. Récupération de la grille | Fonctionne — trois lecteurs, source XMLTV FR recommandée |
| 2. Moteur de notation | Fonctionne |
| 3. Générateur de message | Fonctionne |
| 4. Boucle de retour | Pas commencée |

Aucune dépendance : bibliothèque standard uniquement, Python 3.10 ou plus récent.

## Démarrage rapide

```bash
# 1. Convertir un fichier XMLTV en grille exploitable
python3 sources/xmltv.py --fichier xmltv_tnt.xml --jour 2026-11-11 \
        --chaines "TF1.fr,M6.fr,W9.fr,TMC.fr,NT1.fr,6ter.fr,TF1SeriesFilms.fr" \
        --soir-seulement --sortie data/grille-2026-11-11.json

# 2. Classer
python3 top3.py data/grille-2026-11-11.json --profil data/profil-exemple.json
python3 top3.py data/grille-2026-11-11.json --profil data/profil-exemple.json --tout
```

`--tout` affiche en plus les programmes écartés par les filtres et toutes les
notes, de la meilleure à la moins bonne.

`data/grille-exemple-9ch.json` contient une soirée réelle complète — le
mercredi 11 novembre 2026, neuf chaînes, 87 programmes — pour essayer le
classement sans rien télécharger.

## Les trois sources

Le classement consomme toujours le même format JSON interne ; trois lecteurs
produisent ce format.

### XMLTV FR — recommandé

Fichiers sur [xmltvfr.fr/xmltv.php](https://xmltvfr.fr/xmltv.php). Le format
[XMLTV](http://wiki.xmltv.org/index.php/XMLTVFormat) est normalisé : une liste
plate de `<programme>` portant chacune son horaire de début et de fin.

```xml
<programme start="20261111211000 +0100" stop="20261111215500 +0100" channel="TF1.fr">
  <title lang="fr">Esprits criminels : Evolution</title>
  <sub-title lang="fr">La mémoire de l'eau</sub-title>
  <desc lang="fr">…</desc>
  <category lang="fr">Série</category>
  <new />
</programme>
```

C'est la source à préférer, pour trois raisons :

- **L'heure de fin est fournie** (`stop`). Les autres sources obligent à la
  déduire de l'écart avec le programme suivant, ce qui produit des durées fausses
  sur les programmes de transition et sur ceux qui franchissent minuit.
- **Les chaînes suisses y sont** : `RTSUn.ch` et `RTSDeux.ch`, dans les variantes
  `xmltv.xml` (complet, ~782 chaînes) et `xmltv_fr.xml`. Le fichier TNT ne les a pas.
- **Une seule URL couvre tout**, y compris Canal+.

Extraction rapide sur la TNT seule :

```bash
python3 sources/xmltv.py --fichier xmltv_tnt.xml --jour 2026-11-11 --liste
```

### Groupe M6 — M6, W9, 6ter

Un export XML par chaîne et par semaine :

```text
https://pro.m6.fr/<chaîne>/grille/<année>-<numéro de semaine>.xml
```

Exemples : `pro.m6.fr/m6/grille/2026-49.xml`, `pro.m6.fr/w9/grille/2026-49.xml`.
L'accès est ouvert, sans compte. Le fichier est un flux RSS avec `<dateheure>`,
`<titreprogramme>`, `<format>` et un vrai booléen `<inedit>`. Pas d'heure de fin.

### TF1 Pro — TF1, TFX, TMC

Un export XML par chaîne et par semaine :

```text
https://tf1pro.com/grilles-xml/<numéro de chaîne>/<samedi de la semaine>
```

| Numéro | Chaîne |
|---|---|
| 17 | TF1 |
| 18 | TFX |
| 22 | TMC |

Exemple vérifié : `tf1pro.com/grilles-xml/22/2026-11-07` (semaine 46). Structure :
`<EXPORT_TF1_PRO>` → `<GRILLE>` → `<JOUR>` → `<EMISSION heureDiffusion="21.10">`,
avec `<titre>`, `<sousTitre>`, `<typeEmission>` et `<ineditTV valeur="1"/>`.
Pas d'heure de fin, pas de note de presse, et seulement cinq genres.

## Entrée : la grille

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

Les champs `inedit`, `note_presse` et `replay` sont optionnels. Genres reconnus :

| Genre | Ce qu'il couvre |
|---|---|
| `serie` | série, policier, feuilleton |
| `quotidienne` | quotidienne française *(attribué automatiquement)* |
| `film` | cinéma, téléfilm, long métrage |
| `documentaire` | documentaire, docu-société |
| `divertissement` | téléréalité, talk, jeu télévisé |
| `magazine` | magazine, talk-show |
| `jeu` | jeu |
| `info` | journal, météo |
| `sport` | retransmission sportive |

Le genre `quotidienne` n'est jamais écrit dans la source : `top3.py` le déduit du
titre. Une quotidienne française (*Demain nous appartient*, *Plus belle la vie*,
*Ici tout commence*…) et une série américaine (*NCIS*, *Esprits criminels*) n'ont
ni la même longueur ni le même attachement, et les noter pareil fausse tout.

## Entrée : le profil

```json
{
  "debut_soiree": "19:00",
  "heure_coucher": "23:30",
  "chaines_captees": ["TF1", "M6", "W9", "RTS Un"],
  "genres_aimes": {
    "film": 10, "serie": 8, "documentaire": 7, "magazine": 5,
    "quotidienne": 4, "divertissement": 3, "jeu": 3, "info": 2
  },
  "genres_exclus": [],
  "emissions_bannies": ["touche pas à mon poste", "super nanny"],
  "deja_vus": ["Hunger Games"],
  "majoration_chaine": { "RTS Un": 1 }
}
```

- **`debut_soiree` / `heure_coucher`** — la fenêtre de soirée. Un programme qui
  commence avant 19 h est écarté ; après minuit, la fenêtre se prolonge de six
  heures (un programme de 00 h 40 appartient encore à la soirée). Un programme
  qui finit après l'heure de coucher perd des points, d'autant plus qu'il déborde.
- **`chaines_captees`** — vide = toutes les chaînes de la grille sont retenues.
- **`genres_aimes`** — une note de 0 à 10 par genre, utilisée telle quelle comme
  critère d'affinité. Un genre absent vaut 5.
- **`genres_exclus`** — filtre dur, le programme est écarté avant le classement.
- **`emissions_bannies`** — filtre dur par mot-clé sur le titre. Comparaison en
  minuscules et par sous-chaîne : `"super nanny"` attrape toutes les variantes.
- **`deja_vus`** — titres exacts à exclure.
- **`majoration_chaine`** — petit bonus par chaîne, pour corriger un classement à
  la main. À utiliser avec parcimonie, c'est une béquille.

## Comment la note est calculée

Chaque programme reçoit une note de 0 à 10 par critère, puis la note finale est
la moyenne pondérée :

| Critère | Poids | Ce qu'il mesure |
|---|---|---|
| Affinité | 45 % | Genre déclaré dans le profil, ajusté par la chaîne |
| Effort | 20 % | Film ou doc plutôt que série ; léger retrait au-delà de 2 h 30 |
| Compatibilité horaire | 12 % | Dans la fenêtre de soirée, et fini avant le coucher |
| Réputation | 10 % | Note de presse, neutre (5/10) si absente |
| Nouveauté | 8 % | Inédit (7,5) ou rediffusion (6,0) |
| Confort | 5 % | Replay disponible |

Deux réglages valent d'être expliqués, parce qu'ils ont été corrigés après essai :

- **L'affinité pèse 45 %**, et les autres critères se partagent le reste. Avec des
  poids plus étalés, un même genre se retrouvait avec six programmes à égalité
  parfaite et le classement ne tranchait plus rien.
- **La nouveauté ne pèse que 8 %** et vaut 7,5 contre 6,0. En donnant 9 contre 5,
  une rediffusion perdait quatre points d'un coup, ce qui enterrait des films
  aimés sur des chaînes qui rediffusent beaucoup.

À note égale, les programmes sont départagés par leur proximité avec le prime
time (21 h) : un film de 21 h passe avant une rediffusion de 15 h.

## Le message

```text
Ce soir — mercredi 11 novembre

1. Le pari — RTS 1, 21:00, 1 h 33.  Note 7.3
   Pourquoi : fini à 22:33, avant ton coucher, tu aimes les films, format facile à suivre.

2. Arizona junior — RTS 1, 22:50, 1 h 30.  Note 7.3
   Pourquoi : fini à 00:20, avant ton coucher, tu aimes les films.

3. Toy Story 4 — 6ter, 19:00, 2 h 10.  Note 7.3
   Pourquoi : fini à 21:10, avant ton coucher, tu aimes les films.

Juste derrière : Kaamelott (6ter, 6.1) · Esprits criminels — La mémoire de l'eau (TF1, 6.1)

Réponds « 1 », « 2 », « 3 » ou « aucun » pour affiner les prochains classements.
```

## Ce qui manque

- **La boucle de retour.** Le message demande une réponse, mais rien ne la lit :
  `genres_aimes` et `emissions_bannies` se modifient à la main.
- **L'envoi.** La sortie va dans le terminal. Mail, message ou notification
  restent à brancher.
- **Les notes de presse.** Aucune source utilisée ici n'en fournit, donc le
  critère « réputation » est inerte à 5/10 pour tout le monde.
- **`sources/recuperer.py` a été retiré** : il ne gérait que TF1 Pro, qui n'est
  plus la source principale. Les téléchargements se font à la main depuis
  xmltvfr.fr, qui publie un fichier couvrant toutes les chaînes à la fois.

## Avertissement

Usage strictement personnel. La redistribution de grilles de programmes TV est
encadrée par des droits : vérifie la licence de ta source avant de publier ou de
diffuser quoi que ce soit qui en dépende.

## Licence

MIT — voir `LICENSE`.
