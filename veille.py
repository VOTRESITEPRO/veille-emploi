#!/usr/bin/env python3
"""
Collecte des offres BA / PO sur Nantes depuis France Travail et l'APEC.

Le script ne juge pas les offres : il collecte, dedoublonne, applique des
filtres objectifs (contrat, departement, salaire plancher, titres exclus)
et ecrit un JSON. Le scoring et la redaction de la synthese sont faits
ensuite par Claude, qui lit ce JSON.

Usage :
    python veille.py                  # collecte du jour
    python veille.py --source ft      # une seule source
    python veille.py --no-state       # ignore l'historique (retest)
    python veille.py --verbose
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.yaml"
STATE_PATH = BASE / "state" / "vues.json"
DATA_DIR = BASE / "data"

FT_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
FT_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

# ATTENTION : l'APEC n'expose pas d'API publique documentee. L'URL ci-dessous
# correspond a l'endpoint interne utilise par le front. Elle peut changer sans
# preavis. Voir README, section "Adaptateur APEC".
APEC_SEARCH_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

VERBOSE = False


def log(*a):
    if VERBOSE:
        print("[veille]", *a, file=sys.stderr)


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def slug(txt):
    """Normalise une chaine pour comparaison : sans accent, sans ponctuation."""
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", str(txt))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return " ".join(txt.split())


def cle_dedoublon(offre):
    """
    Cle de rapprochement inter-sources. Une meme offre diffusee sur FT et
    l'APEC n'a pas le meme identifiant : on rapproche sur titre + entreprise.
    Les mots vides du titre sont retires pour absorber les variantes
    ("Product Owner H/F" vs "Product Owner (H/F) - Nantes").
    """
    stop = {"h", "f", "hf", "cdi", "nantes", "44", "poste", "de", "du", "la",
            "le", "les", "un", "une", "en", "sur", "et", "pour"}
    mots = [m for m in slug(offre.get("titre")).split() if m not in stop]
    entreprise = slug(offre.get("entreprise"))
    if not entreprise:
        # L'APEC ne renvoie pas le nom de l'entreprise dans les resultats de
        # recherche : sans repli, deux offres distinctes partageant un
        # intitule generique ("Product Owner F/H") fusionneraient a tort.
        entreprise = f"{offre.get('source')}:{offre.get('id_source')}"
    return f"{' '.join(sorted(mots))}|{entreprise}"


def charger_state(actif=True):
    if not actif or not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log(f"state illisible ({e}), on repart de zero")
        return {}


def ecrire_state(state):
    """Purge les entrees de plus de 90 jours pour eviter la croissance infinie."""
    limite = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    state = {k: v for k, v in state.items() if v.get("vu_le", "") >= limite}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                          encoding="utf-8")


# --------------------------------------------------------------------------
# Source 1 : France Travail (API officielle)
# --------------------------------------------------------------------------

def ft_token(client_id, client_secret):
    scope = f"api_offresdemploiv2 o2dsoffre application_{client_id}"
    r = requests.post(
        FT_TOKEN_URL,
        params={"realm": "/partenaire"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        timeout=20,
    )
    if r.status_code == 400:
        # Certaines applications n'acceptent pas le scope application_{id}
        log("scope complet refuse, nouvel essai en scope court")
        r = requests.post(
            FT_TOKEN_URL,
            params={"realm": "/partenaire"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
            timeout=20,
        )
    r.raise_for_status()
    return r.json()["access_token"]


def ft_salaire_annuel(libelle):
    """
    Extrait un salaire annuel approximatif depuis le libelle texte de FT
    ('Annuel de 45000.0 Euros a 55000.0 Euros sur 12 mois').
    Retourne (min, max) ou (None, None). Heuristique assumee.
    """
    if not libelle:
        return (None, None)
    nombres = [float(n) for n in re.findall(r"(\d[\d\s]*[\.,]?\d*)", libelle.replace(" ", ""))]
    nombres = [n for n in nombres if n > 1000]
    if not nombres:
        return (None, None)
    low = str(libelle).lower()
    facteur = 12 if "mensuel" in low else (1820 if "horaire" in low else 1)
    vals = sorted(n * facteur for n in nombres)
    return (vals[0], vals[-1])


def collecte_ft(cfg):
    cid = os.environ.get("FT_CLIENT_ID")
    csec = os.environ.get("FT_CLIENT_SECRET")
    if not cid or not csec:
        raise RuntimeError(
            "FT_CLIENT_ID / FT_CLIENT_SECRET absents de l'environnement. "
            "Voir README, section France Travail."
        )
    token = ft_token(cid, csec)
    req = cfg["requete"]
    depuis = (datetime.now(timezone.utc)
              - timedelta(days=req.get("anciennete_jours", 3)))

    resultats, vus_ids = [], set()
    for mot in req["mots_cles"]:
        params = {
            "motsCles": mot,
            "commune": req.get("commune_insee"),
            "distance": req.get("rayon_km", 30),
            "typeContrat": ",".join(req.get("types_contrat", ["CDI"])),
            "minCreationDate": depuis.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxCreationDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "range": "0-99",
            "sort": "1",
        }
        if req.get("codes_rome"):
            params["codeROME"] = ",".join(req["codes_rome"])

        r = requests.get(
            FT_SEARCH_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={k: v for k, v in params.items() if v is not None},
            timeout=30,
        )
        # 204 = aucun resultat, ce n'est pas une erreur
        if r.status_code == 204:
            log(f"FT '{mot}' : 0 resultat")
            continue
        r.raise_for_status()
        offres = r.json().get("resultats", [])
        log(f"FT '{mot}' : {len(offres)} resultats")

        for o in offres:
            if o.get("id") in vus_ids:
                continue
            vus_ids.add(o["id"])
            lieu = o.get("lieuTravail", {}) or {}
            smin, smax = ft_salaire_annuel((o.get("salaire") or {}).get("libelle"))
            resultats.append({
                "source": "france_travail",
                "id_source": o.get("id"),
                "titre": o.get("intitule"),
                "entreprise": (o.get("entreprise") or {}).get("nom"),
                "lieu": lieu.get("libelle"),
                "code_postal": lieu.get("codePostal"),
                "date_publication": o.get("dateCreation"),
                "type_contrat": o.get("typeContratLibelle"),
                "experience": o.get("experienceLibelle"),
                "qualification": o.get("qualificationLibelle"),
                "salaire_libelle": (o.get("salaire") or {}).get("libelle"),
                "salaire_min": smin,
                "salaire_max": smax,
                "teletravail": o.get("dureeTravailLibelleConverti"),
                "url": (o.get("origineOffre") or {}).get("urlOrigine"),
                "description": o.get("description"),
                "competences": [c.get("libelle") for c in (o.get("competences") or [])],
                "mot_cle_declencheur": mot,
            })
        time.sleep(0.6)
    return resultats


# --------------------------------------------------------------------------
# Source 2 : APEC (endpoint interne, non contractuel)
# --------------------------------------------------------------------------

def collecte_apec(cfg):
    req = cfg["requete"]
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": "https://www.apec.fr/candidat/recherche-emploi.html",
    })

    resultats, vus_ids = [], set()
    for mot in req["mots_cles"]:
        payload = {
            "lieux": [str(req.get("departement", "44"))],
            "fonctions": [],
            "motsCles": mot,
            "typesContrat": ["101888"],   # CDI
            "sorts": [{"type": "SCORE", "direction": "DESCENDING"}],
            "pagination": {"range": 50, "startIndex": 0},
            "activeFiltre": True,
        }
        try:
            r = session.post(APEC_SEARCH_URL, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[APEC] echec sur '{mot}' : {e}", file=sys.stderr)
            print("[APEC] l'endpoint interne a probablement change. "
                  "Voir README, section 'Adaptateur APEC'.", file=sys.stderr)
            return resultats

        offres = data.get("resultats", []) or data.get("resultatRecherche", [])
        log(f"APEC '{mot}' : {len(offres)} resultats")

        for o in offres:
            oid = o.get("numeroOffre") or o.get("id")
            if not oid or oid in vus_ids:
                continue
            vus_ids.add(oid)
            resultats.append({
                "source": "apec",
                "id_source": str(oid),
                "titre": o.get("intitule") or o.get("intituleOffre"),
                "entreprise": o.get("nomCommercialEtablissement") or o.get("entreprise"),
                "lieu": o.get("lieuTexte") or o.get("lieu"),
                "code_postal": None,
                "date_publication": o.get("datePublication"),
                "type_contrat": o.get("libelleTypeContrat"),
                "experience": o.get("libelleNiveauExperience"),
                "qualification": "Cadre",
                "salaire_libelle": o.get("salaireTexte"),
                "salaire_min": o.get("salaireMin"),
                "salaire_max": o.get("salaireMax"),
                "teletravail": o.get("libelleTeletravail"),
                "url": f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{oid}",
                "description": o.get("texteOffre") or o.get("descriptifMission"),
                "competences": [],
                "mot_cle_declencheur": mot,
            })
        time.sleep(1.2)
    return resultats


# --------------------------------------------------------------------------
# Filtres durs
# --------------------------------------------------------------------------

def annees_experience(libelle):
    """Extrait le nombre d'annees exigees depuis un libelle texte."""
    if not libelle:
        return None
    m = re.search(r"(\d+)\s*[Aa]n", str(libelle))
    return int(m.group(1)) if m else None


def commune_proche(lieu, communes_slug):
    """
    Vrai si le champ lieu (ex. 'Ancenis-Saint-Gereon   - 44', '44000 - NANTES')
    contient une des communes acceptees. Sans lieu exploitable, on ne rejette
    pas : l'absence de donnee ne doit pas valoir rejet (meme principe que le
    filtre salaire).
    """
    if not lieu:
        return True
    texte = slug(re.sub(r"\d+", " ", str(lieu)))
    return any(c in texte for c in communes_slug)


def filtrer(offres, cfg):
    """Retourne (retenues, rejetees) ; chaque rejet porte son motif."""
    f = cfg["filtres_durs"]
    motifs = [re.compile(p, re.IGNORECASE) for p in f.get("titre_exclu", [])]
    plancher = f.get("salaire_min_annuel")
    exp_max = f.get("experience_max_exigee")
    dept = str(cfg["requete"].get("departement", "44"))
    communes_slug = [slug(c) for c in cfg["requete"].get("communes_proches", [])]

    retenues, rejetees = [], []
    for o in offres:
        motif = None
        titre = o.get("titre") or ""

        for rx in motifs:
            if rx.search(titre):
                motif = f"titre exclu ({rx.pattern})"
                break

        if not motif and o.get("code_postal"):
            if not str(o["code_postal"]).startswith(dept):
                motif = f"hors departement {dept} ({o['code_postal']})"

        if not motif and communes_slug and not commune_proche(o.get("lieu"), communes_slug):
            motif = f"hors zone geographique ({o.get('lieu')})"

        if not motif and plancher and o.get("salaire_max"):
            if o["salaire_max"] < plancher:
                motif = f"salaire max {int(o['salaire_max'])} < {plancher}"

        if not motif and exp_max:
            n = annees_experience(o.get("experience"))
            if n and n > exp_max:
                motif = f"experience exigee {n} ans > {exp_max}"

        if motif:
            o["motif_rejet"] = motif
            rejetees.append(o)
        else:
            retenues.append(o)
    return retenues, rejetees


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["ft", "apec", "all"], default="all")
    ap.add_argument("--no-state", action="store_true",
                    help="ignore l'historique et ressort toutes les offres")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    brut, erreurs = [], []

    if args.source in ("ft", "all"):
        try:
            brut += collecte_ft(cfg)
        except Exception as e:
            erreurs.append(f"france_travail : {e}")
            print(f"[ERREUR] France Travail : {e}", file=sys.stderr)

    if args.source in ("apec", "all"):
        try:
            brut += collecte_apec(cfg)
        except Exception as e:
            erreurs.append(f"apec : {e}")
            print(f"[ERREUR] APEC : {e}", file=sys.stderr)

    # Dedoublonnage inter-sources : FT prime (description plus complete)
    par_cle = {}
    for o in brut:
        k = cle_dedoublon(o)
        if k not in par_cle:
            par_cle[k] = o
        else:
            existant = par_cle[k]
            existant.setdefault("aussi_sur", []).append(o["source"])
            if o["source"] == "france_travail" and existant["source"] != "france_travail":
                o["aussi_sur"] = existant.get("aussi_sur", [])
                par_cle[k] = o
    dedoublonnees = list(par_cle.values())

    # Historique : ne ressortir que ce qui n'a pas deja ete presente
    state = charger_state(actif=not args.no_state)
    maintenant = datetime.now(timezone.utc).isoformat()
    nouvelles = []
    for o in dedoublonnees:
        k = cle_dedoublon(o)
        if k in state:
            continue
        nouvelles.append(o)
        state[k] = {"vu_le": maintenant, "titre": o.get("titre"),
                    "entreprise": o.get("entreprise"), "url": o.get("url")}

    retenues, rejetees = filtrer(nouvelles, cfg)

    sortie = {
        "genere_le": maintenant,
        "erreurs": erreurs,
        "stats": {
            "brut": len(brut),
            "apres_dedoublon": len(dedoublonnees),
            "nouvelles": len(nouvelles),
            "retenues": len(retenues),
            "rejetees": len(rejetees),
        },
        "offres": retenues,
        "rejetees": [{"titre": o.get("titre"), "entreprise": o.get("entreprise"),
                      "motif": o["motif_rejet"]} for o in rejetees],
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    jour = datetime.now().strftime("%Y-%m-%d")
    chemin = DATA_DIR / f"candidats_{jour}.json"
    chemin.write_text(json.dumps(sortie, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    if not args.no_state:
        ecrire_state(state)

    print(json.dumps(sortie["stats"], ensure_ascii=False))
    print(str(chemin))

    # Echec total des deux sources : code de sortie non nul
    if len(erreurs) >= (2 if args.source == "all" else 1):
        sys.exit(1)


if __name__ == "__main__":
    main()
