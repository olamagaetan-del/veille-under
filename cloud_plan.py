"""Plan du jour cloud (GitHub Actions) : lance plan_jour.py et envoie le résumé sur ntfy."""
import json, subprocess, sys
from pathlib import Path

from cloud_scan import ntfy

ICI = Path(__file__).parent


def main():
    r = subprocess.run([sys.executable, str(ICI / "plan_jour.py")],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        ntfy(f"❌ Plan du jour : erreur ({r.stderr.strip()[-120:]}). La veille scanne quand même.", "default")
        raise SystemExit(r.stderr)
    plan = json.loads(r.stdout)
    print(json.dumps(plan, ensure_ascii=False, indent=1))
    if not plan.get("creneaux"):
        ntfy(f'📅 {plan.get("message", "Aucun match")} — pas de scan aujourd\'hui', "default")
        return
    debut = plan["creneaux"][0][0][11:16]
    msg = (f'📅 {plan["journee"]} : {plan["nb_matchs"]} matchs · 1er {plan["premier_coup_envoi"]} · '
           f'pic {plan["pic"]} · scans UNDER dès {debut}')
    if plan["nb_matchs"] > 150:
        msg += " · journée dense"
    ntfy(msg, "default")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
