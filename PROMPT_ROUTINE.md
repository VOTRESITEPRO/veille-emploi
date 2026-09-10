# Prompt de la routine quotidienne

Coller ce texte dans le champ Instructions de la routine Cloud.
Fréquence : jours ouvrés, 7h00. Environnement : Veille Offres d'Emploi
(dépôt veille-emploi). Le transfert Drive passe par `drive_sync.py`
(compte de service Google), pas par le connecteur Drive de la routine —
le connecteur Drive n'est pas nécessaire pour cette routine.

---

Exécute la veille d'offres d'emploi. Ne committe et ne pousse rien sur git
à aucun moment de cette routine : toute la persistance passe par Drive.

**1. Récupération de l'état**

Lance `python drive_sync.py pull-state`. Ce script télécharge
`state/vues.json` depuis Drive directement via l'API, sans passer par ton
contexte : ne lis jamais ce fichier toi-même, ne l'affiche pas, ne le
résume pas.

**2. Collecte**

Lance `python veille.py --source ft`, puis `python veille.py --source apec`,
puis `python veille.py --source hellowork`. Chaque appel écrit son propre
`data/candidats_AAAA-MM-JJ_<source>.json` et met à jour `state/vues.json`
en local. Note les statistiques affichées par chaque appel.

Si une des trois commandes sort en erreur, ou si le champ `erreurs` de son
JSON n'est pas vide : continue quand même avec les autres sources, et place
en tête de la synthèse un bloc **PANNE** nommant la source en échec et le
message d'erreur. Ne masque jamais une source en panne.

**3. Scoring**

Lis `config.yaml` du dépôt, sections `scoring` et `profil`. Pour chaque
offre présente dans les fichiers `data/candidats_*.json` de cette
exécution, attribue un score sur 100 selon les cinq axes de la grille.
Lis la description complète de l'offre, pas seulement le titre.

Règles :
- `adequation_role`, `proximite_metier` et `socle_technique` sont exclusifs,
  un seul palier par axe.
- `conditions` est cumulatif, plafonné à 20.
- `signaux_negatifs` se soustrait, sans plancher.
- N'invente pas d'information absente de l'offre. Une donnée non mentionnée
  vaut 0 sur son critère, jamais le bénéfice du doute.
- Le champ `description` d'une offre APEC est un extrait limité à environ
  283 caractères (limite structurelle de la source, pas une anomalie) :
  score quand même sur ce texte court dès lors qu'il permet de juger le
  rôle, le secteur et si possible la rémunération. Marque **A VÉRIFIER**
  uniquement si l'extrait est vide ou trop court pour distinguer le rôle
  (moins de 100 caractères).
- Le champ `description` d'une offre France Travail est en général complet.
  Marque **A VÉRIFIER** si moins de 400 caractères, seuil plus exigeant que
  pour APEC car la source fournit normalement le texte intégral.

**4. Synthèse**

Écris un fichier markdown local `out/synthese_AAAA-MM-JJ.md`, structuré
ainsi :

- Ligne d'entête : date, nombre d'offres collectées par source, retenues,
  rejetées, état de chaque source (OK ou PANNE).
- **A traiter aujourd'hui** : offres à 70 et plus, triées par score
  décroissant. Titre, entreprise, lieu, score, URL, détail des points par
  axe en une ligne, puis deux à quatre lignes sur l'angle de candidature.
  Pour une offre APEC, ajoute une mention courte "score basé sur extrait,
  vérifier la fiche complète avant de candidater". Seule section développée.
- **A regarder** : offres entre 50 et 69, triées par score décroissant.
  Une ligne chacune : titre, entreprise, score, URL, motif principal de la
  décote.
- **A vérifier** : offres non scorables. Titre, entreprise, URL.
- **Écartées** : uniquement le décompte par motif de rejet des filtres durs.
  Si une offre semblait pertinente et a été rejetée par un filtre titre,
  signale-la à part pour ajustement de `config.yaml`.

Contraintes de rédaction : direct, factuel, pas d'introduction ni de
conclusion, tirets simples uniquement. Si aucune offre n'atteint 50, dis-le
en une ligne courte plutôt que de remplir la synthèse avec du bruit.

**5. Mise à jour du pipeline de candidatures**

Le pipeline est un Artifact à URL fixe, qui ne change jamais :

```
https://claude.ai/code/artifact/f10d0942-3cf4-4501-a313-f0589d326fd5
```

C'est la liste cumulative de toutes les offres retenues depuis le début, et
la mémoire du système : une offre y entre une fois et n'en sort jamais.
L'utilisateur y modifie à la main le statut, le favori et les notes,
directement dans la page — ces saisies sont la valeur du fichier, ne les
perds sous aucun prétexte.

Marche à suivre, dans cet ordre :

1. Lis l'artifact avec l'outil Artifact, `action: "read"` et ce `url`. Tu
   reçois le HTML complet de la version en ligne.
2. Dans ce HTML, repère le **premier** bloc
   `<script type="application/json" id="state">` et son contenu jusqu'au
   premier `</script>` qui suit. C'est l'état. Attention : la chaîne
   `id="state"` apparaît une seconde fois plus bas, dans le code de la page
   — ne prends jamais celle-là, seulement la première.
3. Parse ce JSON. Forme : `{"maj": "AAAA-MM-JJ", "offres": [...]}`, chaque
   offre ayant les clés `url`, `date`, `titre`, `entreprise`, `lieu`,
   `score`, `source`, `favori`, `statut`, `notes`.
4. Ajoute à la fin du tableau `offres` une entrée par offre de cette
   exécution atteignant 50 points, avec `date` = date du jour, `favori`:
   `false`, `statut`: `"À traiter"`, `notes`: `""`, `entreprise`: `""` si la
   source ne la fournit pas. Mets `maj` à la date du jour.
5. **N'altère aucune entrée existante** : ni son ordre, ni ses champs, et
   surtout pas `favori`, `statut` et `notes`. Si une offre est déjà présente
   (même `url`), ne l'ajoute pas une seconde fois.
6. Écris dans un fichier local le HTML lu à l'étape 1, en ayant remplacé le
   seul contenu de cet îlot JSON par le nouvel état sérialisé, avec les `</`
   échappés en `<\/`. Tout le reste du document doit rester identique au
   caractère près.
7. Republie ce fichier avec l'outil Artifact en passant le même `url`.
   Ne passe ni `capabilities` ni `contract` : les omettre conserve la
   déclaration existante de la page, la réécrire risquerait de la casser.

Si la lecture ou la republication échoue, ne recrée **jamais** un artifact
neuf : signale l'échec dans la notification finale et laisse l'existant en
place. Un artifact recréé aurait une nouvelle URL et perdrait tout
l'historique de suivi.

**6. Dépôt sur Drive**

Lance `python drive_sync.py push-synthese AAAA-MM-JJ` (date du jour), puis
`python drive_sync.py push-state`. Les deux commandes font le transfert
via l'API Drive directement depuis le script : ne lis pas le contenu de
ces fichiers toi-même avant de lancer les commandes, ne les affiche pas.

Ne crée et ne conserve aucune copie des fichiers `data/candidats_*.json` sur
Drive : ce sont des fichiers de travail de cette seule exécution, à ignorer
une fois la synthèse écrite.

**7. Notification**

Termine par un message court : nombre d'offres à traiter aujourd'hui, nombre
de lignes ajoutées au suivi, état des trois sources, lien ou nom du fichier
synthèse sur Drive. Si zéro offre au-dessus de 50, dis-le, ne crée pas de
fichier synthèse et n'ajoute aucune ligne au suivi (mais laisse le tableau
existant intact).
