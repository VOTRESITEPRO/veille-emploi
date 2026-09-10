# Prompt de la routine quotidienne

Coller ce texte dans le champ Instructions de la routine Cloud.
Fréquence : jours ouvrés, 7h00. Environnement : Veille Offres d'Emploi
(dépôt veille-emploi, connecteur Google Drive actif).

Dossier Drive de référence : Mon Drive/CLAUDE/OFFRES EMPLOI

---

Exécute la veille d'offres d'emploi. Ne committe et ne pousse rien sur git
à aucun moment de cette routine : toute la persistance passe par Drive.

**1. Récupération de l'état**

Lis le fichier `state/vues.json` sur Drive, dans
`Mon Drive/CLAUDE/OFFRES EMPLOI/state/vues.json`.

S'il existe : écris son contenu tel quel dans `state/vues.json` en local,
à la racine du dépôt cloné (crée le dossier `state/` s'il n'existe pas).
S'il n'existe pas encore (premier lancement) : ne crée rien en local, le
script partira d'un historique vide.

**2. Collecte**

Lance `python veille.py --source ft`, puis `python veille.py --source apec`.
Chaque appel écrit son propre `data/candidats_AAAA-MM-JJ.json` et met à jour
`state/vues.json` en local. Note les statistiques affichées par chaque appel.

Si une des deux commandes sort en erreur, ou si le champ `erreurs` de son
JSON n'est pas vide : continue quand même avec l'autre source, et place en
tête de la synthèse un bloc **PANNE** nommant la source en échec et le
message d'erreur. Ne masque jamais une source en panne.

**3. Scoring**

Lis `config.yaml` du dépôt, sections `scoring` et `profil`. Pour chaque
offre présente dans les deux fichiers `data/candidats_*.json` de cette
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
