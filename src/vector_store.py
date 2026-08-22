from datetime import datetime
import os
import numpy as np
import chromadb
from sentence_transformers import SentenceTransformer


class GestionnaireVecteurs:
    """
    Gestionnaire de la base de données vectorielle ChromaDB et des embeddings.

    Description :
        Cette classe encapsule un réseau de neurones local (SentenceTransformer)
        et un client de base de données vectorielle (ChromaDB). Elle permet
        d'indexer des morceaux de texte (chunks) sous forme de vecteurs numériques
        et d'effectuer des recherches de similarité sémantique.

        La recherche utilise uniquement la similarité vectorielle (dense), avec
        un reranking optionnel par MMR (Maximal Marginal Relevance) pour éviter
        que les résultats renvoyés soient redondants entre eux. Le MMR ne
        nécessite aucun modèle ou index supplémentaire : il réutilise les
        embeddings déjà calculés par ChromaDB lors de la requête.

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
        self.modele_embedding = SentenceTransformer(nom_modele_embedding)

        print(f"Connexion à la base vectorielle ChromaDB dans '{dossier_db}'...")
        self.client = chromadb.PersistentClient(path=dossier_db)
        # hnsw:space="cosine" : ChromaDB utilise la distance L2 par défaut, mais MiniLM
        # (comme la plupart des modèles sentence-transformers) est entraîné pour la
        # similarité cosinus. Ce paramètre n'est appliqué qu'à LA CRÉATION de la collection —
        # s'il existe déjà une collection en L2, il faut supprimer dossier_db et réindexer.
        self.collection = self.client.get_or_create_collection(
            name=nom_collection,
            metadata={"hnsw:space": "cosine"}
        )

        # Garde-fou : ChromaDB fige la dimension des vecteurs au premier insert.
        # Si on change de modèle d'embedding sans réindexer, les requêtes crashent
        # avec une erreur peu claire côté ChromaDB. On préfère prévenir explicitement.
        if self.collection.count() > 0:
            apercu = self.collection.peek(limit=1)
            dims_existantes = len(apercu["embeddings"][0]) if apercu.get("embeddings") is not None and len(apercu["embeddings"]) > 0 else None
            dims_modele = self.modele_embedding.get_sentence_embedding_dimension()
            if dims_existantes and dims_existantes != dims_modele:
                raise ValueError(
                    f"Le modèle d'embedding actuel '{nom_modele_embedding}' produit des vecteurs de "
                    f"dimension {dims_modele}, mais la base ChromaDB existante ('{dossier_db}') contient "
                    f"des vecteurs de dimension {dims_existantes} (indexés avec un autre modèle).\n"
                    f"→ Supprimez le dossier '{dossier_db}' (ou changez nom_collection), relancez l'appli "
                    f"puis réindexez vos documents pour régénérer la base avec ce modèle."
                )

    def ajouter_chunks(self, chunks: list) -> int:
        """
        Calcule l'embedding de chaque chunk et l'ajoute (ou met à jour) dans ChromaDB.

        Gère les chunks au format dict (clés "texte"/"text" + "metadata" + "id" optionnel)
        ou de simples chaînes de caractères, afin de rester compatible avec
        ProcesseurDocuments.

        Args:
            chunks (list): Liste de chunks (dict ou str).

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

        for idx, chunk in enumerate(chunks):
            if isinstance(chunk, dict):
                texte = chunk.get("texte") or chunk.get("text", "")
                metadata = chunk.get("metadata", {})

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

            vecteur = self.modele_embedding.encode(str(texte)).tolist()

            ids.append(id_chunk)
            textes.append(str(texte))
            metadatas.append(metadata)
            embeddings.append(vecteur)

        # upsert plutôt que add : évite une erreur si on réindexe un document déjà connu
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=textes,
            metadatas=metadatas
        )

        print(f"{len(textes)} chunk(s) indexé(s) avec succès dans ChromaDB !")
        return len(textes)

    def chercher_similaires(
        self,
        question: str,
        nombre_resultats: int = 4,
        diversite: bool = True,
        lambda_diversite: float = 0.7
    ) -> list[dict]:
        """
        Recherche les chunks les plus proches sémantiquement d'une question.

        Si `diversite=True`, on récupère plus de candidats que nécessaire auprès
        de ChromaDB, puis on sélectionne les `nombre_resultats` finaux avec un
        reranking MMR : cela évite de retourner plusieurs chunks quasi identiques
        (ex: 3 paragraphes qui répètent la même information) au détriment d'autres
        passages pertinents mais différents.

        Args:
            question (str): La question de l'utilisateur en langage naturel.
            nombre_resultats (int, optional): Nombre de chunks à retourner. Défaut: 4.
            diversite (bool, optional): Active le reranking MMR. Défaut: True.
            lambda_diversite (float, optional): Compromis pertinence/diversité
                (1.0 = uniquement la pertinence, 0.0 = uniquement la diversité). Défaut: 0.7.

        Returns:
            list[dict]: Une liste des documents les plus proches avec leur texte et métadonnées.
        """
        vecteur_question = self.modele_embedding.encode(question).tolist()

        n_candidats = min(nombre_resultats * 4, 30) if diversite else nombre_resultats

        resultats = self.collection.query(
            query_embeddings=[vecteur_question],
            n_results=n_candidats,
            include=["documents", "metadatas", "distances", "embeddings"]
        )

        candidats = []
        if resultats and resultats.get("documents") and resultats["documents"][0]:
            for i in range(len(resultats["documents"][0])):
                candidats.append({
                    "texte": resultats["documents"][0][i],
                    "metadata": resultats["metadatas"][0][i],
                    "distance": resultats["distances"][0][i] if resultats.get("distances") else None,
                    "embedding": resultats["embeddings"][0][i] if resultats.get("embeddings") is not None else None
                })

        if not candidats:
            return []

        if diversite and len(candidats) > nombre_resultats and candidats[0]["embedding"] is not None:
            candidats = self._reranker_mmr(vecteur_question, candidats, nombre_resultats, lambda_diversite)
        else:
            candidats = candidats[:nombre_resultats]

        # On ne garde pas le vecteur brut dans le résultat final (inutile pour l'appelant)
        for c in candidats:
            c.pop("embedding", None)

        return candidats

    def _reranker_mmr(
        self,
        vecteur_question: list,
        candidats: list[dict],
        k: int,
        lambda_diversite: float = 0.7
    ) -> list[dict]:
        """
        Applique un reranking MMR (Maximal Marginal Relevance).

        À chaque étape, on choisit le candidat qui maximise :
            lambda * pertinence_a_la_question - (1 - lambda) * similarite_max_avec_deja_choisis

        Cela favorise les chunks pertinents tout en pénalisant ceux qui
        ressemblent trop à un chunk déjà sélectionné. Aucun modèle supplémentaire
        n'est chargé : on réutilise les embeddings déjà renvoyés par ChromaDB.
        """
        q = np.array(vecteur_question)
        embeddings = np.array([c["embedding"] for c in candidats])

        def similarite_cosinus(a, b):
            denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-10
            return float(np.dot(a, b) / denom)

        pertinence = [similarite_cosinus(q, e) for e in embeddings]

        selectionnes = []
        restants = list(range(len(candidats)))

        while restants and len(selectionnes) < k:
            if not selectionnes:
                meilleur = max(restants, key=lambda i: pertinence[i])
            else:
                def score_mmr(i):
                    sim_max = max(similarite_cosinus(embeddings[i], embeddings[j]) for j in selectionnes)
                    return lambda_diversite * pertinence[i] - (1 - lambda_diversite) * sim_max
                meilleur = max(restants, key=score_mmr)

            selectionnes.append(meilleur)
            restants.remove(meilleur)

        return [candidats[i] for i in selectionnes]