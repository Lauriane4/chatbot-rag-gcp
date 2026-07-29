from datetime import datetime
import os
import chromadb
from sentence_transformers import SentenceTransformer


class GestionnaireVecteurs:
    """
    Gestionnaire de la base de données vectorielle ChromaDB et des embeddings.

    Description :
        Cette classe encapsule un réseau de neurones local (SentenceTransformer)
        et un client de base de données vectorielle (ChromaDB). Elle permet 
        d'indexer des morceaux de texte (chunks) sous forme de vecteurs numériques 
        et d'effectuer des recherches de similitude sémantique.

    Attributes:
        dossier_db (str): Le chemin vers le dossier où ChromaDB sauvegarde les données.
        nom_collection (str): Le nom de la table/collection dans ChromaDB.
        modele_embedding (SentenceTransformer): Le modèle IA local qui calcule les vecteurs.
        client (chromadb.PersistentClient): Le client de connexion à la base locale.
        collection (chromadb.Collection): La collection active dans ChromaDB.
    """

    def __init__(
        self, 
        dossier_db: str = "./chroma_db", 
        nom_collection: str = "base_connaissances",
        nom_modele_embedding: str = "all-MiniLM-L6-v2"
    ):
        """
        Initialise le modèle d'embedding et la connexion à ChromaDB.

        Args:
            dossier_db (str, optional): Chemin du dossier de stockage local. Défaut: "./chroma_db".
            nom_collection (str, optional): Nom de la collection. Défaut: "base_connaissances".
            nom_modele_embedding (str, optional): Nom du modèle HuggingFace. Défaut: "all-MiniLM-L6-v2".
        """
        print(f"Chargement du modèle d'embedding '{nom_modele_embedding}'...")
        # SentenceTransformer est un réseau de neurones qui convertit un texte en 384 nombres
        self.modele_embedding = SentenceTransformer(nom_modele_embedding)

        print(f"Connexion à la base vectorielle ChromaDB dans '{dossier_db}'...")
        # PersistentClient sauvegarde la base sur le disque dur au lieu de la garder uniquement en RAM
        self.client = chromadb.PersistentClient(path=dossier_db)
        
        # get_or_create_collection crée la collection si elle n'existe pas, ou la charge si elle existe
        self.collection = self.client.get_or_create_collection(name=nom_collection)

    def ajouter_chunks(self, chunks: list[dict]) -> int:
        """
        Calcule l'embedding de chaque chunk et l'ajoute dans ChromaDB.

        Exemple de ce qui est inséré :
            IDs: ["test.pdf_20260729_143000_chunk_1"]
            Embeddings: [[0.012, -0.045, 0.891, ... (384 nombres)]]
            Documents: ["Texte du chunk..."]
            Metadatas: [{"source": "test.pdf", "page": 1}]

        Args:
            chunks (list[dict]): Liste de chunks générée par decouper_texte().

        Returns:
            int: Le nombre de chunks ajoutés avec succès.
        """
        if not chunks:
            print("Aucun chunk à ajouter.")
            return 0

        ids = []
        textes = []
        metadatas = []
        embeddings = []

        print(f"Calcul des embeddings pour {len(chunks)} chunk(s)...")

        for chunk in chunks:
            # 1. On extrait les informations du dictionnaire
            id_chunk = chunk["id"]
            texte = chunk["text"]
            metadata = chunk["metadata"]

            # 2. Le réseau de neurones transforme le texte en vecteur (liste de nombres)
            # .encode() renvoie un tableau numpy, qu'on convertit en liste Python standard avec .tolist()
            vecteur = self.modele_embedding.encode(texte).tolist()

            # 3. On rassemble les données dans nos listes
            ids.append(id_chunk)
            textes.append(texte)
            metadatas.append(metadata)
            embeddings.append(vecteur)

        # 4. Insertion groupée (batch) dans la base ChromaDB
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=textes,
            metadatas=metadatas
        )

        print(f"{len(chunks)} chunk(s) indexé(s) avec succès dans ChromaDB !")
        return len(chunks)

    def chercher_similaires(self, question: str, nombre_resultats: int = 3) -> list[dict]:
        """
        Recherche les chunks les plus proches sémantiquement d'une question.

        Description :
            Cette méthode transforme la question en vecteur numérique, puis
            calcule la distance géométrique dans la base ChromaDB pour 
            retrouver les N morceaux de texte les plus pertinents.

        Exemple :
            Question : "Comment poser mes vacances ?"
            Retourne : Les 3 chunks parlant de congés payés et de portail RH.

        Args:
            question (str): La question de l'utilisateur en langage naturel.
            nombre_resultats (int, optional): Nombre de chunks pertinents à retourner. Défaut: 3.

        Returns:
            list[dict]: Une liste des documents les plus proches avec leur texte et métadonnées.
        """
        # 1. Transformer la question en vecteur avec le MÊME modèle d'embedding
        vecteur_question = self.modele_embedding.encode(question).tolist()

        # 2. Interroger ChromaDB avec ce vecteur
        resultats = self.collection.query(
            query_embeddings=[vecteur_question],
            n_results=nombre_resultats
        )

        # 3. Formater les résultats pour les rendre faciles à lire et manipuler
        chunks_trouves = []
        if resultats and resultats["documents"]:
            for i in range(len(resultats["documents"][0])):
                chunks_trouves.append({
                    "texte": resultats["documents"][0][i],
                    "metadata": resultats["metadatas"][0][i],
                    "distance": resultats["distances"][0][i] if "distances" in resultats else None
                })

        return chunks_trouves