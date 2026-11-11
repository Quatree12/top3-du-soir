# Top 3 du soir

Un script qui lit la grille TV du soir, la note selon des critères pondérés, et
sort un **top 3 expliqué** — une ligne par programme, une raison par ligne.

Le principe : une liste complète de ce qui passe ce soir, on la trouve partout.
Un classement qui tranche, non. C'est tout ce que ce dépôt essaie de faire.

## État du projet

| Brique | État |
|---|---|
| 1. Récupération de la grille | Fonctionne pour le groupe TF1 (TF1 Pro) |
| 2. Moteur de notation | Fonctionne |
| 3. Générateur de message | Fonctionne |
| 4. Boucle de retour | Pas commencée |

Aucune dépendance : bibliothèque standard uniquement, Python 3.10 ou plus récent.

## Démarrage rapide

```bash
# 1. Quelles chaînes répondent ? (à faire une fois)
python3 sources/recuperer.py --sonder

# 2. La soirée du jour, téléchargée et classée en une commande
python3 sources/recuperer.py --profil data/profil-exemple.json

# 3. Un jour précis
python3 sources/recuperer.py --jour 2026-11-11 --profil data/profil-exemple.json
```

## La source : export XML TF1 Pro

Le groupe TF1 publie une grille XML par chaîne et par semaine :

```text
https://tf1pro.com/grilles-xml/<numéro de chaîne>/<samedi de la semaine>
```

Exemple vérifié : `https://tf1pro.com/grilles-xml/22/2026-11-07` (TMC, semaine 46,
du 7 au 13 novembre 2026). **L'accès est ouvert, sans compte.**

Les exports vont du **samedi au vendredi**. Le script calcule donc le samedi de la
semaine qui contient la date demandée : une demande pour le mercredi 11 novembre
récupère l'export du 7 novembre.

### Numéros de chaîne

| Numéro | Chaîne | Statut |
|---|---|---|
| 22 | TMC | Confirmé |
| 1 | TF1 | Hypothèse, à tester |
| 3 | TFX | Hypothèse, à tester |
| 4 | TF1 Séries Films | Hypothèse, à tester |
| 5 | LCI | Hypothèse, à tester |

`python3 sources/recuperer.py --sonder` teste chaque numéro et dit lesquels
répondent. Si un numéro échoue, ouvre la page de la chaîne sur TF1 Pro et relève
le lien « Télécharger (XML) » : le numéro est dans l'URL.

### Structure du fichier

```xml
<EXPORT_TF1_PRO>
  <DERNIERE_MAJ>10/11/2026</DERNIERE_MAJ>
  <GRILLE numeroSemaine="46" dateDebut="07/11/2026" dateFin="13/11/2026">
    <JOUR id="4" date="11/11/2026">
      <EMISSION heureDiffusion="21.10">
        <titre><![CDATA[Esprits criminels : Evolution]]></titre>
        <sousTitre><![CDATA[La mémoire de l'eau]]></sousTitre>
        <typeEmission><![CDATA[Série]]></typeEmission>
        <ineditTV valeur="1"><![CDATA[INEDIT]]></ineditTV>
        <replay valeur="0"/>
      </EMISSION>
    </JOUR>
  </GRILLE>
</EXPORT_TF1_PRO>
```

Trois limites de cette source :

1. **Pas d'heure de fin ni de durée.** La durée se déduit de l'écart avec le
   programme suivant sur la même chaîne. Deux artefacts en découlent : un
   programme de transition peut ressortir très court, et un programme qui franchit
   minuit est mal calculé.
2. **Pas de note de presse.** Le critère « réputation » du classement reste neutre
   (5/10) pour tous les programmes issus de cette source.
3. **Cinq genres seulement** : Série, Téléfilm, Divertissement, Info, Programme
   court. Ils sont traduits vers les genres attendus par `top3.py`.

**M6, W9, RTS 1 et RTS 2 ne sont pas dans l'écosystème TF1 Pro.** Il faut une
autre source pour elles.

## Chaînes de traitement

```text
recuperer.py  →  télécharge l'export XML
              →  tf1pro.py convertit en grille JSON
              →  fusionne toutes les chaînes en une seule soirée
              →  top3.py classe et affiche le top 3
```

Chaque étape est utilisable seule : `tf1pro.py` sur un fichier déjà téléchargé,
`top3.py` sur une grille écrite à la main.

## Planification

Pour recevoir le top 3 chaque soir sans rien lancer, programme la commande :

```bash
python3 sources/recuperer.py --profil data/profil-exemple.json \
  >> journal-soir.log 2>&1
```

**Linux / macOS** — `crontab -e`, puis une ligne pour 18 h 30 du lundi au vendredi :

```cron
30 18 * * 1-5 cd /chemin/vers/top3-du-soir && /usr/bin/python3 sources/recuperer.py --profil data/profil-exemple.json >> journal-soir.log 2>&1
```

**Windows** — Planificateur de tâches, action « Démarrer un programme » :

```text
Programme   : python
Arguments  : sources\recuperer.py --profil data\profil-exemple.json
Démarrer dans : C:\chemin\vers\top3-du-soir
Déclencheur : tous les jours, 18:30
```

À ce stade, la sortie va dans un journal local. L'envoi par mail ou message n'est
pas branché.

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
`serie`, `feuilleton`, `film`, `documentaire`, `divertissement`, `magazine`,
`jeu`, `info`.

## Entrée : le profil

```json
{
  "debut_soiree": "19:00",
  "heure_coucher": "23:30",
  "chaines_captees": ["TF1", "TMC", "RTS Un"],
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

Réponds « 1 », « 2 », « 3 » ou « aucun » pour affiner les prochains classements.
```

## Ce qui manque

- **Les autres chaînes.** Le groupe TF1 est couvert ; M6, W9, RTS 1 et RTS 2
  demandent une autre source.
- **La boucle de retour.** Le message demande une réponse, mais rien ne la lit
  encore : `genres_aimes` et `majoration_chaine` se modifient à la main.
- **L'envoi.** La sortie va dans le terminal ou un journal. Mail, message ou
  notification restent à brancher.
- **Les notes de presse.** Absentes de l'export TF1 Pro, donc le critère
  « réputation » est inerte sur cette source.

## Avertissement

Usage strictement personnel. La redistribution de grilles de programmes TV est
encadrée par des droits : vérifie la licence de ta source avant de publier ou de
diffuser quoi que ce soit qui en dépende.

## Licence

MIT — voir `LICENSE`.
