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
- **A traiter aujourd'hui** : offres a 70 et plus, triees par score
  decroissant. Titre, entreprise, lieu, score, URL, detail des points par
  axe en une ligne, puis deux a quatre lignes sur l'angle de candidature.
  Pour une offre APEC, ajoute une mention courte "score base sur extrait,
  verifier la fiche complete avant de candidater". Seule section developpee.
- **A regarder** : offres entre 50 et 69, triees par score decroissant.
  Une ligne chacune : titre, entreprise, score, URL, motif principal de la
  decote.
- **A verifier** : offres non scorables. Titre, entreprise, URL.
- **Ecartees** : uniquement le decompte par motif de rejet des filtres durs.
  Si une offre semblait pertinente et a ete rejetee par un filtre titre,
  signale-la a part pour ajustement de `config.yaml`.

Contraintes de redaction : direct, factuel, pas d'introduction ni de
conclusion, tirets simples uniquement. Si aucune offre n'atteint 50, dis-le
en une ligne courte plutot que de remplir la synthese avec du bruit.

**5. Mise a jour du pipeline de candidatures**

Le pipeline est un Artifact a URL fixe, qui ne change jamais :

```
https://claude.ai/code/artifact/f10d0942-3cf4-4501-a313-f0589d326fd5
```

C'est la liste cumulative de toutes les offres retenues depuis le debut, et
la memoire du systeme : une offre y entre une fois et n'en sort jamais.
L'utilisateur y modifie a la main le statut, le favori et les notes,
directement dans la page — ces saisies sont la valeur du fichier, ne les
perds sous aucun pretexte.

Marche a suivre, dans cet ordre :

1. Lis l'artifact avec l'outil Artifact, `action: "read"` et ce `url`. Tu
   recois le HTML complet de la version en ligne.
2. Dans ce HTML, reperes le **premier** bloc
   `<script type="application/json" id="state">` et son contenu jusqu'au
   premier `</script>` qui suit. C'est l'etat. Attention : la chaine
   `id="state"` apparait une seconde fois plus bas, dans le code de la page
   — ne prends jamais celle-la, seulement la premiere.
3. Parse ce JSON. Forme : `{"maj": "AAAA-MM-JJ", "offres": [...]}`, chaque
   offre ayant les cles `url`, `date`, `titre`, `entreprise`, `lieu`,
   `score`, `source`, `favori`, `statut`, `notes`.
4. Ajoute a la fin du tableau `offres` une entree par offre de cette
   execution atteignant 50 points, avec `date` = date du jour, `favori`:
   `false`, `statut`: `"À traiter"`, `notes`: `""`, `entreprise`: `""` si la
   source ne la fournit pas. Mets `maj` a la date du jour.
5. **N'altere aucune entree existante** : ni son ordre, ni ses champs, et
   surtout pas `favori`, `statut` et `notes`. Si une offre est deja presente
   (meme `url`), ne l'ajoute pas une seconde fois.
6. Ecris dans un fichier local le HTML lu a l'etape 1, en ayant remplace le
   seul contenu de cet ilot JSON par le nouvel etat serialise, avec les `</`
   echappes en `<\/`. Tout le reste du document doit rester identique au
   caractere pres.
7. Republie ce fichier avec l'outil Artifact en passant le meme `url`.
   Ne passe ni `capabilities` ni `contract` : les omettre conserve la
   declaration existante de la page, la reecrire risquerait de la casser.

Si la lecture ou la republication echoue, ne recree **jamais** un artifact
neuf : signale l'echec dans la notification finale et laisse l'existant en
place. Un artifact recree aurait une nouvelle URL et perdrait tout
l'historique de suivi.

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
