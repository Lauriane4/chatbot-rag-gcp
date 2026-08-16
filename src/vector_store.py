from datetime import datetime
import os
import re
import chromadb
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi


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

        self.bm25_index = None
        self.corpus_bm25 = []       
        self.documents_bm25 = []    
        
        
        self._synchroniser_bm25_depuis_chroma()

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
        self._synchroniser_bm25_depuis_chroma()
        return len(textes)

    def chercher_similaires(self, question: str, nombre_resultats: int = 4) -> list[dict]:
        """Recherche hybride fusionnant la similarité cosinus (ChromaDB) et les mots-clés (BM25)."""
        rangs_dense = {}
        chunks_dense_dict = {}
        rangs_sparse = {}
        chunks_sparse_dict = {}

        # 1. RECHERCHE VECTORIELLE (ChromaDB)
        vecteur_question = self.modele_embedding.encode(question).tolist()
        resultats_chroma = self.collection.query(
            query_embeddings=[vecteur_question],
            n_results=min(nombre_resultats * 3, 20)
        )

        if resultats_chroma and resultats_chroma.get("ids") and resultats_chroma["ids"][0]:
            for rang, doc_id in enumerate(resultats_chroma["ids"][0]):
                rangs_dense[doc_id] = rang + 1
                chunks_dense_dict[doc_id] = {
                    "id": doc_id,
                    "texte": resultats_chroma["documents"][0][rang],
                    "metadata": resultats_chroma["metadatas"][0][rang]
                }

        # 2. RECHERCHE LEXICALE (BM25)
        if self.bm25_index:
            tokens_question = self._nettoyer_et_tokeniser(question)
            if tokens_question:
                scores_bm25 = self.bm25_index.get_scores(tokens_question)
                indices_tries = sorted(range(len(scores_bm25)), key=lambda i: scores_bm25[i], reverse=True)
                
                for rang, idx in enumerate(indices_tries[:min(nombre_resultats * 3, 20)]):
                    if scores_bm25[idx] > 0:
                        doc = self.documents_bm25[idx]
                        doc_id = doc["id"]
                        rangs_sparse[doc_id] = rang + 1
                        chunks_sparse_dict[doc_id] = doc

        # 3. FUSION PAR RRF (Reciprocal Rank Fusion)
        tous_les_ids = set(rangs_dense.keys()).union(set(rangs_sparse.keys()))
        scores_fusion = {}
        k_constante = 60

        for doc_id in tous_les_ids:
            score = 0.0
            if doc_id in rangs_dense:
                score += 2.0 / (k_constante + rangs_dense[doc_id])
            if doc_id in rangs_sparse:
                score += 0.8 / (k_constante + rangs_sparse[doc_id])
            scores_fusion[doc_id] = score

        # 4. TRI FINAL & TOP_K
        ids_tries = sorted(scores_fusion.keys(), key=lambda d_id: scores_fusion[d_id], reverse=True)
        
        resultats_finaux = []
        for doc_id in ids_tries[:nombre_resultats]:
            chunk_data = chunks_dense_dict.get(doc_id) or chunks_sparse_dict.get(doc_id)
            if chunk_data:
                resultats_finaux.append({
                    "texte": chunk_data["texte"],
                    "metadata": chunk_data["metadata"],
                    "score_rrf": scores_fusion[doc_id]
                })

        return resultats_finaux

    def _nettoyer_et_tokeniser(self, texte: str) -> list[str]:
        """Découpe un texte en minuscules et conserve les codes avec tirets et chiffres."""
        texte_propre = re.sub(r"[^\w\s\-]", " ", texte.lower())
        return [mot for mot in texte_propre.split() if len(mot) > 1]

    def _synchroniser_bm25_depuis_chroma(self):
        """Recharge l'index BM25 à partir des documents existants dans ChromaDB."""
        donnees = self.collection.get()
        if donnees and donnees["documents"]:
            self.documents_bm25 = []
            self.corpus_bm25 = []
            for i in range(len(donnees["documents"])):
                doc_obj = {
                    "id": donnees["ids"][i],
                    "texte": donnees["documents"][i],
                    "metadata": donnees["metadatas"][i] if donnees["metadatas"] else {}
                }
                self.documents_bm25.append(doc_obj)
                self.corpus_bm25.append(self._nettoyer_et_tokeniser(doc_obj["texte"]))
            
            if self.corpus_bm25:
                self.bm25_index = BM25Okapi(self.corpus_bm25)
                print(f"✅ Index BM25 synchronisé avec {len(self.corpus_bm25)} chunks.")