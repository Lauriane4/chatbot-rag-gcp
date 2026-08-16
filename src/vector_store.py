from datetime import datetime
import os
import chromadb
from sentence_transformers import SentenceTransformer


class GestionnaireVecteurs:
    """Gestionnaire de la base de données vectorielle ChromaDB et des embeddings."""

    def __init__(
        self, 
        dossier_db: str = "./chroma_db", 
        nom_collection: str = "base_connaissances",
        nom_modele_embedding: str = "all-MiniLM-L6-v2"
    ):
        print(f"Chargement du modèle d'embedding '{nom_modele_embedding}'...")
        self.modele_embedding = SentenceTransformer(nom_modele_embedding)

        print(f"Connexion à la base vectorielle ChromaDB dans '{dossier_db}'...")
        self.client = chromadb.PersistentClient(path=dossier_db)
        self.collection = self.client.get_or_create_collection(name=nom_collection)

    def ajouter_chunks(self, chunks: list) -> int:
        """Calcule l'embedding de chaque chunk et l'ajoute dans ChromaDB."""
        if not chunks:
            print("Aucun chunk à ajouter.")
            return 0

        ids = []
        textes = []
        metadatas = []
        embeddings = []

        print(f"Calcul des embeddings pour {len(chunks)} chunk(s)...")

        for idx, chunk in enumerate(chunks):
            # 1. Gestion flexible si chunk est un dict ou un str
            if isinstance(chunk, dict):
                texte = chunk.get("texte") or chunk.get("text", "")
                metadata = chunk.get("metadata", {})
                
                # Récupère l'ID existant ou en fabrique un unique
                if "id" in chunk and chunk["id"]:
                    id_chunk = str(chunk["id"])
                else:
                    source = metadata.get("source", "doc")
                    page = metadata.get("page", "0")
                    c_id = metadata.get("chunk_id", idx)
                    id_chunk = f"{source}_p{page}_c{c_id}_{idx}"
            else:
                texte = str(chunk)
                metadata = {"source": "document_brut", "index": idx}
                id_chunk = f"chunk_{idx}"

            if not str(texte).strip():
                continue

            # 2. Vectorisation du texte
            vecteur = self.modele_embedding.encode(str(texte)).tolist()

            ids.append(id_chunk)
            textes.append(str(texte))
            metadatas.append(metadata)
            embeddings.append(vecteur)

        # 3. Insertion / Mise à jour dans ChromaDB
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=textes,
            metadatas=metadatas
        )

        print(f"{len(textes)} chunk(s) indexé(s) avec succès dans ChromaDB !")
        return len(textes)

    def chercher_similaires(self, question: str, nombre_resultats: int = 3) -> list[dict]:
        """Recherche les chunks les plus proches sémantiquement d'une question."""
        vecteur_question = self.modele_embedding.encode(question).tolist()

        resultats = self.collection.query(
            query_embeddings=[vecteur_question],
            n_results=nombre_resultats
        )

        chunks_trouves = []
        if resultats and resultats["documents"]:
            for i in range(len(resultats["documents"][0])):
                chunks_trouves.append({
                    "texte": resultats["documents"][0][i],
                    "metadata": resultats["metadatas"][0][i],
                    "distance": resultats["distances"][0][i] if "distances" in resultats else None
                })

        return chunks_trouves