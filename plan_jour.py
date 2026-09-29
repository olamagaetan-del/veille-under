"""Plan des matchs de la journée (06h00 -> 06h00 le lendemain, heure locale).

Écrit plan_actif.json (fenêtre de scan utilisée par scan_under.py) et plans/plan_AAAAMMJJ.md,
puis affiche un résumé JSON : premier/dernier coup d'envoi, fenêtre de scan, expression cron,
nombre de matchs par heure et compétitions principales.
"""
import json, sys, urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ICI = Path(__file__).parent
DUREE_MATCH = timedelta(hours=2)   # coup d'envoi + ~2 h = fin du match
DEBUT_JOURNEE = 6                  # une journée va de 06h00 à 06h00


def decalage_utc() -> int:
    off = datetime.now().astimezone().utcoffset()
    return int(off.total_seconds() // 3600)


def recuperer(jour: str):
    url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{jour}/{decalage_utc()}?MD=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fusionner(matchs, maintenant):
    """Créneaux où au moins un match est en cours : union des intervalles [ko, ko + 2 h]."""
    creneaux = []
    for m in matchs:
        d, f = m["ko"], m["ko"] + DUREE_MATCH
        if f <= maintenant:
            continue
        d = max(d, maintenant.replace(second=0, microsecond=0))
        if creneaux and d <= creneaux[-1][1]:
            creneaux[-1][1] = max(creneaux[-1][1], f)
        else:
            creneaux.append([d, f])
    return creneaux


def heures_cron(creneaux) -> str:
    """Heures (0-23) touchées par les créneaux, compressées en plages cron."""
    heures = set()
    for d, f in creneaux:
        h = d.replace(minute=0, second=0, microsecond=0)
        while h < f:
            heures.add(h.hour)
            h += timedelta(hours=1)
    heures = sorted(heures)
    if not heures:
        return ""
    plages, i = [], 0
    while i < len(heures):
        j = i
        while j + 1 < len(heures) and heures[j + 1] == heures[j] + 1:
            j += 1
        plages.append(str(heures[i]) if i == j else f"{heures[i]}-{heures[j]}")
        i = j + 1
    return f"*/3 {','.join(plages)} * * *"


def main():
    maintenant = datetime.now()
    jour0 = maintenant.replace(hour=DEBUT_JOURNEE, minute=0, second=0, microsecond=0)
    if maintenant.hour < DEBUT_JOURNEE:
        jour0 -= timedelta(days=1)
    jour1 = jour0 + timedelta(days=1)

    matchs = []
    for d in (jour0, jour1):
        data = recuperer(d.strftime("%Y%m%d"))
        for st in data.get("Stages", []):
            comp = f'{st.get("Cnm", "")} — {st.get("Snm", "")}'
            for ev in st.get("Events", []):
                try:
                    ko = datetime.strptime(str(ev["Esd"]), "%Y%m%d%H%M%S")
                except (KeyError, ValueError):
                    continue
                if jour0 <= ko < jour1 and ev.get("Eps") not in ("Canc.", "Postp.", "Abd."):
                    matchs.append({"eid": ev.get("Eid"), "ko": ko, "comp": comp,
                                   "match": f'{ev["T1"][0]["Nm"]} vs {ev["T2"][0]["Nm"]}'})

    uniques = {m["eid"]: m for m in matchs}
    matchs = sorted(uniques.values(), key=lambda m: m["ko"])
    if not matchs:
        print(json.dumps({"nb_matchs": 0, "message": "Aucun match trouvé pour la journée"}))
        return

    premier, dernier = matchs[0]["ko"], matchs[-1]["ko"]
    creneaux = fusionner(matchs, maintenant)  # les créneaux déjà passés sont ignorés
    if not creneaux:
        print(json.dumps({"nb_matchs": len(matchs), "message": "Tous les matchs de la journée sont terminés"}))
        return
    debut, fin = creneaux[0][0], creneaux[-1][1]
    cron = heures_cron(creneaux)

    par_heure = Counter(m["ko"].strftime("%Hh") for m in matchs)
    comps = Counter(m["comp"].split(" — ")[0] for m in matchs).most_common(8)
    pic = max(par_heure.items(), key=lambda x: x[1])

    plan = {"journee": jour0.strftime("%Y-%m-%d"),
            "debut_scan": debut.isoformat(timespec="minutes"),
            "fin_scan": fin.isoformat(timespec="minutes"),
            "creneaux": [[d.isoformat(timespec="minutes"), f.isoformat(timespec="minutes")]
                         for d, f in creneaux],
            "cron": cron, "nb_matchs": len(matchs)}
    (ICI / "plan_actif.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")

    # Plan lisible
    dossier = ICI / "plans"
    dossier.mkdir(exist_ok=True)
    lignes = [f"# Plan des matchs — journée du {jour0:%A %d/%m/%Y}", "",
              f"- Matchs : **{len(matchs)}**",
              f"- Premier coup d'envoi : **{premier:%d/%m %H:%M}** — dernier : **{dernier:%d/%m %H:%M}**",
              f"- Fenêtre de scan : **{debut:%d/%m %H:%M} → {fin:%d/%m %H:%M}**",
              f"- Pic : **{pic[0]}** ({pic[1]} matchs)", "", "## Créneaux de scan", ""]
    lignes += [f"- {d:%d/%m %H:%M} → {f:%d/%m %H:%M}" for d, f in creneaux]
    lignes += ["", "## Par heure", ""]
    lignes += [f"- {h} : {n} match(s)" for h, n in sorted(par_heure.items(),
               key=lambda x: (int(x[0][:2]) < DEBUT_JOURNEE, x[0]))]
    lignes += ["", "## Liste complète", ""]
    lignes += [f"- {m['ko']:%H:%M} · {m['comp']} · {m['match']}" for m in matchs]
    (dossier / f"plan_{jour0:%Y%m%d}.md").write_text("\n".join(lignes), encoding="utf-8")

    print(json.dumps({**plan,
                      "premier_coup_envoi": premier.strftime("%H:%M"),
                      "dernier_coup_envoi": dernier.strftime("%d/%m %H:%M"),
                      "pic": f"{pic[0]} ({pic[1]} matchs)",
                      "par_heure": dict(sorted(par_heure.items())),
                      "competitions": comps,
                      "fichier_plan": str(dossier / f"plan_{jour0:%Y%m%d}.md")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
