# Prompt de la routine quotidienne

Coller ce texte dans le champ prompt de la routine Claude Code Desktop.
Frequence : jours ouvres, 7h00. Dossier de travail : celui de ce projet.

---

Execute la veille d'offres d'emploi.

**1. Collecte**

Lance `python veille.py` depuis le dossier du projet. Le script ecrit
`data/candidats_AAAA-MM-JJ.json` et affiche ses statistiques.

Si le script sort en erreur ou si le champ `erreurs` du JSON n'est pas vide :
ecris quand meme la synthese avec ce qui a ete collecte, et place en tete un
bloc **PANNE** nommant la source tombee et le message d'erreur. Ne masque
jamais une source en echec : une synthese vide parce que l'APEC a change son
endpoint ne doit pas ressembler a une journee sans offre.

**2. Scoring**

Lis `config.yaml`, sections `scoring` et `profil`. Pour chaque offre du
tableau `offres`, attribue un score sur 100 selon les cinq axes de la grille.
La description complete de l'offre est dans le champ `description` : lis-la,
ne te contente pas du titre.

Regles :
- Les paliers `adequation_role`, `proximite_metier` et `socle_technique` sont
  exclusifs : un seul palier par axe, celui qui correspond le mieux.
- `conditions` est cumulatif, plafonne a 20.
- `signaux_negatifs` se soustrait, sans plancher.
- N'invente pas d'information absente de l'offre. Une donnee non mentionnee
  vaut 0 sur son critere, jamais le benefice du doute. Si le salaire n'est pas
  annonce, ce n'est pas un signal positif ni negatif : c'est une inconnue a
  signaler.
- Si la description est trop pauvre pour scorer (moins de 400 caracteres,
  cas frequent sur les annonces d'ESN), marque l'offre **A VERIFIER** au lieu
  de lui attribuer un score fictif, et donne l'URL.

**3. Synthese**

Ecris `out/synthese_AAAA-MM-JJ.md`, structure ainsi :

- Ligne d'entete : date, nombre d'offres collectees, retenues, rejetees,
  et l'etat de chaque source (OK ou en panne).
- **A traiter aujourd'hui** : offres a 70 et plus. Pour chacune : titre,
  entreprise, lieu, score, URL, le detail des points par axe en une ligne,
  puis deux a quatre lignes sur l'angle de candidature (ce qui accroche dans
  mon profil, ce qui manque, quel materiau adapter). C'est la seule section
  ou tu developpes.
- **A regarder** : offres entre 50 et 69. Une ligne chacune : titre,
  entreprise, score, URL, et le motif principal de la decote.
- **A verifier** : offres non scorables. Titre, entreprise, URL.
- **Ecartees** : uniquement le decompte par motif, pas la liste. Sauf si une
  offre a ete rejetee par le filtre titre alors qu'elle semblait pertinente,
  auquel cas signale-la pour que j'ajuste `config.yaml`.

Contraintes de redaction : direct, factuel, pas d'introduction ni de
conclusion, tirets simples uniquement. Ne me vends pas les offres, evalue-les.
Si aucune offre n'atteint 50, dis-le en une ligne, ne remplis pas la synthese
avec les offres a 30.

**4. Notification**

Termine par un message court : nombre d'offres a traiter aujourd'hui et le
chemin du fichier. Si zero offre au-dessus de 50, dis-le et n'ecris pas de
fichier.
