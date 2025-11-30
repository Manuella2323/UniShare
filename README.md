# UniShare Library (Cloud Saas intégré)
Plateforme académique pour le partage et la recherche de documents universitaires
## 1. Problématique
De nombreux étudiants et chercheurs rencontrent des difficultés pour trouver rapidement des documents académiques (livres, mémoires, rapports, cours, articles). Les ressources sont souvent dispersées sur plusieurs sites, parfois mal référencées, ou limitées à une seule université. Cette fragmentation ralentit l’accès à la connaissance et pousse les étudiants à passer beaucoup de temps à chercher sur Google sans toujours trouver les documents pertinents.
## 2. Objectif général
Créer une plateforme web  qui regroupe l’ensemble des ressources académiques et documentaires disponibles dans les universités partenaires, permettant une recherche unifiée, rapide et intelligente à travers plusieurs institutions.
## 3. Objectifs spécifiques
- Centraliser et structurer les ressources universitaires par domaine (informatique, médecine, droit, mécanique, etc.).
- Permettre aux universités de partager automatiquement leurs documents entre elles.
- Offrir un moteur de recherche unique capable d’interroger plusieurs serveurs universitaires simultanément.
- Favoriser la collaboration interuniversitaire et le libre accès à la connaissance.
- Créer une interface intuitive adaptée aux étudiants, enseignants et chercheurs.
## 4. Description du projet
UniShare Library est une application qui permet de consulter et partager des documents académiques provenant de plusieurs universités. Chaque université héberge son propre serveur contenant ses ressources (livres, mémoires, articles, cours, etc.).

Lorsqu’un utilisateur effectue une recherche :
- La requête est transmise à tous les serveurs partenaires.
- Les résultats sont agrégés et affichés dans une seule interface.
- Les documents peuvent être filtrés par domaine, université, type, niveau d’étude, etc.

L’application propose également une catégorisation claire :
- École primaire
- Lycée / secondaire
- Université / faculté
- Documents officiels
- Ouvrages scientifiques
## 5. Justification du projet
Ce projet répond à un besoin réel du milieu académique : faciliter l’accès aux ressources d’apprentissage et de recherche. En plus de simplifier la vie des étudiants, il valorise les universités en leur permettant de partager leurs productions intellectuelles et d’améliorer leur visibilité. D’un point de vue technique, le projet permet d’expérimenter la mise en place d’un système distribué et collaboratif, un sujet d’actualité dans le domaine informatique.
## 6. Portée du projet (Scope)
- Le projet cible d’abord quelques universités partenaires qui acceptent de mutualiser leurs ressources.
- L’application sera accessible via le web et plus tard sur mobile.
- Les documents seront organisés et indexés par métadonnées (titre, auteur, université, domaine, résumé).
- Une extension future pourrait inclure :
  - Un système d’authentification (étudiant, enseignant, administrateur).
  - Des suggestions personnalisées basées sur l’IA.
  - Un système de recommandation ou de notation des documents.
## 7. Architecture technique (aperçu)
- Frontend : React.js 
- Backend : python
- Base de données : MongoDB ou PostgreSQL
- Communication entre universités : APIs REST, gRPC ou message broker (RabbitMQ)
- Indexation / recherche : Elasticsearch
- Stockage des fichiers : services cloud 

Chaque université = un serveur indépendant
Le système global = un réseau distribué de bibliothèques interconnectées
## 8. Méthodologie de réalisation
1. Phase d’analyse :
   - Étude des besoins des utilisateurs (étudiants, enseignants).
   - Définition des structures de données et des protocoles d’échange.
2. Phase de conception :
   - Création du modèle de base de données.
   - Conception de l’architecture distribuée.
   - Élaboration des interfaces utilisateurs.
3. Phase de développement :
   - Implémentation du prototype local (base centralisée).
   - Extension vers un modèle distribué avec 2 ou 3 serveurs simulés.
   - Intégration du moteur de recherche global.
4. Phase de test et déploiement :
   - Test de la recherche multi-serveur.
   - Hébergement sur un serveur cloud.
   - Tests utilisateurs et amélioration continue.
## 9. Résultats attendus
- Une application fonctionnelle capable de rechercher des documents à travers plusieurs serveurs.
- Une interface claire et intuitive.
- Un modèle technique réutilisable pour d’autres domaines (bibliothèques scolaires, nationales, etc.).
- Une contribution à la transformation numérique des institutions universitaires.
## 10. Perspectives d’évolution
- Déploiement à plus grande échelle (toutes les universités partenaires).
- Application mobile native.
- Intégration de fonctionnalités d’IA (analyse automatique des documents, résumé, recommandation).
- Création d’une communauté d’apprentissage académique autour de la plateforme.

