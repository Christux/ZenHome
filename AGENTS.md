# Guide du projet ZenHome

## Présentation

ZenHome est une application personnelle de gestion de notes, checklists et tâches. Le backend Python expose une API FastAPI; l'interface est une application JavaScript servie comme fichiers statiques. Les données sont stockées dans SQLite.

## Architecture

- `app/main.py` configure FastAPI, les routes, les fichiers statiques et le cycle de vie de l'application.
- `app/web_routes.py` contient les routes de l'interface et les endpoints de l'API.
- `app/auth.py` authentifie les requêtes avec l'en-tête `X-Auth-Token`.
- `app/business.py` définit les modèles Pydantic et la validation des entrées.
- `app/models.py` définit les tables et relations SQLAlchemy; `models/zenhome_v1.sql` contient le schéma SQL de référence.
- `app/database.py` configure SQLite, les sessions et l'initialisation des données de référence.
- `app/daemon.py` génère périodiquement les occurrences planifiées et notifications.
- `app/cli.py` gère les utilisateurs et leurs tokens.
- `index.html`, `static/js/app.js` et `static/css/app.css` forment l'interface. Elle utilise Bootstrap, jQuery et Bootstrap Icons via CDN; aucun processus de compilation frontend n'est défini.
- `config.yaml`, `Dockerfile` et `docker-compose.yml` décrivent le déploiement, notamment comme add-on Home Assistant et conteneur Docker.

## Développement

Installer les dépendances Python puis lancer le serveur depuis la racine du dépôt :

```sh
pip install -r requirements.txt
ZENHOME_ENV=development uvicorn app.main:app --reload
```

En développement, `ZENHOME_ENV=development` active notamment les logs SQL et l'endpoint de version de développement. Le service écoute sur le port 8000 par défaut.

L'application crée la base `data/zenhome.sqlite3` par défaut. `ZENHOME_DATA_DIR` permet de changer le répertoire des données et `ZENHOME_DAEMON_INTERVAL_SECONDS` l'intervalle du daemon. Utiliser `docker compose up --build` pour démarrer la version conteneurisée.

Les commandes de gestion des utilisateurs sont exécutées depuis la racine du projet :

```sh
python -m app.cli create-user "Alice"
python -m app.cli list-users
python -m app.cli show-token 1
python -m app.cli renew-token 1
```

Ces commandes affichent les tokens lorsque nécessaire. Ne jamais ajouter de token réel aux sources, exemples, rapports ou fixtures.

## Principes de modification

- Garder les responsabilités dans leurs modules existants : validation dans `business.py`, persistance dans les modèles et l'accès base de données, endpoints dans `web_routes.py`, présentation dans les fichiers frontend.
- Pour tout endpoint privé, conserver l'authentification existante et filtrer chaque lecture ou mutation par l'utilisateur courant. Ne jamais faire confiance à un identifiant fourni par le navigateur pour établir la propriété d'une ressource.
- Valider les payloads avec Pydantic et utiliser SQLAlchemy pour les requêtes et mutations; éviter de construire du SQL avec des valeurs utilisateur interpolées.
- Maintenir la cohérence entre les modèles SQLAlchemy et le schéma SQL de référence lors d'un changement de schéma. Préserver les contraintes, clés étrangères et règles de suppression existantes.
- Garder les changements frontend compatibles avec l'interface existante et ses dépendances CDN. Envoyer les requêtes authentifiées via le helper API de `static/js/app.js`.
- Suivre le style existant : Python typé, noms explicites, fonctions ciblées; JavaScript cohérent avec `app.js`; interface et libellés destinés aux utilisateurs en français.
- Ne pas commettre la base locale, de tokens ni d'autres données personnelles. Préserver toute donnée utilisateur existante dans `data/`.

## Vérification

Aucune suite de tests n'est actuellement présente dans le dépôt. Pour une modification d'API, vérifier au minimum le démarrage du service et `/api/health`; vérifier également le parcours concerné et le cloisonnement entre utilisateurs. Pour une modification de schéma ou de déploiement, vérifier l'initialisation de la base et la configuration Docker correspondante.