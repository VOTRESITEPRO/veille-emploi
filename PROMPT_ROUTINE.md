# Prompt de la routine quotidienne

Coller ce texte dans le champ Instructions de la routine Cloud.
Frequence : jours ouvres, 7h00. Environnement : Veille Offres d'Emploi
(dépôt veille-emploi, connecteur Google Drive actif).

Dossier Drive de reference : Mon Drive/CLAUDE/OFFRES EMPLOI

---

Execute la veille d'offres d'emploi. Ne committe et ne pousse rien sur git
a aucun moment de cette routine : toute la persistance passe par Drive.

**1. Recuperation de l'etat**

Lis le fichier `state/vues.json` sur Drive, dans
`Mon Drive/CLAUDE/OFFRES EMPLOI/state/vues.json`.

S'il existe : ecris son contenu tel quel dans `state/vues.json` en local,
a la racine du depot clone (cree le dossier `state/` s'il n'existe pas).
S'il n'existe pas encore (premier lancement) : ne cree rien en local, le
script partira d'un historique vide.

**2. Collecte**

Lance `python veille.py --source ft`, puis `python veille.py --source apec`.
Chaque appel ecrit son propre `data/candidats_AAAA-MM-JJ.json` et met a jour
`state/vues.json` en local. Note les statistiques affichees par chaque appel.

Si une des deux commandes sort en erreur, ou si le champ `erreurs` de son
JSON n'est pas vide : continue quand meme avec l'autre source, et place en
tete de la synthese un bloc **PANNE** nommant la source en echec et le
message d'erreur. Ne masque jamais une source en panne.

**3. Scoring**

Lis `config.yaml` du depot, sections `scoring` et `profil`. Pour chaque
offre presente dans les deux fichiers `data/candidats_*.json` de cette
execution, attribue un score sur 100 selon les cinq axes de la grille.
Lis la description complete de l'offre, pas seulement le titre.

Regles :
- `adequation_role`, `proximite_metier` et `socle_technique` sont exclusifs,
  un seul palier par axe.
- `conditions` est cumulatif, plafonne a 20.
- `signaux_negatifs` se soustrait, sans plancher.
- N'invente pas d'information absente de l'offre. Une donnee non mentionnee
  vaut 0 sur son critere, jamais le benefice du doute.
- Le champ `description` d'une offre APEC est un extrait limite a environ
  283 caracteres (limite structurelle de la source, pas une anomalie) :
  score quand meme sur ce texte court des lors qu'il permet de juger le
  role, le secteur et si possible la remuneration. Marque **A VERIFIER**
  uniquement si l'extrait est vide ou trop court pour distinguer le role
  (moins de 100 caracteres).
- Le champ `description` d'une offre France Travail est en general complet.
  Marque **A VERIFIER** si moins de 400 caracteres, seuil plus exigeant que
  pour APEC car la source fournit normalement le texte integral.

**4. Synthese**

Ecris un fichier markdown local `out/synthese_AAAA-MM-JJ.md`, structure
ainsi :

- Ligne d'entete : date, nombre d'offres collectees par source, retenues,
  rejetees, etat de chaque source (OK ou PANNE).
- **A traiter aujourd'hui** : offres a 70 et plus. Titre, entreprise, lieu,
  score, URL, detail des points par axe en une ligne, puis deux a quatre
  lignes sur l'angle de candidature. Pour une offre APEC, ajoute une mention
  courte "score base sur extrait, verifier la fiche complete avant de
  candidater". Seule section developpee.
- **A regarder** : offres entre 50 et 69. Une ligne chacune : titre,
  entreprise, score, URL, motif principal de la decote.
- **A verifier** : offres non scorables. Titre, entreprise, URL.
- **Ecartees** : uniquement le decompte par motif de rejet des filtres durs.
  Si une offre semblait pertinente et a ete rejetee par un filtre titre,
  signale-la a part pour ajustement de `config.yaml`.

Contraintes de redaction : direct, factuel, pas d'introduction ni de
conclusion, tirets simples uniquement. Si aucune offre n'atteint 50, dis-le
en une ligne courte plutot que de remplir la synthese avec du bruit.

**5. Mise a jour du suivi de candidatures**

Le Google Sheet `Suivi candidatures` dans `Mon Drive/CLAUDE/OFFRES EMPLOI/`
est la liste cumulative de toutes les offres retenues depuis le debut. Il
n'est jamais remis a zero : c'est lui qui permet de retrouver une offre
reperee un jour precedent et de suivre l'avancement d'une candidature.

Retrouve-le **par son nom** (`title = 'Suivi candidatures'`), jamais par un
identifiant fixe : son identifiant Drive change a chaque mise a jour, pour
la raison expliquee plus bas.

Telecharge son contenu au format CSV (`exportMimeType: text/csv`). Colonnes,
dans cet ordre :

```
Date détectée, Titre, Entreprise, Lieu, Score, Source, URL, Favori, Statut, Notes
```

Ajoute en fin de tableau une ligne par offre de cette execution ayant un
score de 50 ou plus :
- `Date détectée` : date du jour, AAAA-MM-JJ
- `Statut` : `À traiter`
- `Favori` et `Notes` : vides
- les autres colonnes depuis l'offre ; `Entreprise` vide si la source ne la
  fournit pas

Trois regles strictes :
- Ne modifie, ne reordonne et ne supprime **jamais** une ligne existante.
  Les colonnes `Favori`, `Statut` et `Notes` sont saisies a la main : elles
  doivent etre reportees a l'identique, sans exception.
- Si une offre est deja presente dans le tableau (meme URL), ne l'ajoute pas
  une seconde fois.
- Entoure de guillemets tout champ contenant une virgule, un guillemet ou un
  retour a la ligne.

Valeurs possibles en `Statut`, saisies par l'utilisateur : `À traiter`,
`Exclue`, `Postulée`, `Contacts en cours`, `Candidature rejetée`.

Pour ecrire le resultat : le connecteur Drive ne sait pas remplacer le
contenu d'un fichier existant. Mets donc l'ancien fichier a la corbeille
(`trash_file`), puis cree le nouveau avec le **meme titre** `Suivi
candidatures`, le meme dossier parent, `contentMimeType: text/csv` et sans
desactiver la conversion (pour qu'il redevienne un Google Sheet). Fais-le
dans cet ordre, et seulement une fois le contenu fusionne pret : le tableau
ne doit jamais se retrouver absent de Drive plus d'un instant.

**6. Depot sur Drive**

Envoie ce fichier sur Drive a l'emplacement
`Mon Drive/CLAUDE/OFFRES EMPLOI/out/synthese_AAAA-MM-JJ.md`.

Le fichier `state/vues.json` local a ete mis a jour une premiere fois par
l'appel FT puis une seconde fois par l'appel APEC (qui relit l'etat laisse
par FT avant d'ecrire le sien) : le contenu local apres les deux appels est
donc deja complet, pas besoin de le fusionner avec quoi que ce soit. Ecrase
directement avec ce fichier local le fichier
`Mon Drive/CLAUDE/OFFRES EMPLOI/state/vues.json` sur Drive.

Ne cree et ne conserve aucune copie des fichiers `data/candidats_*.json` sur
Drive : ce sont des fichiers de travail de cette seule execution, a ignorer
une fois la synthese ecrite.

**7. Notification**

Termine par un message court : nombre d'offres a traiter aujourd'hui, nombre
de lignes ajoutees au suivi, etat des deux sources, lien ou nom du fichier
synthese sur Drive. Si zero offre au-dessus de 50, dis-le, ne cree pas de
fichier synthese et n'ajoute aucune ligne au suivi (mais laisse le tableau
existant intact).
