# RAT (Remote Access Tool)

Un outil d'accès à distance simple et sécurisé écrit en Python.

## Fonctionnalités

- Interface graphique moderne avec PyQt6
- Surveillance système en temps réel
- Capture d'écran
- Communication sécurisée avec chiffrement AES-256-GCM

## Installation

1. Cloner le dépôt :
```bash
git clone https://github.com/votre-username/RAT.git
cd RAT
```

2. Créer un environnement virtuel :
```bash
python -m venv venv
source venv/bin/activate  # Sur Linux/Mac
# ou
.\venv\Scripts\activate  # Sur Windows
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

## Utilisation

1. Lancer le serveur :
```bash
python server.py
```

2. Lancer le client :
```bash
python client.py
```

## Sécurité

- Toutes les communications sont chiffrées avec AES-256-GCM
- Authentification requise pour la connexion
- Pas de stockage de données sensibles

## Licence

MIT License