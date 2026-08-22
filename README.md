# Veille offres BA / PO - Nantes

Collecte quotidienne des offres sur deux sources (France Travail, APEC),
dedoublonnage, filtrage objectif, puis scoring et synthese par Claude.

Repartition assumee : Python collecte et filtre sur des criteres binaires.
Claude juge le contenu. Aucun scoring par mots-cles dans le script, il
produirait du bruit.

## Arborescence

```
veille-emploi/
  veille.py            collecte + dedoublonnage + filtres durs
  config.yaml          requete, filtres, grille de scoring, profil
  PROMPT_ROUTINE.md    prompt a coller dans la routine
  state/vues.json      historique 90 jours (dedoublonnage inter-jours)
  data/                JSON de collecte, un par jour
  out/                 syntheses markdown
```

## Installation

```bash
pip install requests pyyaml
```

## 1. Credentials France Travail

C'est la seule etape qui demande du temps, environ 15 minutes.

1. Compte sur https://francetravail.io
2. Creer une application dans l'espace developpeur
3. Souscrire a l'API **Offres d'emploi v2**
4. Recuperer client_id et client_secret

Exposer les deux valeurs dans l'environnement du shell qui lance la routine :

```bash
export FT_CLIENT_ID="..."
export FT_CLIENT_SECRET="..."
```

Ne pas les mettre dans `config.yaml` : ce fichier a vocation a etre modifie
souvent et potentiellement versionne.

Details techniques verifies :
- token : `https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire`
- recherche : `https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search`
- scope : `api_offresdemploiv2 o2dsoffre` (le script tente d'abord avec
  `application_{client_id}` en plus, puis se rabat en cas de 400)

Un HTTP 204 signifie zero resultat, pas une erreur. Le script le gere.

## 2. Adaptateur APEC

**Point de fragilite assume.** L'APEC n'expose pas d'API publique
documentee. Le script cible l'endpoint interne du front :

```
POST https://www.apec.fr/cms/webservices/rechercheOffre
```

Je n'ai pas pu verifier ni la structure exacte du payload, ni les
identifiants de filtres (`typesContrat`, `typesConvention`), ni le nom des
champs de reponse. Ce que contient `collecte_apec()` est une hypothese
construite sur la forme habituelle de cet endpoint.

Premiere execution : lance `python veille.py --source apec --verbose`.

- Si des offres remontent : rien a faire.
- Si le script signale un echec : ouvre les DevTools sur une recherche APEC
  reelle, onglet Network, copie la requete XHR de recherche, et donne-la moi.
  Corriger l'adaptateur prend cinq minutes une fois la requete connue.

Le script traite l'echec APEC sans planter : la collecte France Travail se
poursuit et l'erreur est remontee dans le champ `erreurs` du JSON, que la
routine doit afficher en tete de synthese.

Prevoir que cet endpoint casse une a deux fois par an.

## 3. Routine

Claude Code Desktop, sidebar **Routines**, **New routine**, type **Local**.
Dossier : celui de ce projet, a approuver. Frequence : jours ouvres, 7h00.
Prompt : le contenu de `PROMPT_ROUTINE.md`.

Le toggle worktree n'est pas utile ici : la routine ne modifie pas de code,
elle ecrit dans `data/` et `out/`.

## 4. Reglage

La grille de `config.yaml` est un point de depart, pas un reglage valide.
Elle produira des faux positifs et des faux negatifs la premiere semaine.

Deux arbitrages a surveiller :

**Le filtre `scrum master` dans `titre_exclu`** ecarte aussi les offres
"Product Owner / Scrum Master", qui sont frequentes en PME et pas toujours
sans interet. Si tu constates des rejets injustifies, retire ce motif et
laisse la penalite de scoring faire le tri.

**Le plancher `salaire_min_annuel: 40000`** ne s'applique qu'aux offres
avec salaire annonce, soit une minorite. Il ne filtrera pas grand-chose.

Methode de calibrage : pendant une semaine, lance aussi
`python veille.py --no-state` en fin de journee et parcours la section
`rejetees` du JSON. Chaque rejet que tu juges injustifie est un motif a
retirer de `titre_exclu`.

## Limites connues

- **Couverture.** France Travail et APEC ne couvrent pas tout. HelloWork
  publie des offres en exclusivite, notamment des PME regionales. A mesurer
  apres deux semaines avant de decider d'ajouter la source.
- **Le dedoublonnage inter-sources** repose sur titre + entreprise
  normalises. Une meme offre publiee sous deux intitules differents passera
  deux fois. Une offre publiee par une ESN sans nom d'entreprise ne se
  dedoublonnera pas correctement.
- **L'extraction de salaire France Travail** est heuristique : elle parse un
  libelle texte libre. Verifier avant de se fier a un chiffre.
- **L'historique 90 jours** empeche de revoir une offre deja presentee, meme
  si elle a ete republiee avec une description enrichie. Supprimer
  `state/vues.json` remet le compteur a zero.
- **Consommation.** Chaque execution de la routine consomme des tokens comme
  une session normale. Lire une trentaine de descriptions completes chaque
  matin n'est pas gratuit.
