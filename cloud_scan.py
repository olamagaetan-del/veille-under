"""Guetteur cloud (GitHub Actions) : lance scan_under.py, puis transmet les candidats.

- Si la routine Claude est configurée (CLAUDE_ROUTINE_URL + CLAUDE_ROUTINE_TOKEN), les candidats
  lui sont envoyés : Claude applique les vetos et envoie lui-même les alertes ntfy.
- Sinon (ou si l'appel échoue), une alerte ntfy brute est envoyée directement, marquée "à vérifier".
"""
import json, os, subprocess, sys, urllib.request
from pathlib import Path

ICI = Path(__file__).parent
LIEN_1XBET = "https://1xbet.cm/fr/live/football"  # ouvert en touchant l'alerte


def lancer_scan(*args) -> str:
    r = subprocess.run([sys.executable, str(ICI / "scan_under.py"), *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def ntfy(message: str, priorite: str = "high"):
    sujet = os.environ.get("NTFY_TOPIC")
    if not sujet:
        print("NTFY_TOPIC absent : alerte non envoyée ->", message)
        return
    req = urllib.request.Request(f"https://ntfy.sh/{sujet}", data=message.encode("utf-8"),
                                 headers={"Priority": priorite, "Tags": "soccer",
                                          "Click": LIEN_1XBET}, method="POST")
    urllib.request.urlopen(req, timeout=15).read()


def appeler_routine(candidats) -> bool:
    url, jeton = os.environ.get("CLAUDE_ROUTINE_URL"), os.environ.get("CLAUDE_ROUTINE_TOKEN")
    if not (url and jeton):
        return False
    corps = json.dumps({"text": json.dumps(candidats, ensure_ascii=False)}).encode("utf-8")
    req = urllib.request.Request(url, data=corps, method="POST", headers={
        "Authorization": f"Bearer {jeton}",
        "anthropic-beta": "experimental-cc-routine-2026-04-01",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("Routine Claude déclenchée :", json.load(r).get("claude_code_session_url"))
        return True
    except Exception as ex:
        print("Échec de l'appel à la routine Claude :", ex)
        return False


def cote_mini(p: float) -> str:
    return f"{1 / p + 0.05:.2f}".replace(".", ",")


def main():
    res = json.loads(lancer_scan())
    if res.get("hors_fenetre"):
        print(f'Scan {res["heure"]} — hors créneau')
        return
    if res.get("erreur"):
        print("Erreur API :", res["erreur"])
        return
    candidats = res.get("candidats", [])
    if not candidats:
        print(f'Scan {res["heure"]} — {res["nb_live"]} matchs live, 0 opportunité')
        return

    # On marque tout de suite pour ne jamais retraiter le même candidat au scan suivant.
    lancer_scan("--marquer", *[c["cle"] for c in candidats])

    if appeler_routine(candidats):
        return
    for c in candidats:
        ntfy(f'⚠️ À VÉRIFIER (veto non contrôlé) — {c["ligne"]} — {c["match"]} {c["score"]} '
             f'{c["minute"]} — {round(c["p_sans_perte"] * 100)}% sans perte — cote mini {cote_mini(c["p_sans_perte"])}')
    print(f"{len(candidats)} alerte(s) brute(s) envoyée(s)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
