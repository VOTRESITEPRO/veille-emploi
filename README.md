Veille offres PO / Chef de projet - Nantes
Collecte quotidienne des offres sur deux sources (France Travail, APEC),
dedoublonnage, filtrage objectif, puis scoring et synthese par Claude.
Repartition assumee : Python collecte et filtre sur des criteres binaires.
Claude juge le contenu. Aucun scoring par mots-cles dans le script, il
produirait du bruit.
Persistance : via git. La routine committe et pousse elle-meme
`out/synthese_AAAA-MM-JJ.md` et `state/vues.json` a chaque execution.
Pas de service externe (pas de Google Drive, pas de compte de service).
Arborescence

```
veille-emploi/
  veille.py            collecte + dedoublonnage + filtres durs
  config.yaml           requete, filtres, grille de scoring, profil
  PROMPT_ROUTINE.md      prompt a coller dans la routine
  artifact/pipeline.html source de la page de suivi (voir plus bas)
  state/vues.json        historique 30 jours (dedoublonnage inter-jours),
                          commite par la routine
  data/                  JSON de collecte, un par jour, jamais commite
                          (fichiers de travail, purges par execution)
  out/                   syntheses markdown, commitees par la routine

```

Le suivi des candidatures, lui, ne vit pas dans le depot : c'est un
Artifact (voir plus bas).
Pipeline de candidatures
La synthese quotidienne est une photo : elle ne montre que les offres
parues ce jour-la. Le pipeline est la memoire du systeme — chaque offre a
50 ou plus y est ajoutee une fois, et n'en sort jamais. C'est la qu'on
retrouve une offre reperee la semaine derniere.
URL fixe, qui ne change jamais :
https://claude.ai/code/artifact/f10d0942-3cf4-4501-a313-f0589d326fd5
Source de la page : `artifact/pipeline.html`.
Trois champs se modifient a la main, directement dans la page :

* Favori : l'etoile, independante du statut
* Statut : `À traiter` (pose a l'ajout), `Postulée`, `Contacts en cours`, `Candidature rejetée`, `Exclue`
* Notes : texte libre

Comment la persistance fonctionne
La page declare la capacite `artifact` : son etat vit dans un ilot JSON
(`<script type="application/json" id="state">`) a l'interieur du document,
et chaque modification republie le document entier a la meme URL. La
recherche et les filtres, eux, ne sont pas persistes — ils restent propres
a la session de lecture.
La routine ne reecrit jamais la page : elle lit la version en ligne,
remplace le seul contenu de l'ilot JSON par l'etat fusionne, et republie
sur la meme URL. C'est ce qui garantit que les statuts saisis a la main
survivent a chaque execution.
Deux consequences a connaitre :

* Ne jamais recreer l'artifact. Un artifact recree a une URL neuve et
perd tout l'historique. En cas d'echec de lecture ou de republication, la
routine doit signaler l'erreur et ne rien faire d'autre.
* Si la page est ouverte pendant que la routine republie, la vue se
recharge sur la version de la routine. Une modification en cours de
saisie a cet instant precis peut etre perdue : la routine tournant a 7h,
le risque est theorique.

Installation

```bash
pip install requests pyyaml

```

1. Credentials France Travail
C'est la seule etape qui demande du temps, environ 15 minutes.

1. Compte sur https://francetravail.io
2. Creer une application dans l'espace developpeur
3. Souscrire a l'API Offres d'emploi v2
4. Recuperer client_id et client_secret

Exposer les deux valeurs dans l'environnement du shell qui lance la routine :

```bash
export FT_CLIENT_ID="..."
export FT_CLIENT_SECRET="..."

```

Ne pas les mettre dans `config.yaml` : ce fichier a vocation a etre modifie
souvent et potentiellement versionne.
Details techniques verifies :

* token : `https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire`
* recherche : `https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search`
* scope : `api_offresdemploiv2 o2dsoffre` (le script tente d'abord avec
`application_{client_id}` en plus, puis se rabat en cas de 400)

Un HTTP 204 signifie zero resultat, pas une erreur. Le script le gere.
2. Adaptateur APEC
Point de fragilite assume. L'APEC n'expose pas d'API publique
documentee. Le script cible l'endpoint interne du front :

```
POST https://www.apec.fr/cms/webservices/rechercheOffre

```

Je n'ai pas pu verifier ni la structure exacte du payload, ni les
identifiants de filtres (`typesContrat`), ni le nom des champs de reponse.
Ce que contient `collecte_apec()` est une hypothese construite sur la
forme habituelle de cet endpoint.
Verifie le 22/08/2026 : le payload envoyait aussi un filtre
`typesConvention` (codes de convention collective devines, non
documentes). Il excluait silencieusement des offres CDI legitimes —
confirme en comparant les resultats avec et sans ce filtre sur une
recherche "product owner" (22 offres avec le filtre, 31 sans, dont des
offres Product Owner reelles absentes a tort). Le filtre a ete retire ;
seul `typesContrat` (CDI) reste applique.
Premiere execution : lance `python veille.py --source apec --verbose`.

* Si des offres remontent : rien a faire.
* Si le script signale un echec : ouvre les DevTools sur une recherche APEC
reelle, onglet Network, copie la requete XHR de recherche, et donne-la moi.
Corriger l'adaptateur prend cinq minutes une fois la requete connue.

Le script traite l'echec APEC sans planter : la collecte France Travail se
poursuit et l'erreur est remontee dans le champ `erreurs` du JSON, que la
routine doit afficher en tete de synthese.
Prevoir que cet endpoint casse une a deux fois par an.
3. Routine
Claude Code Desktop, sidebar Routines, New routine, type Local.
Dossier : `C:\Users\letra\dev\OFFRES EMPLOI` (deplace hors de tout dossier
synchronise par Google Drive, pour eviter tout conflit entre git et un
client de synchronisation cloud). Frequence : jours ouvres, 7h00.
Prompt : le contenu de `PROMPT_ROUTINE.md`.
Le toggle worktree n'est pas utile ici : la routine ne modifie pas de code
source, elle ecrit dans `out/` et `state/`, puis committe.
A verifier avant de faire confiance a la routine : qu'elle dispose bien
des droits de push sur le depot, pas seulement de lecture/clone. Un echec
de `git push` est gere sans planter (voir `PROMPT_ROUTINE.md`, etape 6),
mais autant le confirmer par un test avant de compter dessus.
Limite connue de ce type (Local) : contrairement a une routine Cloud,
une tache planifiee locale respecte les regles de permission du projet et
peut redemander une autorisation manuelle a chaque execution (commandes
bash, ecritures de fichiers, git push). Migration vers une routine Cloud
envisagee pour supprimer ce besoin — non encore faite.
4. Reglage
La grille de `config.yaml` est un point de depart, pas un reglage valide.
Elle produira des faux positifs et des faux negatifs la premiere semaine.
Deux arbitrages a surveiller :
Le filtre `scrum master` dans `titre_exclu` ecarte aussi les offres
"Product Owner / Scrum Master", qui sont frequentes en PME et pas toujours
sans interet. Si tu constates des rejets injustifies, retire ce motif et
laisse la penalite de scoring faire le tri.
Le plancher `salaire_min_annuel: 45000` ne s'applique qu'aux offres
avec salaire annonce, soit une minorite. Il ne filtrera pas grand-chose.
Methode de calibrage : pendant une semaine, lance aussi
`python veille.py --no-state` en fin de journee et parcours la section
`rejetees` du JSON. Chaque rejet que tu juges injustifie est un motif a
retirer de `titre_exclu`.
Mise a jour des fichiers locaux
Le depot git est clone dans un dossier separe, non synchronise par
Google Drive : `C:\Users\letra\dev\OFFRES EMPLOI`.

```bash
cd "C:\Users\letra\dev\OFFRES EMPLOI"
git add .
git commit -m "description de ce que vous avez change"
git push

```

Attention : depuis que la routine committe elle-meme `out/` et
`state/vues.json` (voir plus haut), fais un `git pull` avant toute
modification manuelle pour eviter un conflit avec ce que la routine a
pousse ce matin-la.
Limites connues

* Couverture. France Travail et APEC ne couvrent pas tout. HelloWork
publie des offres en exclusivite, notamment des PME regionales — ajout en
cours d'evaluation, pas encore integre au script.
* Le dedoublonnage inter-sources repose sur titre + entreprise
normalises. Une meme offre publiee sous deux intitules differents passera
deux fois. Une offre publiee par une ESN sans nom d'entreprise ne se
dedoublonnera pas correctement.
* L'extraction de salaire France Travail est heuristique : elle parse un
libelle texte libre. Verifier avant de se fier a un chiffre.
* L'historique 30 jours empeche de revoir une offre deja presentee, meme
si elle a ete republiee avec une description enrichie. Supprimer
`state/vues.json` remet le compteur a zero.
* Consommation. Chaque execution de la routine consomme des tokens comme
une session normale. Lire une trentaine de descriptions completes chaque
matin n'est pas gratuit.
* Historique git. Un commit par jour ouvre, contenant la synthese et
l'etat de dedoublonnage. Sur plusieurs mois, ca alourdit l'historique du
depot sans beneficier au code lui-meme — a surveiller, un squash
periodique des commits de routine reste possible si ca devient genant.
