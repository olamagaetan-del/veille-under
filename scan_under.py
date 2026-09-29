"""Veille UNDER live — scan des matchs de foot en cours (LiveScore) et calcul des probabilités.

Sortie : JSON sur stdout {"candidats": [...], "nb_live": N}
Un candidat = match en live où une ligne Under a une probabilité "sans perte" >= SEUIL
et qui n'a pas déjà été alerté (fichier alertes.json, remis à zéro chaque jour).
"""
import json, math, re, sys, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ICI = Path(__file__).parent
ETAT = ICI / "alertes.json"
SEUIL = 0.85          # probabilité minimale sans perte
PLAFOND = 0.97        # au-delà, cote trop basse pour avoir de la valeur
MIN_MIN, MAX_MIN = 15, 75   # fenêtre de minutes exploitable

# Buts / 90 min par défaut, et compétitions réputées fermées
TAUX_DEFAUT = 2.65
FERMEES = [
    "primera nacional", "primera b", "federal a", "segunda", "laliga 2", "serie b",
    "ligue 2", "national", "azadegan", "africa cup of nations qualification",
    "botola", "egypt", "algeria", "tunisia", "greece", "super league 2", "iran",
    "morocco",
]
TAUX_FERME = 2.15


def taux_base(comp: str) -> float:
    c = comp.lower()
    for mot in FERMEES:
        if mot in c:
            return TAUX_FERME
    return TAUX_DEFAUT


def poisson_cdf(k: int, lam: float) -> float:
    if k < 0:
        return 0.0
    return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


def minute(eps: str):
    """'57'' -> 57 ; '45+2'' -> 45 ; 'HT' -> 45 ; sinon None (NS, FT, etc.)."""
    if eps == "HT":
        return 45
    m = re.match(r"^(\d+)(?:\+\d+)?'$", eps or "")
    return int(m.group(1)) if m else None


def lignes(buts: int, lam: float):
    """Probabilités pour chaque ligne Under pertinente. Renvoie liste de dicts."""
    res = []
    for L in (1.5, 2.5, 3.0, 3.5, 4.5):
        if L == 3.0:
            reste_gagne = 2 - buts          # 0..2 buts = gagné
            reste_perd = 4 - buts           # >=4 = perdu, 3 = remboursé
            if reste_perd <= 0:
                continue
            p_gagne = poisson_cdf(reste_gagne, lam)
            p_sans_perte = poisson_cdf(reste_perd - 1, lam)
        else:
            marge = math.floor(L) - buts    # buts supplémentaires tolérés
            if marge < 0:
                continue
            p_gagne = p_sans_perte = poisson_cdf(marge, lam)
        res.append({"ligne": f"Under {L}", "p_gagne": round(p_gagne, 3),
                    "p_sans_perte": round(p_sans_perte, 3)})
    return res


def charger_etat(jour: str):
    try:
        e = json.loads(ETAT.read_text(encoding="utf-8"))
        if e.get("jour") == jour:
            return e
    except Exception:
        pass
    return {"jour": jour, "alertes": []}


def dans_fenetre(maintenant: datetime):
    """Lit plan_actif.json (écrit par plan_jour.py). Sans plan valide, on scanne quand même."""
    try:
        plan = json.loads((ICI / "plan_actif.json").read_text(encoding="utf-8"))
        creneaux = [(datetime.fromisoformat(d), datetime.fromisoformat(f))
                    for d, f in plan["creneaux"]]
    except Exception:
        return True, None
    if maintenant > creneaux[-1][1] + timedelta(hours=12):  # plan périmé (planificateur non lancé)
        return True, None
    return any(d <= maintenant <= f for d, f in creneaux), plan


def recuperer(jour: str):
    decalage = int(datetime.now().astimezone().utcoffset().total_seconds() // 3600)
    url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{jour}/{decalage}?MD=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    maintenant = datetime.now()
    ok_fenetre, plan = dans_fenetre(maintenant)
    if not ok_fenetre:
        print(json.dumps({"hors_fenetre": True, "heure": maintenant.strftime("%H:%M"),
                          "fenetre": f'{plan["debut_scan"]} -> {plan["fin_scan"]}'}))
        return
    jours = [maintenant.strftime("%Y%m%d")]
    if maintenant.hour < 6:  # matchs de la veille encore en cours après minuit
        jours.insert(0, (maintenant - timedelta(days=1)).strftime("%Y%m%d"))
    etat = charger_etat(maintenant.strftime("%Y%m%d"))
    deja = set(etat["alertes"])

    candidats, nb_live, vus = [], 0, set()
    for jour in jours:
        try:
            data = recuperer(jour)
        except Exception as ex:
            print(json.dumps({"erreur": str(ex)}))
            return
        for st in data.get("Stages", []):
            comp = f'{st.get("Cnm", "")} — {st.get("Snm", "")}'
            for ev in st.get("Events", []):
                eid = ev.get("Eid")
                if eid in vus:
                    continue
                vus.add(eid)
                mn = minute(ev.get("Eps", ""))
                if mn is None:
                    continue
                nb_live += 1
                if not (MIN_MIN <= mn <= MAX_MIN):
                    continue
                try:
                    b1, b2 = int(ev.get("Tr1", 0)), int(ev.get("Tr2", 0))
                except ValueError:
                    continue
                buts = b1 + b2
                base = taux_base(comp)
                # rythme observé : si le match marque plus que prévu, on relève le taux
                rythme = buts / max(mn, 1) * 90
                taux = max(base, 0.6 * base + 0.4 * rythme)
                restant = max(90 - mn, 0) + 4  # + temps additionnel moyen
                lam = taux * restant / 90
                ok = [l for l in lignes(buts, lam) if SEUIL <= l["p_sans_perte"] <= PLAFOND]
                if not ok:
                    continue
                meilleure = ok[0]  # la ligne la plus basse qui passe le seuil = meilleure cote
                cle = f'{eid}|{meilleure["ligne"]}'
                if cle in deja:
                    continue
                candidats.append({
                    "cle": cle,
                    "competition": comp,
                    "match": f'{ev["T1"][0]["Nm"]} vs {ev["T2"][0]["Nm"]}',
                    "minute": ev.get("Eps"),
                    "score": f"{b1}-{b2}",
                    "buts_attendus_restants": round(lam, 2),
                    "ligne": meilleure["ligne"],
                    "p_gagne": meilleure["p_gagne"],
                    "p_sans_perte": meilleure["p_sans_perte"],
                    "autres_lignes": ok[1:],
                })

    print(json.dumps({"heure": maintenant.strftime("%H:%M"), "nb_live": nb_live,
                      "candidats": candidats}, ensure_ascii=False, indent=1))


def marquer(cles):
    """python scan_under.py --marquer cle1 cle2 ... : enregistre les alertes envoyées."""
    jour = datetime.now().strftime("%Y%m%d")
    etat = charger_etat(jour)
    etat["alertes"] = sorted(set(etat["alertes"]) | set(cles))
    ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cles)} alerte(s) enregistrée(s)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "--marquer":
        marquer(sys.argv[2:])
    else:
        main()
