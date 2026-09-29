# Veille UNDER live — version cloud

## Comment ça marche

| Rôle | Où | Quand |
|---|---|---|
| Plan du jour (`cloud_plan.py` → `plan_jour.py`) | GitHub Actions | chaque matin à 06h10, heure de Yaoundé |
| Guetteur (`cloud_scan.py` → `scan_under.py`) | GitHub Actions | toutes les 5 min ; s'arrête aussitôt hors des créneaux du plan |
| Expert (vetos) | Routine Claude cloud, appelée par le guetteur | seulement quand il y a des candidats |
| Messager | application ntfy sur le téléphone | instantané |

Sans routine Claude configurée, le guetteur envoie directement des alertes « ⚠️ À VÉRIFIER » (vetos non contrôlés).

## Secrets GitHub (Settings → Secrets and variables → Actions)

| Nom | Valeur |
|---|---|
| `NTFY_TOPIC` | le nom de ton canal ntfy (secret : quiconque le connaît peut lire tes alertes) |
| `CLAUDE_ROUTINE_URL` | l'URL `/fire` de la routine Claude |
| `CLAUDE_ROUTINE_TOKEN` | le jeton de la routine Claude |

## Routine Claude (claude.ai/code/routines → New routine → Cloud)

- Instructions : contenu de `ROUTINE_PROMPT.md`
- Dépôt : ce dépôt
- Environnement : accès réseau **Custom**, domaine autorisé `ntfy.sh` ; variable d'environnement `NTFY_TOPIC` = ton canal
- Connecteurs : retirer tous ceux qui ne servent pas
- Déclencheur : **API** → copier l'URL et générer le jeton → les mettre dans les secrets GitHub

## Limites

- GitHub peut retarder les tâches planifiées de quelques minutes aux heures chargées.
- Le calcul ne voit ni les cotes, ni les cartons rouges : toujours vérifier avant de jouer.
- Paris simples uniquement ; aucune alerte n'est sûre à 100 %.
