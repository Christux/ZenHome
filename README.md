# ZenHome
Simple domestic note, task and todo list manager

## Connexion

Au premier démarrage, ZenHome crée un token de connexion et l’affiche dans les journaux de l’application. Lors de la mise à niveau d’une base existante, un nouveau token est généré pour chaque utilisateur migré et affiché de la même façon. Saisissez ce token dans la fenêtre de connexion ; il sera conservé dans le stockage local du navigateur.

Les tokens n’expirent pas. Ils sont envoyés aux API dans l’en-tête HTTP `X-Auth-Token`.

## Gestion des utilisateurs

Créez un utilisateur depuis le conteneur en cours d'exécution. Son token est affiché dans la console :

```sh
docker compose exec zenhome python -m app.cli create-user "Alice"
```

Pour retrouver le token d'un utilisateur existant, indiquez son identifiant :

```sh
docker compose exec zenhome python -m app.cli show-token 1
```

Pour lister les utilisateurs sans afficher leurs tokens :

```sh
docker compose exec zenhome python -m app.cli list-users
```

Pour renouveler le token d'un utilisateur, indiquez son identifiant. L'ancien token est immédiatement invalidé :

```sh
docker compose exec zenhome python -m app.cli renew-token 1
```

La commande peut aussi être lancée sans démarrer le serveur :

```sh
docker compose run --rm --no-deps zenhome python -m app.cli create-user "Alice"
```

## Notifications ntfy

Les rappels planifiés sont publiés sur le serveur ntfy configuré par `NTFY_SERVER` (par défaut `https://ntfy.sh`). Les items publics utilisent le topic `{préfixe}_general`; les items privés utilisent `{préfixe}_{nom_utilisateur}` à partir de son nom affiché. Le préfixe vaut `ZenHome` par défaut et se configure avec `ZENHOME_NTFY_TOPIC_PREFIX`. Les topics sont normalisés en minuscules.

Chaque notification contient une action « Voir l'item » qui ouvre sa fiche dans ZenHome. Configurez `HOME_URL` avec l'URL de base atteignable depuis l'appareil recevant les notifications (par défaut `http://localhost:8000`). Avec Docker Compose, cette variable est transmise au conteneur.

Pour l'authentification, configurez `NTFY_TOKEN` ou la paire `NTFY_USER` et `NTFY_PASSWORD`. Avec Docker Compose, ces variables de l'environnement hôte sont transmises au conteneur.
