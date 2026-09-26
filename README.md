# ZenHome
Simple domestic note, task and todo list manager

## Connexion

Au premier démarrage, ZenHome crée un token de connexion et l’affiche dans les journaux de l’application. Lors de la mise à niveau d’une base existante, un nouveau token est généré pour chaque utilisateur migré et affiché de la même façon. Saisissez ce token dans la fenêtre de connexion ; il sera conservé dans le stockage local du navigateur.

Les tokens n’expirent pas. Ils sont envoyés aux API dans l’en-tête HTTP `X-Auth-Token`.
